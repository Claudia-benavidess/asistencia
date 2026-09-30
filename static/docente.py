from browser import document, timer, window

formulario = document.select_one("#finalizar")


def confirmar(evento):
    if not window.confirm("¿Finalizar la clase? Quienes no ingresaron quedarán con FALTA."):
        evento.preventDefault()


if formulario is not None:
    formulario.bind("submit", confirmar)
    timer.set_timeout(lambda: window.location.reload(), 10000)
