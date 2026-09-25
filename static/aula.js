// Monitorea la permanencia: cada 5 s envía una "señal" al servidor.
// Si el estudiante cambia de pestaña o minimiza, envía visible=false (salida).
// Si se corta internet, las señales dejan de llegar y el servidor lo detecta.
const sello = document.getElementById("sello");
const punto = document.getElementById("punto");
const texto = document.getElementById("texto");
const desconexiones = document.getElementById("desconexiones");

function enviarSenal(visible) {
  const cuerpo = JSON.stringify({ visible });
  if (!visible && navigator.sendBeacon) {        // funciona aunque la pestaña se cierre
    navigator.sendBeacon("/api/senal", new Blob([cuerpo], { type: "application/json" }));
    return;
  }
  fetch("/api/senal", { method: "POST", headers: { "Content-Type": "application/json" }, body: cuerpo })
    .then(r => r.json())
    .then(d => {
      if (!d.clase_activa) { texto.textContent = "La clase terminó."; clearInterval(reloj); return; }
      sello.textContent = d.estado;
      sello.className = "sello " + d.estado;
      desconexiones.textContent = d.desconexiones + " de 3 permitidas";
      punto.classList.remove("fuera");
      texto.textContent = d.estado === "RETIRO-FALTA" ? "Tu asistencia quedó como retiro." : "Conectado a la clase";
    })
    .catch(() => { punto.classList.add("fuera"); texto.textContent = "Sin conexión. Intentando reconectar…"; });
}

document.addEventListener("visibilitychange", () => enviarSenal(!document.hidden));
const reloj = setInterval(() => { if (!document.hidden) enviarSenal(true); }, 5000);
enviarSenal(true);
