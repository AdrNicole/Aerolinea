"""Patron SINGLETON: una sola conexion (engine) para toda la aplicacion.

Por que Singleton: el engine de SQLAlchemy administra un pool de
conexiones; crear uno nuevo en cada repositorio abriria conexiones de
mas y desperdiciaria recursos. Con __new__ todos los repositorios
reciben la misma instancia.
"""
from contextlib import contextmanager

import pandas as pd

from .config import url_mysql


class ConexionMySQL:
    _instancia = None

    def __new__(cls, url: str | None = None):
        if cls._instancia is None:
            # Import diferido: el resto del sistema (patrones, analisis)
            # funciona y se prueba aunque SQLAlchemy no este instalado.
            from sqlalchemy import create_engine

            instancia = super().__new__(cls)
            instancia.engine = create_engine(url or url_mysql(), pool_pre_ping=True)
            cls._instancia = instancia
        return cls._instancia

    # --- lectura ---------------------------------------------------------
    def consultar(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        """Ejecuta un SELECT y devuelve un DataFrame."""
        from sqlalchemy import text

        with self.engine.connect() as cn:
            return pd.read_sql(text(sql), cn, params=params or {})

    # --- escritura ---------------------------------------------------------
    @contextmanager
    def transaccion(self):
        """Bloque transaccional: COMMIT si todo sale bien, ROLLBACK si falla.

        Uso:
            with ConexionMySQL().transaccion() as cn:
                cn.execute(text("UPDATE ..."), {...})
        """
        with self.engine.begin() as cn:
            yield cn

    @classmethod
    def reiniciar(cls):
        """Solo para pruebas: descarta la instancia actual."""
        if cls._instancia is not None:
            cls._instancia.engine.dispose()
        cls._instancia = None
