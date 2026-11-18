"""Strategy para tarifas aéreas: historico fijo y dinámico por anticipación/ocupación.

Solo patrón Strategy. No incorpora EMSR-b ni un optimizador de ingresos.
Los factores por tarifa proceden de calibración histórica 2024-2025.
La inflación se aplica igual a ambas estrategias; su IPC debe informarse.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import json
import math

DIAS = ('0–1 días','1–3 días','3–7 días','7–14 días',
        '14–30 días','30–60 días','60–90 días','90+ días')
OCUPACION = ('0–20 %','20–40 %','40–60 %','60–80 %','80–100 %')


def redondear(valor):
    return str(Decimal(str(valor)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class DatosCotizacion:
    id_ruta: int
    id_tarifa: int
    fecha_salida: datetime
    fecha_cotizacion: datetime
    capacidad: int
    asientos_ocupados: int
    ipc_us_cotizacion: float
    tipo_cambio_pen_usd: float


class EstrategiaPrecio(ABC):
    @abstractmethod
    def multiplicador(self, id_tarifa: int, dias: float, ocupacion: float, modelo: dict) -> float:
        """Factor respecto al precio base histórico ajustado por inflación."""


class PrecioHistoricoFijo(EstrategiaPrecio):
    def multiplicador(self, id_tarifa, dias, ocupacion, modelo):
        return 1.0


class PrecioDinamicoStrategy(EstrategiaPrecio):
    """Multiplicadores por tarifa y por dos variables exigidas en la rúbrica."""
    def multiplicador(self, id_tarifa, dias, ocupacion, modelo):
        coef = modelo['estrategia_tarifa'].get(str(id_tarifa))
        if coef is None:
            raise KeyError(f'Tarifa {id_tarifa} sin calibración')
        limites_dias = (1,3,7,14,30,60,90)
        limites_ocup = (.2,.4,.6,.8)
        idx_dias = next((i for i, v in enumerate(limites_dias) if dias <= v), 7)
        idx_ocup = next((i for i, v in enumerate(limites_ocup) if ocupacion <= v), 4)
        return math.exp(coef['intercept_log']
                        +coef['factor_log_anticipacion'][DIAS[idx_dias]]
                        +coef['factor_log_ocupacion'][OCUPACION[idx_ocup]])


class Cotizador:
    """Contexto Strategy: la aplicación cambia la estrategia sin cambiar SQL."""
    def __init__(self, ruta_modelo: str | Path, estrategia: EstrategiaPrecio):
        self.modelo=json.loads(Path(ruta_modelo).read_text(encoding='utf-8'))
        self.precios={(int(row['id_ruta']),int(row['id_tarifa'])):float(row['precio_base'])
                      for row in self.modelo['base_usd_constantes_diciembre_2025']}
        self.estrategia=estrategia

    def cotizar(self, datos: DatosCotizacion) -> dict:
        if datos.capacidad<=0 or not 0<=datos.asientos_ocupados<=datos.capacidad:
            raise ValueError('Capacidad/ocupación no válida')
        if datos.fecha_salida<=datos.fecha_cotizacion:
            raise ValueError('No se cotizan vuelos ya iniciados')
        if datos.ipc_us_cotizacion<=0 or datos.tipo_cambio_pen_usd<=0:
            raise ValueError('IPC y tipo de cambio deben ser positivos')
        key=(int(datos.id_ruta),int(datos.id_tarifa))
        if key not in self.precios:
            raise KeyError(f'No hay precio base para ruta/tarifa {key}')
        dias=(datos.fecha_salida-datos.fecha_cotizacion).total_seconds()/86400
        ocup=datos.asientos_ocupados/datos.capacidad
        base=self.precios[key] * datos.ipc_us_cotizacion/self.modelo['ipc_base_diciembre_2025']
        multip=self.estrategia.multiplicador(datos.id_tarifa,dias,ocup,self.modelo)
        usd=base*multip
        return {'precio_usd':redondear(usd),
                'precio_pen':redondear(usd*datos.tipo_cambio_pen_usd),
                'precio_base_usd':redondear(base),
                'multiplicador':round(multip,4),
                'dias_anticipacion':round(dias,2),
                'ocupacion_pct':round(100*ocup,2),
                'importe_estimado':True}
