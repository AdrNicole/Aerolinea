"""Cotización ilustrativa PEN/USD para seis tarifas.

La app solo presenta información; no crea boletos ni pagos.
El tipo de cambio se configura explícitamente. El IPC usado es la última
observación disponible ANTERIOR O IGUAL al mes de cotización, nunca el IPC
futuro del mes de salida.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import csv
from decimal import Decimal, ROUND_HALF_UP

from precio_strategy import Cotizador, PrecioDinamicoStrategy, DatosCotizacion

BASE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ReferenciaMonetaria:
    periodo_ipc: str
    valor_ipc: float
    tc_pen_por_usd: float
    tc_tipo: str = "Simulación"


def ultimo_ipc_disponible(ahora: datetime, ruta: Path | None = None) -> tuple[str, float]:
    ruta = ruta or BASE / "ipc_usa_bls_nsa.csv"
    mes_cotizacion = ahora.strftime("%Y-%m")
    valores = []
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        for fila in csv.DictReader(f):
            mes = fila["periodo"].strip()
            if mes <= mes_cotizacion and fila["ipc"].strip():
                valores.append((mes, float(fila["ipc"])))
    if not valores:
        raise ValueError("No existe un IPC disponible para la fecha de cotización")
    return max(valores, key=lambda t: t[0])


def redondeo_dinero(valor: float) -> str:
    return str(Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class ServicioPrecios:
    def __init__(self, ruta_modelo: Path | None = None):
        self.cotizador = Cotizador(
            ruta_modelo or BASE / "parametros_strategy_por_tarifa.json",
            PrecioDinamicoStrategy(),
        )

    def cotizar_tarifas(self, info_vuelo: dict, tarifas: list[dict],
                        ocupados: int, instante: datetime,
                        cambio: float) -> list[dict]:
        if not 2 <= cambio <= 6:
            raise ValueError("El tipo de cambio de simulación debe estar entre 2 y 6 PEN/USD")
        periodo, ipc = ultimo_ipc_disponible(instante)
        salida = info_vuelo["salida_prog"]
        if hasattr(salida, "to_pydatetime"):
            salida = salida.to_pydatetime()
        salida = datetime.fromisoformat(salida) if isinstance(salida, str) else salida
        resultados = []
        for t in tarifas:
            precio = self.cotizador.cotizar(DatosCotizacion(
                id_ruta=int(info_vuelo["id_ruta"]),
                id_tarifa=int(t["id_tarifa"]),
                fecha_salida=salida,
                fecha_cotizacion=instante,
                capacidad=int(info_vuelo["capacidad"]),
                asientos_ocupados=int(ocupados),
                ipc_us_cotizacion=ipc,
                tipo_cambio_pen_usd=cambio,
            ))
            # Convertir a PEN a partir de USD publicado a dos decimales,
            # para que precio unitario y total sean internamente consistentes.
            precio["precio_pen"] = redondeo_dinero(
                Decimal(precio["precio_usd"]) * Decimal(str(cambio))
            )
            resultados.append({**t, **precio, "ipc_periodo": periodo,
                               "ipc_valor": ipc, "tipo_cambio": cambio})
        return resultados


def total_en_moneda(usd: str, cantidad: int, cambio: float) -> tuple[str, str]:
    if not 1 <= cantidad <= 9:
        raise ValueError("Los pasajeros deben estar entre 1 y 9")
    usd_unitario = Decimal(usd)
    pen_unitario = Decimal(redondeo_dinero(usd_unitario * Decimal(str(cambio))))
    return (redondeo_dinero(usd_unitario * cantidad),
            redondeo_dinero(pen_unitario * cantidad))


def formato_importe(valor: str, moneda: str) -> str:
    return f"{'USD' if moneda == 'USD' else 'S/'} {Decimal(valor):,.2f}"
