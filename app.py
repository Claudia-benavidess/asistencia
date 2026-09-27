import csv
import io
import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   send_file, session, url_for)
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

import logica

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave")

BD = os.environ.get("BD_ASISTENCIA", "asistencia.db")
CLAVE_DOCENTE = os.environ.get("CLAVE_DOCENTE", "docente123")
SEGUNDOS_SIN_SENAL = int(os.environ.get("SEGUNDOS_SIN_SENAL", "15"))
ZONA_HORARIA = ZoneInfo("America/Lima")


def hora_peru():
    """Hora actual de Perú, aunque el servidor esté en otro país (Codespaces, AWS)."""
    return datetime.now(ZONA_HORARIA).replace(tzinfo=None)


# ---------------------------------------------------------------- base de datos
def bd():
    if "bd" not in g:
        g.bd = sqlite3.connect(BD)
        g.bd.row_factory = sqlite3.Row
    return g.bd


@app.teardown_appcontext
def cerrar_bd(_):
    conexion = g.pop("bd", None)
    if conexion:
        conexion.close()


def crear_tablas():
    con = sqlite3.connect(BD)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS estudiantes (codigo TEXT PRIMARY KEY, nombre TEXT);
        CREATE TABLE IF NOT EXISTS clases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, curso TEXT, hora_inicio TEXT,
            hora_fin TEXT, tolerancia_min INTEGER, activa INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS registros (
            clase_id INTEGER, codigo TEXT, hora_ingreso TEXT, estado_ingreso TEXT,
            desconexiones INTEGER, desconectado_desde TEXT, ultima_senal TEXT,
            retiro INTEGER, PRIMARY KEY (clase_id, codigo));
        CREATE TABLE IF NOT EXISTS eventos (
            clase_id INTEGER, codigo TEXT, tipo TEXT, hora TEXT);
    """)
    # Carga la lista de estudiantes desde estudiantes.csv (codigo,nombre)
    if os.path.exists("estudiantes.csv"):
        with open("estudiantes.csv", encoding="utf-8") as f:
            filas = [(r["codigo"].strip().upper(), r["nombre"].strip()) for r in csv.DictReader(f)]
        con.executemany("INSERT OR REPLACE INTO estudiantes VALUES (?, ?)", filas)
    con.commit()
    con.close()


def clase_activa():
    return bd().execute("SELECT * FROM clases WHERE activa = 1 ORDER BY id DESC LIMIT 1").fetchone()


def leer_registro(clase_id, codigo):
    fila = bd().execute("SELECT * FROM registros WHERE clase_id=? AND codigo=?",
                        (clase_id, codigo)).fetchone()
    return dict(fila) if fila else None


def guardar_registro(clase_id, reg, eventos):
    bd().execute("""INSERT OR REPLACE INTO registros VALUES (?,?,?,?,?,?,?,?)""",
                 (clase_id, reg["codigo"], reg["hora_ingreso"], reg["estado_ingreso"],
                  reg["desconexiones"], reg["desconectado_desde"], reg["ultima_senal"],
                  reg["retiro"]))
    for tipo, hora in eventos:
        bd().execute("INSERT INTO eventos VALUES (?,?,?,?)",
                     (clase_id, reg["codigo"], tipo, hora.isoformat(timespec="seconds")))
    bd().commit()


def revisar_clase(clase_id):
    """Recorre a todos los conectados para detectar pérdidas de conexión."""
    ahora = hora_peru()
    filas = bd().execute("SELECT * FROM registros WHERE clase_id=? AND retiro=0", (clase_id,))
    for fila in filas.fetchall():
        reg, eventos = dict(fila), []
        logica.revisar_tiempos(reg, ahora, SEGUNDOS_SIN_SENAL, eventos)
        guardar_registro(clase_id, reg, eventos)


# ---------------------------------------------------------------- estudiante
@app.route("/", methods=["GET", "POST"])
def ingreso():
    clase = clase_activa()
    mensaje = None
    if request.method == "POST":
        codigo = request.form.get("codigo", "").strip().upper()
        estudiante = bd().execute("SELECT * FROM estudiantes WHERE codigo=?", (codigo,)).fetchone()
        if not clase:
            mensaje = "La clase todavía no ha iniciado. Espera a que el docente la inicie."
        elif not estudiante:
            mensaje = "Código inválido. Revisa tu código institucional e inténtalo de nuevo."
        else:
            ahora = hora_peru()
            reg = leer_registro(clase["id"], codigo)
            eventos = []
            if reg is None:        # primer ingreso -> PRESENTE o TARDANZA
                reg = logica.nuevo_registro(codigo, ahora, logica.a_fecha(clase["hora_inicio"]),
                                            clase["tolerancia_min"])
            else:                  # volvió a entrar (cerró la pestaña, etc.)
                logica.revisar_tiempos(reg, ahora, SEGUNDOS_SIN_SENAL, eventos)
                logica.registrar_reingreso(reg, ahora, eventos)
                reg["ultima_senal"] = ahora.isoformat(timespec="seconds")
            guardar_registro(clase["id"], reg, eventos)
            session["codigo"] = codigo
            return redirect(url_for("aula"))
    return render_template("ingreso.html", clase=clase, mensaje=mensaje)


@app.route("/aula")
def aula():
    clase = clase_activa()
    codigo = session.get("codigo")
    if not clase or not codigo:
        return redirect(url_for("ingreso"))
    reg = leer_registro(clase["id"], codigo)
    if reg is None:
        return redirect(url_for("ingreso"))
    estudiante = bd().execute("SELECT * FROM estudiantes WHERE codigo=?", (codigo,)).fetchone()
    return render_template("aula.html", clase=clase, reg=reg, estudiante=estudiante,
                           estado=logica.estado_final(reg))


@app.route("/api/senal", methods=["POST"])
def senal():
    """El navegador del estudiante avisa cada pocos segundos si la clase está visible."""
    clase = clase_activa()
    codigo = session.get("codigo")
    if not clase or not codigo:
        return jsonify(clase_activa=False)
    reg = leer_registro(clase["id"], codigo)
    if reg is None:
        return jsonify(clase_activa=False)
    datos = request.get_json(silent=True) or {}
    ahora, eventos = hora_peru(), []
    logica.revisar_tiempos(reg, ahora, SEGUNDOS_SIN_SENAL, eventos)
    if datos.get("visible", True):
        logica.registrar_reingreso(reg, ahora, eventos)
    else:
        logica.registrar_salida(reg, ahora, eventos)
    reg["ultima_senal"] = ahora.isoformat(timespec="seconds")
    guardar_registro(clase["id"], reg, eventos)
    return jsonify(clase_activa=True, estado=logica.estado_final(reg),
                   desconexiones=reg["desconexiones"])


# ---------------------------------------------------------------- docente
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
    ultima = bd().execute("SELECT * FROM clases WHERE activa=0 ORDER BY id DESC LIMIT 1").fetchone()
    return render_template("docente.html", clase=clase, filas=filas, ultima=ultima)


@app.post("/docente/iniciar")
def iniciar_clase():
    if not session.get("docente"):
        return redirect(url_for("docente"))
    if not clase_activa():
        bd().execute("INSERT INTO clases (curso, hora_inicio, tolerancia_min) VALUES (?,?,?)",
                     (request.form.get("curso") or "Clase virtual",
                      hora_peru().isoformat(timespec="seconds"),
                      int(request.form.get("tolerancia") or 10)))
        bd().commit()
    return redirect(url_for("docente"))


@app.post("/docente/finalizar")
def finalizar_clase():
    if not session.get("docente"):
        return redirect(url_for("docente"))
    clase = clase_activa()
    if clase:
        revisar_clase(clase["id"])
        bd().execute("UPDATE clases SET activa=0, hora_fin=? WHERE id=?",
                     (hora_peru().isoformat(timespec="seconds"), clase["id"]))
        bd().commit()
        return redirect(url_for("reporte", clase_id=clase["id"]))
    return redirect(url_for("docente"))


def filas_reporte(clase_id):
    """Une la lista de estudiantes con sus registros. Quien no ingresó queda en FALTA."""
    filas = []
    for est in bd().execute("SELECT * FROM estudiantes ORDER BY nombre").fetchall():
        reg = leer_registro(clase_id, est["codigo"])
        eventos = bd().execute("SELECT tipo, hora FROM eventos WHERE clase_id=? AND codigo=? "
                               "ORDER BY hora", (clase_id, est["codigo"])).fetchall()
        filas.append({
            "codigo": est["codigo"],
            "nombre": est["nombre"],
            "hora_ingreso": reg["hora_ingreso"][11:] if reg else "",
            "estado_ingreso": reg["estado_ingreso"] if reg else "",
            "desconexiones": reg["desconexiones"] if reg else 0,
            "salidas": ", ".join(e["hora"][11:] for e in eventos if e["tipo"] == "salida"),
            "reingresos": ", ".join(e["hora"][11:] for e in eventos if e["tipo"] == "reingreso"),
            "conectado": bool(reg and not reg["desconectado_desde"] and not reg["retiro"]),
            "estado_final": logica.estado_final(reg),
        })
    return filas


@app.route("/reporte/<int:clase_id>")
def reporte(clase_id):
    if not session.get("docente"):
        return redirect(url_for("docente"))
    clase = bd().execute("SELECT * FROM clases WHERE id=?", (clase_id,)).fetchone()
    filas = filas_reporte(clase_id)
    resumen = {e: sum(1 for f in filas if f["estado_final"] == e)
               for e in (logica.PRESENTE, logica.TARDANZA, logica.FALTA, logica.RETIRO_FALTA)}
    return render_template("reporte.html", clase=clase, filas=filas, resumen=resumen)


@app.route("/reporte/<int:clase_id>/excel")
def reporte_excel(clase_id):
    if not session.get("docente"):
        return redirect(url_for("docente"))
    clase = bd().execute("SELECT * FROM clases WHERE id=?", (clase_id,)).fetchone()
    colores = {"PRESENTE": "C8E6D4", "TARDANZA": "F6E2B3", "FALTA": "F2C4C0",
               "RETIRO-FALTA": "DCCDEE"}
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Asistencia"
    hoja.append([f"Reporte de asistencia - {clase['curso']}"])
    hoja.append([f"Fecha: {clase['hora_inicio'][:10]}  Inicio: {clase['hora_inicio'][11:]}  "
                 f"Fin: {(clase['hora_fin'] or '')[11:]}"])
    hoja.append([])
    hoja.append(["Código", "Estudiante", "Hora de ingreso", "Estado de ingreso",
                 "Desconexiones", "Horas de salida", "Horas de reingreso", "Estado final"])
    for celda in hoja[4]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="1F3A5F")
    for f in filas_reporte(clase_id):
        hoja.append([f["codigo"], f["nombre"], f["hora_ingreso"], f["estado_ingreso"],
                     f["desconexiones"], f["salidas"], f["reingresos"], f["estado_final"]])
        hoja.cell(hoja.max_row, 8).fill = PatternFill("solid", fgColor=colores[f["estado_final"]])
    hoja["A1"].font = Font(bold=True, size=14)
    for col, ancho in zip("ABCDEFGH", (12, 32, 15, 17, 14, 24, 24, 16)):
        hoja.column_dimensions[col].width = ancho

    archivo = io.BytesIO()
    libro.save(archivo)
    archivo.seek(0)
    return send_file(archivo, as_attachment=True,
                     download_name=f"asistencia_{clase['hora_inicio'][:10]}_clase{clase_id}.xlsx")


@app.route("/salir")
def salir():
    session.clear()
    return redirect(url_for("ingreso"))


crear_tablas()

if __name__ == "__main__":
    app.run(debug=True)
