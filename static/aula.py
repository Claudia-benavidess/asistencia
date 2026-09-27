import json
import time
import threading
import urllib.request
import urllib.error

# Nota: Este código está traducido a Python manteniendo la lógica original, 
# pero al ser un entorno de consola (Python standard library), las referencias al 
# DOM de JavaScript (document.getElementById, navigator.sendBeacon, fetch, etc.) 
# se simulan o se adaptan conceptualmente si se ejecutara en un entorno backend o de escritorio.

def enviar_senal(visible):
    cuerpo = json.dumps({"visible": visible})
    url = "/api/senal"
    
    try:
        # Simulación de la petición HTTP POST usando urllib
        req = urllib.request.Request(
            url,
            data=cuerpo.encode('utf-8'),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
            d = json.loads(response.read().decode('utf-8'))
            
            if not d.get("clase_activa"):
                print("La clase terminó.")
                return False  # Indicar detener el reloj
                
            estado = d.get("estado")
            desconexiones_count = d.get("desconexiones")
            
            print(f"Estado: {estado} | Desconexiones: {desconexiones_count} de 3 permitidas")
            
            if estado == "RETIRO-FALTA":
                print("Tu asistencia quedó como retiro.")
            else:
                print("Conectado a la clase")
                
    except (urllib.error.URLError, Exception):
        print("Sin conexión. Intentando reconectar…")
    
    return True

def main():
    print("Iniciando monitoreo de permanencia...")
    # Simulación del estado inicial
    enviar_senal(True)
    
    # Simulación del intervalo de 5 segundos
    try:
        while True:
            time.sleep(5)
            activo = enviar_senal(True)
            if not activo:
                break
    except KeyboardInterrupt:
        print("\nMonitoreo finalizado por el usuario.")

if __name__ == "__main__":
    main()
