"""Patron OBSERVER: avisar retrasos y cancelaciones.

El vuelo (sujeto) no sabe a quien hay que avisar ni como. Solo publica
eventos; cada observador decide que hacer:
    - NotificadorPasajeros: arma un aviso por pasajero afectado.
    - PanelOperaciones: muestra todos los eventos (centro de control).
    - RegistroCSV: deja constancia en un archivo.
Agregar un canal nuevo (SMS, correo) es crear otra clase Observador,
sin tocar el codigo del vuelo.
"""
import csv
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

UMBRAL_RETRASO_MIN = 15   # criterio de la industria: retrasado si sale 15+ min tarde


@dataclass(frozen=True)
class EventoVuelo:
    tipo: str                 # 'CAMBIO_ESTADO' | 'RETRASO' | 'CANCELACION'
    id_vuelo: int
    numero_vuelo: str
    mensaje: str
    estado: str = ""
    minutos: int = 0
    momento: datetime = field(default_factory=datetime.now)


class Observador(ABC):
    @abstractmethod
    def actualizar(self, evento: EventoVuelo) -> None: ...


class Sujeto:
    """Lo hereda el vuelo (VueloOperacion)."""

    def __init__(self):
        self._observadores: list[Observador] = []

    def suscribir(self, obs: Observador) -> None:
        if obs not in self._observadores:
            self._observadores.append(obs)

    def desuscribir(self, obs: Observador) -> None:
        self._observadores.remove(obs)

    def notificar(self, evento: EventoVuelo) -> None:
        for obs in list(self._observadores):
            obs.actualizar(evento)


# ----------------------------------------------------------------------
class NotificadorPasajeros(Observador):
    """Avisa a cada pasajero del vuelo cuando hay un retraso
    significativo (>= umbral) o una cancelacion.

    proveedor_pasajeros(id_vuelo) -> DataFrame con columnas
    'nombre' y 'codigo_pnr' (en la app: VueloRepository.pasajeros_del_vuelo).
    """

    def __init__(self, proveedor_pasajeros: Callable[[int], pd.DataFrame],
                 umbral_min: int = UMBRAL_RETRASO_MIN):
        self.proveedor = proveedor_pasajeros
        self.umbral = umbral_min
        self.mensajes: list[str] = []

    def actualizar(self, evento: EventoVuelo) -> None:
        if evento.tipo == "RETRASO" and evento.minutos < self.umbral:
            return
        if evento.tipo not in ("RETRASO", "CANCELACION"):
            return
        pasajeros = self.proveedor(evento.id_vuelo)
        for p in pasajeros.itertuples():
            if evento.tipo == "CANCELACION":
                texto = (f"Estimado(a) {p.nombre}: el vuelo {evento.numero_vuelo} "
                         f"(reserva {p.codigo_pnr}) fue CANCELADO. {evento.mensaje}")
            else:
                texto = (f"Estimado(a) {p.nombre}: el vuelo {evento.numero_vuelo} "
                         f"(reserva {p.codigo_pnr}) sale con {evento.minutos} min de retraso.")
            self.mensajes.append(texto)


class PanelOperaciones(Observador):
    """Registra y (opcionalmente) imprime todos los eventos."""

    def __init__(self, imprimir: bool = True):
        self.imprimir = imprimir
        self.eventos: list[EventoVuelo] = []

    def actualizar(self, evento: EventoVuelo) -> None:
        self.eventos.append(evento)
        if self.imprimir:
            print(f"  [PANEL {evento.momento:%H:%M:%S}] {evento.tipo:<13} "
                  f"{evento.numero_vuelo}: {evento.mensaje}")


class RegistroCSV(Observador):
    """Agrega cada evento como una fila de un archivo CSV."""

    def __init__(self, ruta: str | Path):
        self.ruta = Path(ruta)

    def actualizar(self, evento: EventoVuelo) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        nuevo = not self.ruta.exists()
        with self.ruta.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(asdict(evento)))
            if nuevo:
                w.writeheader()
            w.writerow(asdict(evento))
