from browser import ajax, document, timer, window

URL_SENAL = "/api/senal"
SEGUNDOS_ENTRE_SENALES = 5

reloj = None


def pagina_visible():
    return document.visibilityState == "visible"


def mostrar_conexion(conectado, mensaje):
    document["texto"].text = mensaje
    if conectado:
        document["punto"].classList.remove("fuera")
    else:
        document["punto"].classList.add("fuera")


def mostrar_estado(estado, desconexiones):
    sello = document["sello"]
    sello.text = estado
    sello.className = "sello " + estado
    document["desconexiones"].text = f"{desconexiones} de 3 permitidas"


def detener():
    global reloj
    if reloj is not None:
        timer.clear_interval(reloj)
        reloj = None


def respuesta(req):
    """Se ejecuta cuando el servidor responde a la señal."""
    if req.status != 200:
        mostrar_conexion(False, "Sin conexión. Intentando reconectar…")
        return

    datos = req.json
    if not datos["clase_activa"]:
        detener()
        mostrar_conexion(False, "La clase terminó.")
        return

    mostrar_estado(datos["estado"], datos["desconexiones"])

    if datos["estado"] == "RETIRO-FALTA":
        detener()
        mostrar_conexion(False, "Tu asistencia quedó como retiro.")
    elif pagina_visible():
        mostrar_conexion(True, "Conectado a la clase")
    else:
        mostrar_conexion(False, "Saliste de la ventana de la clase")


def enviar_senal(visible=None):
    if visible is None:
        visible = pagina_visible()
    ajax.post(
        URL_SENAL,
        data=window.JSON.stringify({"visible": visible}),
        headers={"Content-Type": "application/json"},
        oncomplete=respuesta,
        timeout=4,
        ontimeout=lambda req: mostrar_conexion(False, "Sin conexión. Intentando reconectar…"),
    )


def cambio_de_visibilidad(evento):
    # Salió de la pestaña / minimizó (False) o volvió (True)
    enviar_senal(pagina_visible())


def al_cerrar(evento):
    # Al cerrar la pestaña no hay tiempo de esperar respuesta: sendBeacon
    window.navigator.sendBeacon(URL_SENAL, window.JSON.stringify({"visible": False}))


document.bind("visibilitychange", cambio_de_visibilidad)
window.bind("pagehide", al_cerrar)

enviar_senal()
reloj = timer.set_interval(enviar_senal, SEGUNDOS_ENTRE_SENALES * 1000)
