import csv
import io
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   send_file, session, url_for)
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

import basedatos
import logica


app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave")
CLAVE_DOCENTE = os.environ.get("CLAVE_DOCENTE", "docente123")
SEGUNDOS_SIN_SENAL = int(os.environ.get("SEGUNDOS_SIN_SENAL", "15"))
ZONA_HORARIA = ZoneInfo("America/Lima")


# HORA

def hora_peru():
    """Hora actual de Perú (sin zona horaria, para guardarla como texto)."""
    return datetime.now(ZONA_HORARIA).replace(tzinfo=None)


def texto(hora):
    return hora.isoformat(timespec="seconds")

def hora_12(valor):
  if not valor:
    return ""
  hora = datetime.fromisoformat(valor)
  return hora.strftime("%I:%M %p").lstrip("0")

app.add_template_filter(hora_12, "hora12")


# BASE DE DATOS (SQLite local o MySQL en AWS RDS, ver basedatos.py)

def bd():
    """Una conexión por petición."""
    if "bd" not in g:
        g.bd = basedatos.BaseDatos()
    return g.bd


@app.teardown_appcontext
def cerrar_bd(_):
    conexion = g.pop("bd", None)
    if conexion:
        conexion.cerrar()


def cargar_estudiantes(con):
    """Carga (o actualiza) la lista de estudiantes desde estudiantes.csv."""
    if not os.path.exists("estudiantes.csv"):
        return

    filas = []
    with open("estudiantes.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            codigo = r.get("codigo", "").strip().upper()
            nombre = r.get("nombre", "").strip()
            if codigo:
                filas.append((codigo, nombre))

    # REPLACE INTO funciona igual en SQLite y en MySQL
    con.ejecutar_varios(
        "REPLACE INTO estudiantes (codigo, nombre) VALUES (?, ?)", filas
    )
    con.confirmar()


# CLASE

def clase_activa():
    return bd().uno(
        "SELECT * FROM clases WHERE activa = 1 ORDER BY id DESC LIMIT 1"
    )


def buscar_estudiante(codigo):
    return bd().uno("SELECT * FROM estudiantes WHERE codigo = ?", (codigo,))


# REGISTROS

def leer_registro(clase_id, codigo):
    """Busca el registro de un alumno en una clase."""
    return bd().uno(
        "SELECT * FROM registros WHERE clase_id = ? AND codigo = ?",
        (clase_id, codigo),
    )


def guardar_registro(clase_id, reg, eventos):
    """Guarda el registro del alumno y sus eventos (salidas / reingresos)."""
    bd().ejecutar(
        """
        REPLACE INTO registros
        (clase_id, codigo, hora_ingreso, estado_ingreso, desconexiones,
         desconectado_desde, ultima_senal, retiro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (clase_id, reg["codigo"], reg["hora_ingreso"], reg["estado_ingreso"],
         reg["desconexiones"], reg["desconectado_desde"], reg["ultima_senal"],
         reg["retiro"]),
    )
    bd().ejecutar_varios(
        "INSERT INTO eventos (clase_id, codigo, tipo, hora) VALUES (?, ?, ?, ?)",
        [(clase_id, reg["codigo"], tipo, texto(hora)) for tipo, hora in eventos],
    )
    bd().confirmar()


# MONITOREO

def revisar_clase(clase_id):
    """Revisa a los alumnos que ya ingresaron y detecta pérdidas de conexión."""
    ahora = hora_peru()
    filas = bd().consultar(
        "SELECT * FROM registros WHERE clase_id = ? AND retiro = 0", (clase_id,)
    )
    for reg in filas:
        antes = dict(reg)
        eventos = []
        logica.revisar_tiempos(reg, ahora, SEGUNDOS_SIN_SENAL, eventos)
        # Solo se escribe en la base si algo cambió (menos viajes a AWS)
        if reg != antes or eventos:
            guardar_registro(clase_id, reg, eventos)


def marcar_presencia(reg, ahora, eventos):
    """El alumno está en la página: registra su reingreso si estaba fuera."""
    if reg["desconectado_desde"] and not reg["retiro"]:
        logica.registrar_reingreso(reg, ahora, eventos)
    if not reg["retiro"]:
        reg["ultima_senal"] = texto(ahora)


# INGRESO DEL ALUMNO

@app.route("/", methods=["GET", "POST"])
def ingreso():
    clase = clase_activa()
    mensaje = None

    if request.method == "POST":
        codigo = request.form.get("codigo", "").strip().upper()
        estudiante = buscar_estudiante(codigo)

        if not clase:
            mensaje = "La clase todavía no ha iniciado. Espera a que el docente la inicie."
        elif not estudiante:
            mensaje = "Código inválido. Revisa tu código institucional."
        else:
            ahora = hora_peru()
            reg = leer_registro(clase["id"], codigo)
            eventos = []

            if reg is None:
                # PRIMER INGRESO
                reg = logica.nuevo_registro(
                    codigo, ahora,
                    logica.a_fecha(clase["hora_inicio"]),
                    clase["tolerancia_min"],
                )
            else:
                # VOLVIÓ A ENTRAR
                logica.revisar_tiempos(reg, ahora, SEGUNDOS_SIN_SENAL, eventos)
                marcar_presencia(reg, ahora, eventos)

            guardar_registro(clase["id"], reg, eventos)
            session["codigo"] = codigo
            return redirect(url_for("aula"))

    return render_template("ingreso.html", clase=clase, mensaje=mensaje)


# AULA DEL ALUMNO

@app.route("/aula")
def aula():
    clase = clase_activa()
    codigo = session.get("codigo")
    if not clase or not codigo:
        return redirect(url_for("ingreso"))

    reg = leer_registro(clase["id"], codigo)
    if reg is None:
        return redirect(url_for("ingreso"))

    return render_template(
        "aula.html",
        clase=clase,
        reg=reg,
        estudiante=buscar_estudiante(codigo),
        estado=logica.estado_final(reg),
    )


# SEÑAL DEL NAVEGADOR (la envía static/aula.py cada 5 segundos)

@app.route("/api/senal", methods=["POST"])
def senal():
    clase = clase_activa()
    codigo = session.get("codigo")
    if not clase or not codigo:
        return jsonify(clase_activa=False)

    reg = leer_registro(clase["id"], codigo)
    if reg is None:
        return jsonify(clase_activa=False)

    datos = request.get_json(silent=True, force=True) or {}
    visible = datos.get("visible", True)
    ahora = hora_peru()
    eventos = []

    # ¿Había perdido la conexión?
    logica.revisar_tiempos(reg, ahora, SEGUNDOS_SIN_SENAL, eventos)

    if visible:
        marcar_presencia(reg, ahora, eventos)
    else:
        logica.registrar_salida(reg, ahora, eventos)
        if not reg["retiro"]:
            reg["ultima_senal"] = texto(ahora)

    guardar_registro(clase["id"], reg, eventos)

    return jsonify(
        clase_activa=True,
        estado=logica.estado_final(reg),
        desconexiones=reg["desconexiones"],
    )


# PANEL DOCENTE

@app.route("/docente", methods=["GET", "POST"])
def docente():
    if request.method == "POST" and "clave" in request.form:
        if request.form["clave"] == CLAVE_DOCENTE:
            session["docente"] = True
        else:
            return render_template("docente_login.html", mensaje="Clave incorrecta.")

    if not session.get("docente"):
        return render_template("docente_login.html", mensaje=None)

    clase = clase_activa()
    filas = []
    if clase:
        revisar_clase(clase["id"])
        filas = filas_reporte(clase["id"])

    ultima = bd().uno(
        "SELECT * FROM clases WHERE activa = 0 ORDER BY id DESC LIMIT 1"
    )

    return render_template(
        "docente.html",
        clase=clase,
        filas=filas,
        ultima=ultima,
        base_datos=basedatos.descripcion(),
    )


@app.post("/docente/iniciar")
def iniciar_clase():
    if not session.get("docente"):
        return redirect(url_for("docente"))

    if not clase_activa():
        curso = request.form.get("curso") or "Clase virtual"
        tolerancia = int(request.form.get("tolerancia") or 10)
        bd().ejecutar(
            "INSERT INTO clases (curso, hora_inicio, tolerancia_min, activa) VALUES (?, ?, ?, 1)",
            (curso, texto(hora_peru()), tolerancia),
        )
        bd().confirmar()

    return redirect(url_for("docente"))


@app.post("/docente/finalizar")
def finalizar_clase():
    if not session.get("docente"):
        return redirect(url_for("docente"))

    clase = clase_activa()
    if not clase:
        return redirect(url_for("docente"))

    revisar_clase(clase["id"])
    bd().ejecutar(
        "UPDATE clases SET activa = 0, hora_fin = ? WHERE id = ?",
        (texto(hora_peru()), clase["id"]),
    )
    bd().confirmar()
    return redirect(url_for("reporte", clase_id=clase["id"]))


# FILAS DEL REPORTE

def filas_reporte(clase_id):
    """
    Se recorren TODOS los estudiantes.
    Si el alumno nunca ingresó -> FALTA. Si ingresó -> se usa su registro.
    (Se leen los registros y eventos en 2 consultas, no una por alumno,
    para que sea rápido aunque la base esté en AWS.)
    """
    estudiantes = bd().consultar("SELECT * FROM estudiantes ORDER BY nombre")

    registros = {
        r["codigo"]: r
        for r in bd().consultar("SELECT * FROM registros WHERE clase_id = ?", (clase_id,))
    }

    eventos_por_alumno = {}
    for e in bd().consultar(
        "SELECT codigo, tipo, hora FROM eventos WHERE clase_id = ? ORDER BY hora",
        (clase_id,),
    ):
        eventos_por_alumno.setdefault(e["codigo"], []).append(e)

    filas = []
    for est in estudiantes:
        codigo = est["codigo"]
        reg = registros.get(codigo)

        if reg is None:
            filas.append({
                "codigo": codigo, 
                "nombre": est["nombre"],
                "hora_ingreso": hora_12(reg["hora_ingreso"]),
                "estado_ingreso": reg["estado_ingreso"] or "",
                "desconexiones": reg["desconexiones"] or 0,
                "salidas": ", ".join(hora_12(e["hora"]) for e in eventos if e["tipo"] == "salida"),
                "reingresos": ", ".join(hora_12(e["hora"]) for e in eventos if e["tipo"] == "reingreso"),
                "conectado": not reg["desconectado_desde"] and not reg["retiro"],
                "estado_final": logica.estado_final(reg),
            })
            continue

        eventos = eventos_por_alumno.get(codigo, [])
        filas.append({
            "codigo": codigo,
            "nombre": est["nombre"],
            "hora_ingreso": (reg["hora_ingreso"] or "")[11:],
            "estado_ingreso": reg["estado_ingreso"] or "",
            "desconexiones": reg["desconexiones"] or 0,
            "salidas": ", ".join(e["hora"][11:] for e in eventos if e["tipo"] == "salida"),
            "reingresos": ", ".join(e["hora"][11:] for e in eventos if e["tipo"] == "reingreso"),
            "conectado": not reg["desconectado_desde"] and not reg["retiro"],
            "estado_final": logica.estado_final(reg),
        })

    return filas


def buscar_clase(clase_id):
    return bd().uno("SELECT * FROM clases WHERE id = ?", (clase_id,))


# REPORTE HTML

@app.route("/reporte/<int:clase_id>")
def reporte(clase_id):
    if not session.get("docente"):
        return redirect(url_for("docente"))

    clase = buscar_clase(clase_id)
    if not clase:
        return redirect(url_for("docente"))

    revisar_clase(clase_id)
    filas = filas_reporte(clase_id)

    estados = (logica.PRESENTE, logica.TARDANZA, logica.FALTA, logica.RETIRO_FALTA)
    resumen = {e: sum(1 for f in filas if f["estado_final"] == e) for e in estados}

    return render_template("reporte.html", clase=clase, filas=filas, resumen=resumen)


# EXPORTAR A EXCEL

@app.route("/reporte/<int:clase_id>/excel")
def reporte_excel(clase_id):
    if not session.get("docente"):
        return redirect(url_for("docente"))

    clase = buscar_clase(clase_id)
    if not clase:
        return redirect(url_for("docente"))

    revisar_clase(clase_id)
    filas = filas_reporte(clase_id)

    colores = {
        logica.PRESENTE: "C8E6D4",
        logica.TARDANZA: "F6E2B3",
        logica.FALTA: "F2C4C0",
        logica.RETIRO_FALTA: "DCCDEE",
    }

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Asistencia"

    hoja.append([f"Reporte de asistencia - {clase['curso']}"])
    hoja.append([
        f"Fecha: {clase['hora_inicio'][:10]}  "
        f"Inicio: {hora_12(clase['hora_inicio'])}  "
        f"Fin: {hora_12(clase['hora_fin'])}"
    ])
    hoja.append([])
    hoja.append(["Código", "Estudiante", "Hora de ingreso", "Estado de ingreso",
                 "Desconexiones", "Horas de salida", "Horas de reingreso", "Estado final"])

    for celda in hoja[4]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="1F3A5F")

    for f in filas:
        estado = f["estado_final"]
        hoja.append([f["codigo"], f["nombre"], f["hora_ingreso"], f["estado_ingreso"],
                     f["desconexiones"], f["salidas"], f["reingresos"], estado])
        hoja.cell(hoja.max_row, 8).fill = PatternFill(
            "solid", fgColor=colores.get(estado, "FFFFFF")
        )

    hoja["A1"].font = Font(bold=True, size=14)
    for col, ancho in zip("ABCDEFGH", (12, 32, 15, 17, 14, 24, 24, 16)):
        hoja.column_dimensions[col].width = ancho

    archivo = io.BytesIO()
    libro.save(archivo)
    archivo.seek(0)

    return send_file(
        archivo,
        as_attachment=True,
        download_name=f"asistencia_{clase['hora_inicio'][:10]}_clase{clase_id}.xlsx",
    )


# SALIR

@app.route("/salir")
def salir():
    session.clear()
    return redirect(url_for("ingreso"))


# CREAR TABLAS Y CARGAR ESTUDIANTES AL ARRANCAR

_con = basedatos.crear_tablas()
cargar_estudiantes(_con)
_con.cerrar()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
