# Sistema de asistencia para clases virtuales (UPC)

Mini aula virtual centrada en asistencia. El docente inicia la clase, el estudiante
registra su ingreso con su código y la página controla su permanencia.

## Cómo ejecutarlo
```bash
pip install -r requirements.txt
python app.py
```
- Estudiantes: http://127.0.0.1:5000
- Docente: http://127.0.0.1:5000/docente (clave de prueba: `docente123`)
- Pruebas de las reglas: `pytest`

La lista de estudiantes está en `estudiantes.csv` (codigo,nombre).

## Archivos
| Archivo | Qué hace | Historia de usuario |
|---|---|---|
| `logica.py` | Reglas: PRESENTE/TARDANZA, desconexiones, 10 min, 4ta salida, estado final | 2, 3, 4, 5 |
| `app.py` | Páginas web, base de datos SQLite, reporte y Excel | 1, 6 |
| `static/aula.js` | Detecta salida de la ventana y pérdida de conexión (señal cada 5 s) | 3, 4 |
| `templates/` | Pantallas: ingreso, aula, panel docente, reporte | 1, 6 |
| `test_logica.py` | Pruebas automáticas de cada regla | todas |

## Cómo detecta las desconexiones
- **Salida de ventana**: el navegador dispara `visibilitychange` al cambiar de pestaña o minimizar.
- **Pérdida de conexión**: la página envía una señal cada 5 s; si el servidor pasa 15 s sin
  recibirla, registra la desconexión desde la última señal.
- Si vuelve en 10 minutos o menos conserva su estado; si no, o si es la 4ta desconexión, RETIRO-FALTA.

## Configuración (variables de entorno)
`CLAVE_DOCENTE`, `SECRET_KEY`, `BD_ASISTENCIA` (ruta de la base de datos), `SEGUNDOS_SIN_SENAL`.
