"""
Conexión a la base de datos.

- Si existe la variable de entorno DB_HOST  -> usa MySQL en AWS RDS (nube).
- Si no existe                              -> usa SQLite local (asistencia.db),
                                               útil para probar sin internet.

El resto del programa (app.py) no necesita saber cuál se está usando:
siempre escribe las consultas con "?" y recibe las filas como diccionarios.
"""

import os
import sqlite3

USA_AWS = bool(os.environ.get("DB_HOST"))

RUTA_SQLITE = os.environ.get("BD_ASISTENCIA", "asistencia.db")
NOMBRE_BD = os.environ.get("DB_NAME", "asistencia")


def descripcion():
    """Texto que se muestra en el panel del docente."""
    if USA_AWS:
        return f"AWS RDS (MySQL) · {os.environ['DB_HOST']} · base {NOMBRE_BD}"
    return f"SQLite local · {RUTA_SQLITE}"


def _conectar_mysql(con_base=True):
    import pymysql

    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=NOMBRE_BD if con_base else None,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )


class BaseDatos:
    """Envoltura sencilla para SQLite y MySQL con la misma forma de uso."""

    def __init__(self):
        if USA_AWS:
            self.con = _conectar_mysql()
        else:
            self.con = sqlite3.connect(RUTA_SQLITE, timeout=30)
            self.con.row_factory = sqlite3.Row

    def _sql(self, sql):
        # SQLite usa "?" y MySQL usa "%s" para los parámetros.
        return sql.replace("?", "%s") if USA_AWS else sql

    def consultar(self, sql, parametros=()):
        """Devuelve una lista de diccionarios."""
        cur = self.con.cursor()
        cur.execute(self._sql(sql), parametros)
        filas = [dict(f) for f in cur.fetchall()]
        cur.close()
        return filas

    def uno(self, sql, parametros=()):
        """Devuelve un diccionario o None."""
        filas = self.consultar(sql, parametros)
        return filas[0] if filas else None

    def ejecutar(self, sql, parametros=()):
        cur = self.con.cursor()
        cur.execute(self._sql(sql), parametros)
        cur.close()

    def ejecutar_varios(self, sql, lista):
        if not lista:
            return
        cur = self.con.cursor()
        cur.executemany(self._sql(sql), lista)
        cur.close()

    def confirmar(self):
        self.con.commit()

    def cerrar(self):
        self.con.close()


# ---------------------------------------------------------------
# TABLAS
# ---------------------------------------------------------------

_TABLAS = """
CREATE TABLE IF NOT EXISTS estudiantes (
    codigo VARCHAR(20) PRIMARY KEY,
    nombre VARCHAR(150)
);
CREATE TABLE IF NOT EXISTS clases (
    id {AUTO},
    curso VARCHAR(150),
    hora_inicio VARCHAR(19),
    hora_fin VARCHAR(19),
    tolerancia_min INTEGER,
    activa INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS registros (
    clase_id INTEGER,
    codigo VARCHAR(20),
    hora_ingreso VARCHAR(19),
    estado_ingreso VARCHAR(20),
    desconexiones INTEGER,
    desconectado_desde VARCHAR(19),
    ultima_senal VARCHAR(19),
    retiro INTEGER,
    PRIMARY KEY (clase_id, codigo)
);
CREATE TABLE IF NOT EXISTS eventos (
    id {AUTO},
    clase_id INTEGER,
    codigo VARCHAR(20),
    tipo VARCHAR(20),
    hora VARCHAR(19)
)
"""


def crear_tablas():
    """Crea la base (si es AWS) y las tablas si todavía no existen."""

    if USA_AWS:
        # Si en RDS no se creó la base inicial, la creamos aquí.
        con = _conectar_mysql(con_base=False)
        with con.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{NOMBRE_BD}`")
        con.commit()
        con.close()
        auto = "INT AUTO_INCREMENT PRIMARY KEY"
    else:
        auto = "INTEGER PRIMARY KEY AUTOINCREMENT"

    bd = BaseDatos()
    for sentencia in _TABLAS.replace("{AUTO}", auto).split(";"):
        if sentencia.strip():
            bd.ejecutar(sentencia)
    bd.confirmar()
    return bd
