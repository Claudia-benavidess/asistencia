from datetime import datetime, timedelta
import logica as L

INICIO = datetime(2026, 9, 25, 8, 0, 0)


def reg_en(minutos):
    return L.nuevo_registro("U1", INICIO + timedelta(minutes=minutos), INICIO, 10)


def test_presente_y_tardanza():
    assert reg_en(5)["estado_ingreso"] == L.PRESENTE
    assert reg_en(10)["estado_ingreso"] == L.PRESENTE
    assert reg_en(11)["estado_ingreso"] == L.TARDANZA


def test_sin_ingreso_es_falta():
    assert L.estado_final(None) == L.FALTA


def test_reingreso_a_tiempo_conserva_estado():
    r, ev = reg_en(15), []                      # TARDANZA
    L.registrar_salida(r, INICIO + timedelta(minutes=30), ev)
    L.registrar_reingreso(r, INICIO + timedelta(minutes=39), ev)
    assert L.estado_final(r) == L.TARDANZA


def test_reingreso_tarde_es_retiro():
    r, ev = reg_en(0), []
    L.registrar_salida(r, INICIO + timedelta(minutes=30), ev)
    L.registrar_reingreso(r, INICIO + timedelta(minutes=41), ev)
    assert L.estado_final(r) == L.RETIRO_FALTA


def test_cuarta_desconexion_es_retiro():
    r, ev = reg_en(0), []
    for i in range(3):
        L.registrar_salida(r, INICIO + timedelta(minutes=10 * i + 5), ev)
        L.registrar_reingreso(r, INICIO + timedelta(minutes=10 * i + 6), ev)
    assert L.estado_final(r) == L.PRESENTE
    L.registrar_salida(r, INICIO + timedelta(minutes=50), ev)
    assert L.estado_final(r) == L.RETIRO_FALTA


def test_perdida_de_conexion_detectada_por_el_monitoreo():
    r, ev = reg_en(0), []
    ahora = INICIO + timedelta(minutes=20)       # sin señales desde el ingreso
    L.revisar_tiempos(r, ahora, 15, ev)
    assert r["desconexiones"] == 1 and L.estado_final(r) == L.RETIRO_FALTA
