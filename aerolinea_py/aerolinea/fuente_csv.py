"""Fuente de datos alternativa: los 14 CSV del dataset en vez de MySQL.

Se usa cuando el dashboard corre donde no hay MySQL (por ejemplo,
publicado en Streamlit Community Cloud). Devuelve EXACTAMENTE las mismas
columnas que AnalisisRepository, con la misma logica que las vistas y
consultas SQL, asi el resto del sistema (analisis, indicadores,
dashboard) no cambia: es la ventaja del patron Repository.

Donde busca los CSV (el primero que tenga 05_vuelos.csv):
  1. la carpeta de la variable de entorno AEROLINEA_CSV
  2. la carpeta datos/ del proyecto
  3. C:/P6_aerolinea (donde se guardan los CSV para cargar MySQL)
  4. cualquier subcarpeta del repositorio que contiene al proyecto
"""
import os
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

from .config import RAIZ

CARGO_BODEGA = 35   # USD por maleta de bodega en tarifas sin equipaje


def buscar_carpeta_csv() -> Path | None:
    candidatas = []
    if os.getenv("AEROLINEA_CSV"):
        candidatas.append(Path(os.environ["AEROLINEA_CSV"]))
    candidatas.append(RAIZ / "datos")
    candidatas.append(Path("C:/P6_aerolinea"))      # carpeta del curso en Windows
    for c in candidatas:
        if (c / "05_vuelos.csv").exists():
            return c
    for base in (RAIZ, RAIZ.parent):
        for f in sorted(base.rglob("05_vuelos.csv")):
            if ".git" not in f.parts:
                return f.parent
    return None


class AnalisisCSV:
    """Misma interfaz que repositorios.AnalisisRepository."""

    def __init__(self, carpeta: str | Path | None = None):
        self.carpeta = Path(carpeta) if carpeta else buscar_carpeta_csv()
        if self.carpeta is None or not (self.carpeta / "05_vuelos.csv").exists():
            raise FileNotFoundError("No se encontraron los CSV del dataset (05_vuelos.csv)")

    def _leer(self, nombre: str, **kw) -> pd.DataFrame:
        return pd.read_csv(self.carpeta / f"{nombre}.csv", **kw)

    # --- tablas base (se leen una sola vez) ---------------------------------
    @cached_property
    def _vuelos_base(self) -> pd.DataFrame:
        ae = self._leer("01_aeropuertos").set_index("id_aeropuerto")
        ru = self._leer("02_rutas")
        cap = (self._leer("04_aviones").merge(self._leer("03_modelos_avion"), on="id_modelo")
               .set_index("id_avion")["capacidad"])
        v = self._leer("05_vuelos", parse_dates=["salida_prog", "salida_real"]).merge(ru, on="id_ruta")
        v["origen"] = v["id_origen"].map(ae["codigo_iata"])
        v["destino"] = v["id_destino"].map(ae["codigo_iata"])
        v["pais_origen"] = v["id_origen"].map(ae["pais"])
        v["pais_destino"] = v["id_destino"].map(ae["pais"])
        v["ruta"] = v["origen"] + "-" + v["destino"]
        v["capacidad"] = v["id_avion"].map(cap)
        # TIMESTAMPDIFF(MINUTE, ...) de MySQL: minutos enteros truncados
        seg = (v["salida_real"] - v["salida_prog"]).dt.total_seconds()
        v["retraso_min"] = np.trunc(seg / 60)
        return v

    @cached_property
    def _boletos(self) -> pd.DataFrame:
        return self._leer("12_boletos")

    @cached_property
    def _tarifas(self) -> pd.DataFrame:
        return self._leer("11_tarifas")

    # --- mismas consultas que AnalisisRepository ----------------------------
    def vuelos(self) -> pd.DataFrame:
        v, bo, ta = self._vuelos_base, self._boletos, self._tarifas
        b = bo.groupby("id_vuelo").agg(boletos=("id_boleto", "count"),
                                        ingresos_boletos=("precio", "sum"))
        eq = self._leer("13_equipajes")
        sin_equipaje = ta.loc[ta["equipaje_incluido"] == 0, ["id_tarifa"]]
        cargos = (bo.merge(sin_equipaje, on="id_tarifa")
                    .merge(eq[eq["tipo"] == "Bodega"], on="id_boleto")
                    .groupby("id_vuelo").size() * CARGO_BODEGA).rename("ingresos_equipaje")
        out = v.merge(b, on="id_vuelo", how="left").merge(cargos, on="id_vuelo", how="left")
        out[["boletos", "ingresos_boletos", "ingresos_equipaje"]] = (
            out[["boletos", "ingresos_boletos", "ingresos_equipaje"]].fillna(0))
        return out[["id_vuelo", "numero_vuelo", "salida_prog", "salida_real", "estado", "origen",
                    "destino", "ruta", "pais_origen", "pais_destino", "distancia_km", "capacidad",
                    "boletos", "ingresos_boletos", "ingresos_equipaje", "retraso_min"]]

    def ventas(self) -> pd.DataFrame:
        re = self._leer("10_reservas", parse_dates=["fecha_compra"])
        ta = self._tarifas.rename(columns={"nombre": "tarifa"})
        v = self._vuelos_base
        d = (self._boletos
             .merge(re[["id_reserva", "fecha_compra", "canal"]], on="id_reserva")
             .merge(v[["id_vuelo", "salida_prog", "estado", "id_ruta", "origen", "destino",
                       "capacidad"]], on="id_vuelo")
             .merge(ta[["id_tarifa", "clase", "tarifa"]], on="id_tarifa"))
        return d[["id_boleto", "id_vuelo", "id_tarifa", "clase", "tarifa", "precio", "fecha_compra",
                  "canal", "salida_prog", "estado", "id_ruta", "origen", "destino", "capacidad"]]

    def pasajeros_millas(self) -> pd.DataFrame:
        aterrizados = self._vuelos_base.loc[self._vuelos_base["estado"] == "aterrizado", ["id_vuelo"]]
        g = (self._boletos.merge(aterrizados, on="id_vuelo")
             .groupby("id_pasajero").agg(vuelos=("id_boleto", "count"), gasto_usd=("precio", "sum"))
             .reset_index())
        pa = self._leer("08_pasajeros", usecols=["id_pasajero", "nacionalidad"])
        cm = self._leer("09_cuentas_millas", usecols=["id_pasajero", "nivel", "millas"])
        g = g.merge(pa, on="id_pasajero", how="left").merge(cm, on="id_pasajero", how="left")
        return g[["id_pasajero", "nacionalidad", "nivel", "millas", "vuelos", "gasto_usd"]]

    def puntualidad(self) -> pd.DataFrame:
        v = self._vuelos_base
        p = v[(v["estado"] == "aterrizado") & v["salida_real"].notna()].copy()
        p["es_retrasado"] = (p["retraso_min"] >= 15).astype(int)
        return p[["id_vuelo", "numero_vuelo", "origen", "destino", "ruta", "salida_prog",
                  "salida_real", "retraso_min", "es_retrasado"]]

    def ocupacion(self) -> pd.DataFrame:
        v = self.vuelos()
        o = v[v["estado"] == "aterrizado"].copy()
        o["asientos_ocupados"] = o["boletos"]
        o["asientos_libres"] = o["capacidad"] - o["boletos"]
        o["factor_ocupacion_pct"] = (o["boletos"] / o["capacidad"] * 100).round(1)
        return o[["id_vuelo", "numero_vuelo", "origen", "destino", "ruta", "salida_prog", "estado",
                  "capacidad", "asientos_ocupados", "asientos_libres", "factor_ocupacion_pct"]]
