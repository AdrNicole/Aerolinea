"""Patron Builder: reserva con varios tramos y pasajeros."""
from datetime import datetime, timedelta

import pytest

from aerolinea.patrones.precio import CalculadoraPrecio, PrecioDinamico, PrecioFijo
from aerolinea.patrones.reserva_builder import ErrorReserva, ReservaBuilder

COMPRA = datetime(2026, 12, 1, 10, 0)
ASIENTOS = ["1A", "1B", "1C", "2A", "2B"]


def builder(estrategia=None):
    return ReservaBuilder(CalculadoraPrecio(estrategia or PrecioFijo()),
                          precio_base=lambda vuelo, tarifa: 100.0 * tarifa,
                          fecha_compra=COMPRA)


@pytest.fixture
def ida_vuelta(hacer_vuelo):
    ida = hacer_vuelo(1, "LP1", "LIM", "CUZ", datetime(2027, 1, 10, 8, 0))
    vuelta = hacer_vuelo(2, "LP2", "CUZ", "LIM", datetime(2027, 1, 15, 18, 0))
    return ida, vuelta


def test_ida_y_vuelta_dos_pasajeros(ida_vuelta):
    ida, vuelta = ida_vuelta
    r = (builder().para_titular(10).agregar_pasajero(10).agregar_pasajero(11)
         .agregar_tramo(ida, 2, ASIENTOS).agregar_tramo(vuelta, 2, ASIENTOS)
         .con_pago("Yape", "PEN").construir())
    assert len(r.boletos) == 4
    assert r.pasajeros == [10, 11] and r.vuelos == [1, 2]
    assert [b.asiento for b in r.boletos if b.id_vuelo == 1] == ["1A", "1B"]
    assert r.total_usd == 800
    assert r.pagos[0].moneda == "PEN" and r.pagos[0].monto == 3000
    assert len(r.codigo_pnr) == 6


def test_cada_pasajero_sube_la_ocupacion(hacer_vuelo):
    casi_lleno = hacer_vuelo(ocupados=171, capacidad=180)   # 95.0% -> 95.6%: cambia de tramo
    r = (builder(PrecioDinamico()).para_titular(1).agregar_pasajero(1).agregar_pasajero(2)
         .agregar_tramo(casi_lleno, 1, ASIENTOS).construir())
    assert r.boletos[1].precio > r.boletos[0].precio


@pytest.mark.parametrize("paso,mensaje", [
    (lambda b, v: b.agregar_pasajero(1).agregar_tramo(v, 1, ASIENTOS), "titular"),
    (lambda b, v: b.para_titular(1).agregar_tramo(v, 1, ASIENTOS), "pasajero"),
    (lambda b, v: b.para_titular(1).agregar_pasajero(1), "tramo"),
])
def test_faltan_partes(hacer_vuelo, paso, mensaje):
    b = builder()
    paso(b, hacer_vuelo())
    with pytest.raises(ErrorReserva, match=mensaje):
        b.construir()


def test_vuelo_no_programado(hacer_vuelo):
    b = builder().para_titular(1).agregar_pasajero(1).agregar_tramo(
        hacer_vuelo(estado="cancelado"), 1, ASIENTOS)
    with pytest.raises(ErrorReserva, match="cancelado"):
        b.construir()


def test_vuelo_ya_salio(hacer_vuelo):
    b = builder().para_titular(1).agregar_pasajero(1).agregar_tramo(
        hacer_vuelo(salida=COMPRA - timedelta(hours=1)), 1, ASIENTOS)
    with pytest.raises(ErrorReserva, match="ya salio"):
        b.construir()


def test_sin_cupo(hacer_vuelo):
    b = (builder().para_titular(1).agregar_pasajero(1).agregar_pasajero(2)
         .agregar_tramo(hacer_vuelo(capacidad=180, ocupados=179), 1, ASIENTOS))
    with pytest.raises(ErrorReserva, match="asientos libres"):
        b.construir()


def test_tramos_no_encadenados(hacer_vuelo):
    b = (builder().para_titular(1).agregar_pasajero(1)
         .agregar_tramo(hacer_vuelo(1, "LP1", "LIM", "CUZ"), 1, ASIENTOS)
         .agregar_tramo(hacer_vuelo(2, "LP2", "AQP", "LIM", datetime(2027, 1, 12)), 1, ASIENTOS))
    with pytest.raises(ErrorReserva, match="no encadenados"):
        b.construir()


def test_conexion_muy_corta(hacer_vuelo):
    ida = hacer_vuelo(1, "LP1", "LIM", "CUZ", datetime(2027, 1, 10, 8, 0), duracion=70)
    conexion = hacer_vuelo(2, "LP2", "CUZ", "AQP", datetime(2027, 1, 10, 9, 30))  # 20 min
    b = (builder().para_titular(1).agregar_pasajero(1)
         .agregar_tramo(ida, 1, ASIENTOS).agregar_tramo(conexion, 1, ASIENTOS))
    with pytest.raises(ErrorReserva, match="sale antes"):
        b.construir()


def test_pasajero_repetido_y_maximo():
    b = builder().agregar_pasajero(1)
    with pytest.raises(ErrorReserva, match="ya esta"):
        b.agregar_pasajero(1)
    for i in range(2, 10):
        b.agregar_pasajero(i)
    with pytest.raises(ErrorReserva, match="Maximo"):
        b.agregar_pasajero(99)


def test_canal_y_pago_invalidos():
    with pytest.raises(ErrorReserva):
        builder().por_canal("Fax")
    with pytest.raises(ErrorReserva):
        builder().con_pago("Bitcoin")
    with pytest.raises(ErrorReserva):
        builder().con_pago("Yape", "EUR")
