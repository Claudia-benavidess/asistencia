# Sistema Web de Control de Asistencia Virtual para la UPC

Mini aula virtual centrada en el control de asistencia. El docente inicia la clase, el estudiante
registra su ingreso con su código y la página controla su permanencia en la clase.

## Cómo ejecutarlo
### 1. Abrir el proyecto en GitHub Codespaces

1. Presiona **`<>Code`**.
2. Dirígete a la sección **`Codespaces`**.
3. Selecciona el símbolo **`+`** para crear un nuevo Codespace.
4. **Aviso:** serás redirigido a una página virtual de **Visual Studio Code**.
5. Espera a que el entorno termine de cargar completamente.

### 2. Instalar las dependencias

Una vez que el entorno haya cargado, abre la **Terminal** y ejecuta primero:
```bash
pip install -r requirements.txt
python app.py
```

La lista de estudiantes está en `estudiantes.csv` (codigo,nombre).

## Archivos
| Archivo | Qué hace | Historia de usuario |
|---|---|---|
| `logica.py` | Reglas: PRESENTE/TARDANZA, desconexiones, 10 min, 4ta salida, estado final | 2, 3, 4, 5 |
| `app.py` | Páginas web, base de datos SQLite, reporte y Excel | 1, 6 |
| `static/aula.py` | Detecta salida de la ventana y pérdida de conexión (señal cada 5 s) | 3, 4 |
| `templates/` | Pantallas: ingreso, aula, panel docente, reporte | 1, 6 |
| `test_logica.py` | Pruebas automáticas de cada regla | todas |

## Cómo detecta las desconexiones
- **Salida de ventana**: el navegador dispara `visibilitychange` al cambiar de pestaña o minimizar.
- **Pérdida de conexión**: la página envía una señal cada 5 s; si el servidor pasa 15 s sin
  recibirla, registra la desconexión desde la última señal.
- Si vuelve en 10 minutos o menos conserva su estado; si no, o si es la 4ta desconexión, RETIRO-FALTA.

## Configuración (variables de entorno)
`CLAVE_DOCENTE`, `SECRET_KEY`, `BD_ASISTENCIA` (ruta de la base de datos), `SEGUNDOS_SIN_SENAL`.
