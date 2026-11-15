"""Patron BUILDER: armar una reserva con varios tramos y pasajeros.

Una reserva tiene muchas partes (titular, pasajeros, tramos, tarifa por
tramo, asientos, precios, pago) y reglas que dependen de todas a la vez.
El builder deja agregarlas paso a paso, en cualquier orden, y valida y
calcula todo junto en construir():

    reserva = (ReservaBuilder(calculadora, precio_base)
               .para_titular(58162)
               .agregar_pasajero(58162).agregar_pasajero(1805)
               .agregar_tramo(vuelo_ida, id_tarifa=3, asientos_libres=[...])
               .agregar_tramo(vuelo_vuelta, id_tarifa=3, asientos_libres=[...])
               .con_pago("Tarjeta de crédito", "USD")
               .construir())

Reglas que valida:
  - titular definido; entre 1 y 9 pasajeros, sin repetir;
  - al menos un tramo; cada vuelo 'programado' y con cupo suficiente;
  - la compra es anterior a la salida de cada vuelo;
  - tramos encadenados: cada tramo sale de donde llego el anterior
    (conexion o vuelta) y al menos CONEXION_MINIMA despues de su llegada.
El precio de cada boleto lo calcula la estrategia de precio (Strategy):
cada pasajero adicional sube la ocupacion del vuelo antes de cotizar.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from ..modelos import BoletoNuevo, Pago, Reserva, Vuelo
from ..repositorios import generar_pnr
from .precio import CalculadoraPrecio, ContextoPrecio

CONEXION_MINIMA = timedelta(minutes=45)
MAX_PASAJEROS = 9
TIPO_CAMBIO_PEN = 3.75
CANALES = ("Web", "App", "Agencia", "Call center", "Aeropuerto")
METODOS_PAGO = ("Tarjeta de crédito", "Tarjeta de débito", "Millas + dinero",
                "Yape", "PagoEfectivo", "Transferencia")


class ErrorReserva(Exception):
    pass


@dataclass
class _Tramo:
    vuelo: Vuelo
    id_tarifa: int
    asientos_libres: list[str]


class ReservaBuilder:

    def __init__(self, calculadora: CalculadoraPrecio,
                 precio_base: Callable[[Vuelo, int], float],
                 fecha_compra: datetime | None = None):
        """precio_base(vuelo, id_tarifa) -> precio de referencia
        (en la app: TarifaRepository.precio_base)."""
        self._calculadora = calculadora
        self._precio_base = precio_base
        self._fecha_compra = fecha_compra or datetime.now()
        self._titular: int | None = None
        self._canal = "Web"
        self._pasajeros: list[int] = []
        self._tramos: list[_Tramo] = []
        self._pago: tuple[str, str] | None = None

    # --- pasos -----------------------------------------------------------
    def para_titular(self, id_pasajero: int) -> "ReservaBuilder":
        self._titular = id_pasajero
        return self

    def por_canal(self, canal: str) -> "ReservaBuilder":
        if canal not in CANALES:
            raise ErrorReserva(f"Canal invalido: {canal}. Use uno de {CANALES}")
        self._canal = canal
        return self

    def agregar_pasajero(self, id_pasajero: int) -> "ReservaBuilder":
        if id_pasajero in self._pasajeros:
            raise ErrorReserva(f"El pasajero {id_pasajero} ya esta en la reserva")
        if len(self._pasajeros) >= MAX_PASAJEROS:
            raise ErrorReserva(f"Maximo {MAX_PASAJEROS} pasajeros por reserva")
        self._pasajeros.append(id_pasajero)
        return self

    def agregar_tramo(self, vuelo: Vuelo, id_tarifa: int,
                      asientos_libres: list[str]) -> "ReservaBuilder":
        self._tramos.append(_Tramo(vuelo, id_tarifa, list(asientos_libres)))
        return self

    def con_pago(self, metodo: str, moneda: str = "USD") -> "ReservaBuilder":
        if moneda not in ("USD", "PEN"):
            raise ErrorReserva("La moneda debe ser USD o PEN")
        if metodo not in METODOS_PAGO:
            raise ErrorReserva(f"Metodo de pago invalido: {metodo}. Use uno de {METODOS_PAGO}")
        self._pago = (metodo, moneda)
        return self

    # --- validacion y armado --------------------------------------------
    def _validar(self):
        if self._titular is None:
            raise ErrorReserva("Falta el titular de la reserva")
        if not self._pasajeros:
            raise ErrorReserva("Agrega al menos un pasajero")
        if not self._tramos:
            raise ErrorReserva("Agrega al menos un tramo")
        n = len(self._pasajeros)
        for t in self._tramos:
            v = t.vuelo
            if v.estado != "programado":
                raise ErrorReserva(f"El vuelo {v.numero_vuelo} esta '{v.estado}': no se vende")
            if v.salida_prog <= self._fecha_compra:
                raise ErrorReserva(f"El vuelo {v.numero_vuelo} ya salio")
            if v.asientos_libres < n or len(t.asientos_libres) < n:
                raise ErrorReserva(f"El vuelo {v.numero_vuelo} no tiene {n} asientos libres")
        for previo, sig in zip(self._tramos, self._tramos[1:]):
            if sig.vuelo.origen != previo.vuelo.destino:
                raise ErrorReserva(
                    f"Tramos no encadenados: {previo.vuelo.numero_vuelo} llega a "
                    f"{previo.vuelo.destino} y {sig.vuelo.numero_vuelo} sale de {sig.vuelo.origen}")
            if sig.vuelo.salida_prog < previo.vuelo.llegada_prog + CONEXION_MINIMA:
                raise ErrorReserva(
                    f"{sig.vuelo.numero_vuelo} sale antes de {CONEXION_MINIMA} "
                    f"de la llegada de {previo.vuelo.numero_vuelo}")

    def construir(self) -> Reserva:
        self._validar()
        reserva = Reserva(codigo_pnr=generar_pnr(), id_titular=self._titular,
                          canal=self._canal, fecha_compra=self._fecha_compra)
        for t in self._tramos:
            v = t.vuelo
            base = self._precio_base(v, t.id_tarifa)
            dias = (v.salida_prog - self._fecha_compra).days
            for i, id_pas in enumerate(self._pasajeros):
                ocupacion = min((v.asientos_ocupados + i) / v.capacidad, 1.0)
                precio = self._calculadora.cotizar(
                    ContextoPrecio(base, dias, ocupacion, v.salida_prog))
                reserva.boletos.append(BoletoNuevo(id_pas, v.id_vuelo, v.numero_vuelo,
                                                   t.id_tarifa, t.asientos_libres[i], precio))
        if self._pago:
            metodo, moneda = self._pago
            monto = reserva.total_usd * (TIPO_CAMBIO_PEN if moneda == "PEN" else 1)
            reserva.pagos.append(Pago(round(monto, 2), moneda, metodo))
        return reserva
