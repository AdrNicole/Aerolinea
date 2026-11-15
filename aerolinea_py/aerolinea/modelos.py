"""Objetos del dominio. Son dataclasses simples: los repositorios los
construyen a partir de filas de MySQL y los patrones trabajan con ellos
sin saber nada de SQL."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd


@dataclass
class Pasajero:
    id_pasajero: int
    documento: str
    nombre: str
    nacionalidad: str


@dataclass
class Tarifa:
    id_tarifa: int
    clase: str
    nombre: str
    equipaje_incluido: bool
    reembolsable: bool


@dataclass
class Vuelo:
    id_vuelo: int
    numero_vuelo: str
    origen: str
    destino: str
    salida_prog: datetime
    estado: str
    capacidad: int
    asientos_ocupados: int
    duracion_min: int = 0
    salida_real: datetime | None = None
    id_ruta: int | None = None

    @property
    def asientos_libres(self) -> int:
        return self.capacidad - self.asientos_ocupados

    @property
    def ocupacion(self) -> float:
        """Factor de ocupacion entre 0 y 1."""
        return self.asientos_ocupados / self.capacidad if self.capacidad else 0.0

    @property
    def llegada_prog(self) -> datetime:
        return self.salida_prog + timedelta(minutes=int(self.duracion_min))

    def __str__(self) -> str:
        return (f"{self.numero_vuelo} {self.origen}->{self.destino} "
                f"{self.salida_prog:%d/%m/%Y %H:%M} ({self.estado}, "
                f"{self.asientos_libres} libres)")


@dataclass
class BoletoNuevo:
    id_pasajero: int
    id_vuelo: int
    numero_vuelo: str
    id_tarifa: int
    asiento: str
    precio: float


@dataclass
class Pago:
    monto: float
    moneda: str      # 'USD' o 'PEN'
    metodo: str


@dataclass
class Reserva:
    """Resultado del ReservaBuilder: una reserva lista para guardarse."""
    codigo_pnr: str
    id_titular: int
    canal: str
    fecha_compra: datetime
    boletos: list[BoletoNuevo] = field(default_factory=list)
    pagos: list[Pago] = field(default_factory=list)

    @property
    def total_usd(self) -> float:
        return round(sum(b.precio for b in self.boletos), 2)

    @property
    def pasajeros(self) -> list[int]:
        return sorted({b.id_pasajero for b in self.boletos})

    @property
    def vuelos(self) -> list[int]:
        return list(dict.fromkeys(b.id_vuelo for b in self.boletos))

    def resumen(self) -> pd.DataFrame:
        return pd.DataFrame([b.__dict__ for b in self.boletos])
