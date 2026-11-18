"""
reportes.py - Template Method: el esqueleto del reporte es fijo (generar) y
cada reporte concreto cambia los pasos obtener_datos y transformar.
"""
from abc import ABC, abstractmethod

from db_sqlalchemy import AsientoRepository, TarifaRepository, VueloRepository


class Reporte(ABC):
    def generar(self):
        datos = self.obtener_datos()
        return self.transformar(datos)

    @abstractmethod
    def obtener_datos(self): ...

    @abstractmethod
    def transformar(self, datos): ...


class ReporteVuelo(Reporte):
    """Consulta 4 (informacion) + 6a (ocupacion) + 5 (tarifas), unidas con merge."""

    def __init__(self, id_vuelo):
        self.id_vuelo = int(id_vuelo)

    def obtener_datos(self):
        return {
            "info": VueloRepository().informacion_vuelo(self.id_vuelo),
            "ocupacion": AsientoRepository().ocupacion(self.id_vuelo),
            "tarifas": TarifaRepository().por_vuelo(self.id_vuelo),
        }

    def transformar(self, datos):
        ocup = datos["ocupacion"][["id_vuelo", "asientos_ocupados",
                                   "asientos_disponibles", "ocupacion_pct"]]
        tarifas = datos["tarifas"].assign(id_vuelo=self.id_vuelo)
        return (datos["info"]
                .merge(ocup, on="id_vuelo", how="left")       # 4 + 6a (una fila)
                .merge(tarifas, on="id_vuelo", how="left"))   # + 5 (una fila por tarifa)
