from datetime import datetime, timedelta

PRESENTE = "PRESENTE"
TARDANZA = "TARDANZA"
FALTA = "FALTA"
RETIRO_FALTA = "RETIRO-FALTA"

MAX_DESCONEXIONES = 4          # la 4ta desconexión es RETIRO-FALTA
MINUTOS_REINGRESO = 10         # tiempo máximo para volver


def a_fecha(texto):
    return datetime.fromisoformat(texto) if texto else None


def estado_de_ingreso(hora_ingreso, hora_inicio, tolerancia_min):
    """¿Llegó a tiempo? -> PRESENTE, si no -> TARDANZA"""
    limite = hora_inicio + timedelta(minutes=tolerancia_min)
    return PRESENTE if hora_ingreso <= limite else TARDANZA


def nuevo_registro(codigo, hora_ingreso, hora_inicio, tolerancia_min):
    return {
        "codigo": codigo,
        "hora_ingreso": hora_ingreso.isoformat(timespec="seconds"),
        "estado_ingreso": estado_de_ingreso(hora_ingreso, hora_inicio, tolerancia_min),
        "desconexiones": 0,
        "desconectado_desde": None,   # None = está conectado
        "ultima_senal": hora_ingreso.isoformat(timespec="seconds"),
        "retiro": 0,                  # 1 = ya tiene RETIRO-FALTA
    }
def registrar_senal(reg, hora):
    reg["ultima_senal"] = hora.isoformat(timespec="seconds")

def registrar_salida(reg, hora, eventos):
    """El estudiante se desconectó o salió de la ventana de la clase."""
    if reg["retiro"] or reg["desconectado_desde"]:
        return
    reg["desconexiones"] += 1
    reg["desconectado_desde"] = hora.isoformat(timespec="seconds")
    eventos.append(("salida", hora))
    if reg["desconexiones"] >= MAX_DESCONEXIONES:
        reg["retiro"] = 1


def registrar_reingreso(reg, hora, eventos):
    """El estudiante volvió. Si fue en <= 10 min conserva su estado inicial."""
    if reg["retiro"] or not reg["desconectado_desde"]:
        return
    fuera = hora - a_fecha(reg["desconectado_desde"])
    
    eventos.append(("reingreso", hora))
    if fuera > timedelta(minutes=MINUTOS_REINGRESO):
        reg["retiro"] = 1
    reg["desconectado_desde"] = None


def revisar_tiempos(reg, ahora, segundos_sin_senal, eventos):
    """Monitoreo: detecta conexiones perdidas y reingresos que no llegaron a tiempo."""
    if reg["retiro"]:
        return
    ultima = a_fecha(reg["ultima_senal"])
    
    if not reg["desconectado_desde"] and ahora - ultima > timedelta(seconds=segundos_sin_senal):
        registrar_salida(reg, ultima, eventos)   # se perdió la conexión desde la última señal
        
    if reg["desconectado_desde"] and not reg["retiro"]:
        if ahora - a_fecha(reg["desconectado_desde"]) > timedelta(minutes=MINUTOS_REINGRESO):
            reg["retiro"] = 1


def estado_final(reg):
    """Calcula el estado final. Sin registro = nunca ingresó = FALTA."""
    if reg is None:
        return FALTA
    if reg["retiro"]:
        return RETIRO_FALTA
    return reg["estado_ingreso"]
