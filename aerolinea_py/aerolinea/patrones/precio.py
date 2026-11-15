"""Patron STRATEGY: precio dinamico.

La CalculadoraPrecio no sabe como se calcula el precio; delega en una
estrategia intercambiable en tiempo de ejecucion:
    PrecioFijo             -> precio base (sin ajustes)
    PrecioPorAnticipacion  -> sube cuanto menos dias faltan
    PrecioPorOcupacion     -> sube cuanto mas lleno esta el vuelo
    PrecioDinamico         -> anticipacion x ocupacion x temporada

Los factores NO son inventados: salen de calibrar un modelo
multiplicativo log(precio/mediana de ruta y tarifa) con los 487 mil
boletos historicos (ver analisis.calibrar_factores_precio). Referencia
(factor 1.0): compra con 61-120 dias, vuelo con menos del 50% vendido,
temporada normal.
"""
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

# (limite superior del tramo, factor). Calibrados con los datos.
FACTORES_ANTICIPACION = [(3, 2.46), (7, 1.89), (14, 1.49), (30, 1.21),
                         (60, 1.08), (120, 1.00), (math.inf, 0.95)]
FACTORES_OCUPACION = [(0.50, 1.00), (0.70, 1.12), (0.85, 1.26),
                      (0.95, 1.40), (math.inf, 1.61)]
FACTOR_TEMPORADA_ALTA = 1.17
MESES_TEMPORADA_ALTA = {7, 12}


def factor_de_tabla(tabla, valor) -> float:
    """Devuelve el factor del primer tramo cuyo limite >= valor."""
    for limite, factor in tabla:
        if valor <= limite:
            return factor
    return tabla[-1][1]


@dataclass
class ContextoPrecio:
    precio_base: float          # precio de referencia de la tarifa en la ruta
    dias_anticipacion: int      # dias entre la compra y el vuelo
    ocupacion: float            # 0 a 1, al momento de comprar
    fecha_vuelo: datetime

    def __post_init__(self):
        if self.precio_base <= 0:
            raise ValueError("El precio base debe ser positivo")
        if self.dias_anticipacion < 0:
            raise ValueError("No se puede comprar despues de la salida del vuelo")
        if not 0 <= self.ocupacion <= 1:
            raise ValueError("La ocupacion debe estar entre 0 y 1")


class EstrategiaPrecio(ABC):
    nombre = ""

    @abstractmethod
    def calcular(self, ctx: ContextoPrecio) -> float: ...


class PrecioFijo(EstrategiaPrecio):
    nombre = "Fijo"

    def calcular(self, ctx):
        return ctx.precio_base


class PrecioPorAnticipacion(EstrategiaPrecio):
    nombre = "Por anticipacion"

    def __init__(self, tabla=FACTORES_ANTICIPACION):
        self.tabla = tabla

    def calcular(self, ctx):
        return ctx.precio_base * factor_de_tabla(self.tabla, ctx.dias_anticipacion)


class PrecioPorOcupacion(EstrategiaPrecio):
    nombre = "Por ocupacion"

    def __init__(self, tabla=FACTORES_OCUPACION):
        self.tabla = tabla

    def calcular(self, ctx):
        return ctx.precio_base * factor_de_tabla(self.tabla, ctx.ocupacion)


class PrecioDinamico(EstrategiaPrecio):
    """Combina los tres efectos medidos en los datos."""
    nombre = "Dinamico"

    def __init__(self, tabla_anticipacion=FACTORES_ANTICIPACION,
                 tabla_ocupacion=FACTORES_OCUPACION,
                 factor_temporada=FACTOR_TEMPORADA_ALTA,
                 meses_alta=MESES_TEMPORADA_ALTA):
        self.tabla_anticipacion = tabla_anticipacion
        self.tabla_ocupacion = tabla_ocupacion
        self.factor_temporada = factor_temporada
        self.meses_alta = meses_alta

    def factores(self, ctx) -> dict:
        return {
            "anticipacion": factor_de_tabla(self.tabla_anticipacion, ctx.dias_anticipacion),
            "ocupacion": factor_de_tabla(self.tabla_ocupacion, ctx.ocupacion),
            "temporada": self.factor_temporada if ctx.fecha_vuelo.month in self.meses_alta else 1.0,
        }

    def calcular(self, ctx):
        f = self.factores(ctx)
        return ctx.precio_base * f["anticipacion"] * f["ocupacion"] * f["temporada"]

    @classmethod
    def desde_calibracion(cls, calibracion: dict) -> "PrecioDinamico":
        """Crea la estrategia con los factores que devuelve
        analisis.calibrar_factores_precio (recalibrar con datos nuevos)."""
        return cls(calibracion["anticipacion"], calibracion["ocupacion"],
                   calibracion["temporada_alta"])


class CalculadoraPrecio:
    """Contexto del patron Strategy."""

    def __init__(self, estrategia: EstrategiaPrecio | None = None):
        self.estrategia = estrategia or PrecioDinamico()

    def cambiar_estrategia(self, estrategia: EstrategiaPrecio) -> None:
        self.estrategia = estrategia

    def cotizar(self, ctx: ContextoPrecio) -> float:
        return round(self.estrategia.calcular(ctx), 2)
