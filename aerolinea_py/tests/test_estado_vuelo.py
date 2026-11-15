"""Patron State: transiciones validas e invalidas del vuelo."""
from datetime import datetime, timedelta

import pytest

from aerolinea.patrones.estado_vuelo import TransicionInvalida, VueloOperacion

SALIDA = datetime(2027, 1, 10, 8, 0)


def vuelo(estado="programado", persistencia=None):
    return VueloOperacion(1, "LP1000", SALIDA, estado, persistencia=persistencia)


def test_ciclo_completo():
    v = vuelo()
    v.iniciar_embarque()
    v.despegar(SALIDA + timedelta(minutes=5))
    v.aterrizar()
    assert v.estado == "aterrizado"
    assert v.historial == ["programado", "embarcando", "en vuelo", "aterrizado"]
    assert v.retraso_min == 5


@pytest.mark.parametrize("accion", ["despegar", "aterrizar"])
def test_programado_no_puede_saltar_estados(accion):
    v = vuelo()
    with pytest.raises(TransicionInvalida):
        getattr(v, accion)()
    assert v.estado == "programado"


@pytest.mark.parametrize("estado", ["aterrizado", "cancelado"])
def test_estados_finales_no_aceptan_acciones(estado):
    v = vuelo(estado)
    for accion in ("iniciar_embarque", "despegar", "aterrizar", "cancelar"):
        with pytest.raises(TransicionInvalida):
            getattr(v, accion)()


def test_en_vuelo_no_se_puede_cancelar():
    v = vuelo("en vuelo")
    with pytest.raises(TransicionInvalida):
        v.cancelar("tarde")


def test_solo_programado_permite_venta():
    assert vuelo().permite_venta
    assert not vuelo("embarcando").permite_venta


def test_persistencia_recibe_cada_cambio():
    llamadas = []
    v = vuelo(persistencia=lambda *args: llamadas.append(args))
    v.iniciar_embarque()
    hora = SALIDA + timedelta(minutes=20)
    v.despegar(hora)
    assert llamadas == [(1, "embarcando", None), (1, "en vuelo", hora)]


def test_si_la_bd_rechaza_el_cambio_el_estado_no_cambia():
    def falla(*_):
        raise RuntimeError("trigger rechazo la transicion")
    v = vuelo(persistencia=falla)
    with pytest.raises(RuntimeError):
        v.iniciar_embarque()
    assert v.estado == "programado"


def test_estado_desconocido():
    with pytest.raises(ValueError):
        vuelo("volando")
