"""Patron Strategy: estrategias de precio intercambiables."""
from datetime import datetime

import pytest

from aerolinea.patrones.precio import (CalculadoraPrecio, ContextoPrecio, PrecioDinamico,
                                       PrecioFijo, PrecioPorAnticipacion,
                                       PrecioPorOcupacion, factor_de_tabla)

NORMAL = datetime(2027, 3, 10)
ALTA = datetime(2027, 7, 10)


def ctx(dias=90, ocupacion=0.3, fecha=NORMAL, base=100.0):
    return ContextoPrecio(base, dias, ocupacion, fecha)


@pytest.mark.parametrize("dias,esperado", [(0, 2.46), (3, 2.46), (4, 1.89), (30, 1.21),
                                           (31, 1.08), (120, 1.0), (400, 0.95)])
def test_limites_de_tramos_de_anticipacion(dias, esperado):
    assert PrecioPorAnticipacion().calcular(ctx(dias=dias)) == pytest.approx(100 * esperado)


def test_ocupacion_llena():
    assert factor_de_tabla(PrecioPorOcupacion().tabla, 1.0) == 1.61


def test_escenario_de_referencia_es_el_precio_base():
    assert PrecioDinamico().calcular(ctx()) == pytest.approx(100)


def test_dinamico_combina_los_tres_factores():
    precio = PrecioDinamico().calcular(ctx(dias=2, ocupacion=0.96, fecha=ALTA))
    assert precio == pytest.approx(100 * 2.46 * 1.61 * 1.17)


def test_calculadora_cambia_de_estrategia_en_tiempo_de_ejecucion():
    c = CalculadoraPrecio(PrecioFijo())
    caso = ctx(dias=2)
    assert c.cotizar(caso) == 100
    c.cambiar_estrategia(PrecioPorAnticipacion())
    assert c.cotizar(caso) == 246


def test_desde_calibracion():
    cal = {"anticipacion": [(10, 2.0), (float("inf"), 1.0)],
           "ocupacion": [(float("inf"), 1.0)], "temporada_alta": 1.5}
    e = PrecioDinamico.desde_calibracion(cal)
    assert e.calcular(ctx(dias=5, fecha=ALTA)) == pytest.approx(300)


@pytest.mark.parametrize("kwargs", [dict(base=0), dict(dias=-1), dict(ocupacion=1.2)])
def test_contexto_invalido(kwargs):
    with pytest.raises(ValueError):
        ctx(**kwargs)
