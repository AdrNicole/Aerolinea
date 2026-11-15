"""Configuracion de la conexion a MySQL.

Los datos se leen de variables de entorno o de un archivo .env en la
carpeta del proyecto (ver .env.ejemplo). Asi la clave no queda escrita
en el codigo fuente.
"""
import os
from pathlib import Path
from urllib.parse import quote_plus

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_SALIDAS = RAIZ / "salidas"

# "Hoy" del dataset: ultima fecha de compra registrada. Los vuelos
# posteriores estan 'programado'. Se usa como fecha de compra por defecto
# al simular ventas, porque con la fecha real ya habrian salido.
from datetime import datetime  # noqa: E402
FECHA_CORTE = datetime(2026, 9, 30, 12, 0)

try:  # python-dotenv es opcional
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env")
except ImportError:
    pass


def url_mysql() -> str:
    """Arma la URL de SQLAlchemy para MySQL con el driver PyMySQL."""
    usuario = os.getenv("AEROLINEA_DB_USUARIO", "root")
    clave = quote_plus(os.getenv("AEROLINEA_DB_CLAVE", ""))
    host = os.getenv("AEROLINEA_DB_HOST", "localhost")
    puerto = os.getenv("AEROLINEA_DB_PUERTO", "3306")
    base = os.getenv("AEROLINEA_DB_NOMBRE", "aerolinea")
    return f"mysql+pymysql://{usuario}:{clave}@{host}:{puerto}/{base}?charset=utf8mb4"
