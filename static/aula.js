function enviarSenal() {
    fetch("/api/senal", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            visible: document.visibilityState === "visible"
        })
    })
    .then(response => response.json())
    .then(data => {
        if (!data.clase_activa) {
            document.getElementById("texto").textContent = "La clase terminó.";
            return;
        }

        document.getElementById("desconexiones").textContent =
            data.desconexiones + " de 4 permitidas";

        const sello = document.getElementById("sello");
        sello.textContent = data.estado;
        sello.className = "sello " + data.estado;

        const texto = document.getElementById("texto");

        if (data.estado === "RETIRO-FALTA") {
            texto.textContent = "Tu asistencia quedó como retiro.";
        } else {
            texto.textContent = "Conectado a la clase";
        }
    })
    .catch(() => {
        document.getElementById("texto").textContent =
            "Sin conexión. Intentando reconectar…";
    });
}

enviarSenal();

setInterval(enviarSenal, 5000);
