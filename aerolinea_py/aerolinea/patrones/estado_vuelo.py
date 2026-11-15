"""Patron STATE: ciclo de vida de un vuelo.

    programado -> embarcando -> en vuelo -> aterrizado
    programado / embarcando  -> cancelado

Cada estado es una clase que sabe que acciones permite. El vuelo
(contexto) delega en su estado actual, asi no hay cadenas de if/elif
sobre un texto: una accion invalida (p. ej. aterrizar un vuelo
programado) la rechaza el propio estado.
La misma regla esta en la base de datos (trigger
trg_vuelos_transicion_estado): Python valida antes de llamar a MySQL y
MySQL protege los datos aunque alguien actualice por fuera.

VueloOperacion tambien es el SUJETO del patron Observer: publica un
evento en cada cambio de estado, retraso o cancelacion.
"""
from abc import ABC
from datetime import datetime
from typing import Callable

from .observador import UMBRAL_RETRASO_MIN, EventoVuelo, Sujeto


class TransicionInvalida(Exception):
    pass


class EstadoVuelo(ABC):
    nombre = ""
    final = False
    permite_venta = False

    def _rechazar(self, accion: str):
        raise TransicionInvalida(f"No se puede {accion} un vuelo en estado '{self.nombre}'")

    def iniciar_embarque(self, vuelo: "VueloOperacion"):
        self._rechazar("iniciar el embarque de")

    def despegar(self, vuelo: "VueloOperacion", hora: datetime):
        self._rechazar("despegar")

    def aterrizar(self, vuelo: "VueloOperacion"):
        self._rechazar("aterrizar")

    def cancelar(self, vuelo: "VueloOperacion", motivo: str):
        self._rechazar("cancelar")

    def anunciar_retraso(self, vuelo: "VueloOperacion", minutos: int):
        self._rechazar("anunciar un retraso de")

    def __str__(self):
        return self.nombre


class Programado(EstadoVuelo):
    nombre = "programado"
    permite_venta = True

    def iniciar_embarque(self, vuelo):
        vuelo._cambiar_estado(Embarcando())

    def cancelar(self, vuelo, motivo):
        vuelo._cancelar(motivo)

    def anunciar_retraso(self, vuelo, minutos):
        vuelo._avisar_retraso(minutos, "Retraso anunciado antes del embarque")


class Embarcando(EstadoVuelo):
    nombre = "embarcando"

    def despegar(self, vuelo, hora):
        vuelo._cambiar_estado(EnVuelo(), salida_real=hora)
        retraso = vuelo.retraso_min
        if retraso is not None and retraso >= UMBRAL_RETRASO_MIN:
            vuelo._avisar_retraso(retraso, "Salida con retraso")

    def cancelar(self, vuelo, motivo):
        vuelo._cancelar(motivo)

    def anunciar_retraso(self, vuelo, minutos):
        vuelo._avisar_retraso(minutos, "Retraso anunciado durante el embarque")


class EnVuelo(EstadoVuelo):
    nombre = "en vuelo"

    def aterrizar(self, vuelo):
        vuelo._cambiar_estado(Aterrizado())


class Aterrizado(EstadoVuelo):
    nombre = "aterrizado"
    final = True


class Cancelado(EstadoVuelo):
    nombre = "cancelado"
    final = True


ESTADOS = {c.nombre: c for c in (Programado, Embarcando, EnVuelo, Aterrizado, Cancelado)}


# ----------------------------------------------------------------------
class VueloOperacion(Sujeto):
    """Contexto del patron State.

    persistencia: funcion opcional (id_vuelo, estado, salida_real) que
    guarda el cambio, p. ej. VueloRepository.actualizar_estado. Si es
    None, el vuelo se opera solo en memoria (simulacion).
    """

    def __init__(self, id_vuelo: int, numero_vuelo: str, salida_prog: datetime,
                 estado: str = "programado", salida_real: datetime | None = None,
                 persistencia: Callable | None = None):
        super().__init__()
        if estado not in ESTADOS:
            raise ValueError(f"Estado desconocido: {estado}")
        self.id_vuelo = id_vuelo
        self.numero_vuelo = numero_vuelo
        self.salida_prog = salida_prog
        self.salida_real = salida_real
        self._estado: EstadoVuelo = ESTADOS[estado]()
        self._persistencia = persistencia
        self.historial: list[str] = [estado]

    # --- consulta ---------------------------------------------------------
    @property
    def estado(self) -> str:
        return self._estado.nombre

    @property
    def permite_venta(self) -> bool:
        return self._estado.permite_venta

    @property
    def retraso_min(self) -> int | None:
        if self.salida_real is None:
            return None
        return int((self.salida_real - self.salida_prog).total_seconds() // 60)

    # --- acciones: se delegan al estado actual -----------------------------
    def iniciar_embarque(self):
        self._estado.iniciar_embarque(self)

    def despegar(self, hora: datetime | None = None):
        self._estado.despegar(self, hora or datetime.now())

    def aterrizar(self):
        self._estado.aterrizar(self)

    def cancelar(self, motivo: str = ""):
        self._estado.cancelar(self, motivo)

    def anunciar_retraso(self, minutos: int):
        self._estado.anunciar_retraso(self, minutos)

    # --- usados por los estados --------------------------------------------
    def _cambiar_estado(self, nuevo: EstadoVuelo, salida_real: datetime | None = None):
        if self._persistencia is not None:      # primero la BD: si falla, no cambia nada
            self._persistencia(self.id_vuelo, nuevo.nombre, salida_real)
        anterior = self._estado.nombre
        if salida_real is not None:
            self.salida_real = salida_real
        self._estado = nuevo
        self.historial.append(nuevo.nombre)
        self.notificar(EventoVuelo("CAMBIO_ESTADO", self.id_vuelo, self.numero_vuelo,
                                   f"{anterior} -> {nuevo.nombre}", estado=nuevo.nombre))

    def _cancelar(self, motivo: str):
        self._cambiar_estado(Cancelado())
        self.notificar(EventoVuelo("CANCELACION", self.id_vuelo, self.numero_vuelo,
                                   motivo or "Vuelo cancelado", estado=self.estado))

    def _avisar_retraso(self, minutos: int, detalle: str):
        self.notificar(EventoVuelo("RETRASO", self.id_vuelo, self.numero_vuelo,
                                   f"{detalle}: {minutos} min", estado=self.estado,
                                   minutos=int(minutos)))

    def __str__(self):
        return f"{self.numero_vuelo} [{self.estado}]"
