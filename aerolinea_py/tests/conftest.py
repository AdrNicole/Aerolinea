import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aerolinea.modelos import Vuelo  # noqa: E402


@pytest.fixture
def hacer_vuelo():
    """Fabrica de vuelos de prueba (sin base de datos)."""
    def _hacer(id_vuelo=1, numero="LP1000", origen="LIM", destino="CUZ",
               salida=datetime(2027, 1, 10, 8, 0), estado="programado",
               capacidad=180, ocupados=0, duracion=70, id_ruta=1):
        return Vuelo(id_vuelo, numero, origen, destino, salida, estado,
                     capacidad, ocupados, duracion, None, id_ruta)
    return _hacer


@pytest.fixture
def pasajeros_df():
    return pd.DataFrame({"nombre": ["Ana Ruiz", "Luis Soto"], "codigo_pnr": ["ABC123", "ABC123"]})
