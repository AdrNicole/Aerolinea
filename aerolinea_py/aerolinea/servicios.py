"""Casos de uso: conectan los repositorios (datos) con los patrones
(logica). El menu de consola solo habla con estos servicios."""
from functools import lru_cache

from .config import CARPETA_SALIDAS
from .modelos import Reserva, Vuelo
from .patrones.estado_vuelo import VueloOperacion
from .patrones.observador import NotificadorPasajeros, PanelOperaciones, RegistroCSV
from .patrones.precio import CalculadoraPrecio, EstrategiaPrecio
from .patrones.reserva_builder import ReservaBuilder
from .repositorios import (PasajeroRepository, ReservaRepository,
                           TarifaRepository, VueloRepository)


class ServicioVuelos:
    def __init__(self, vuelos: VueloRepository | None = None):
        self.vuelos = vuelos or VueloRepository()

    def operar(self, id_vuelo: int, guardar_en_bd: bool = False,
               imprimir: bool = True):
        """Devuelve el vuelo listo para operarse (State) con sus
        observadores suscritos (Observer).
        guardar_en_bd=False -> simulacion: no modifica MySQL."""
        v = self.vuelos.obtener(id_vuelo)
        op = VueloOperacion(v.id_vuelo, v.numero_vuelo, v.salida_prog, v.estado,
                            v.salida_real,
                            persistencia=self.vuelos.actualizar_estado if guardar_en_bd else None)
        panel = PanelOperaciones(imprimir=imprimir)
        notificador = NotificadorPasajeros(self.vuelos.pasajeros_del_vuelo)
        op.suscribir(panel)
        op.suscribir(notificador)
        op.suscribir(RegistroCSV(CARPETA_SALIDAS / "eventos_vuelos.csv"))
        return op, panel, notificador


class ServicioReservas:
    def __init__(self, vuelos: VueloRepository | None = None,
                 tarifas: TarifaRepository | None = None,
                 reservas: ReservaRepository | None = None,
                 pasajeros: PasajeroRepository | None = None):
        self.vuelos = vuelos or VueloRepository()
        self.tarifas = tarifas or TarifaRepository()
        self.reservas = reservas or ReservaRepository()
        self.pasajeros = pasajeros or PasajeroRepository()

        @lru_cache(maxsize=256)
        def _base(id_ruta: int, id_tarifa: int) -> float:
            return self.tarifas.precio_base(id_ruta, id_tarifa)
        self._base_cache = _base

    def precio_base(self, vuelo: Vuelo, id_tarifa: int) -> float:
        return self._base_cache(vuelo.id_ruta, id_tarifa)

    def nuevo_builder(self, estrategia: EstrategiaPrecio | None = None,
                      fecha_compra=None) -> ReservaBuilder:
        return ReservaBuilder(CalculadoraPrecio(estrategia), self.precio_base, fecha_compra)

    def tramo(self, builder: ReservaBuilder, id_vuelo: int, id_tarifa: int) -> Vuelo:
        """Agrega un tramo al builder buscando el vuelo y sus asientos libres."""
        vuelo = self.vuelos.obtener(id_vuelo)
        builder.agregar_tramo(vuelo, id_tarifa, self.vuelos.asientos_libres(id_vuelo))
        return vuelo

    def guardar(self, reserva: Reserva) -> int:
        return self.reservas.guardar(reserva)
