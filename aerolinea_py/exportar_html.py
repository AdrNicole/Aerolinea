"""Exporta el dashboard a UN solo archivo HTML (salidas/dashboard.html).

Uso:  python exportar_html.py
El archivo se abre con doble clic en Chrome/Edge: no necesita Python,
MySQL ni Streamlit. Los datos van dentro del archivo (agregados por vuelo)
y los filtros, graficos y el mapa se calculan en el navegador con las
mismas definiciones de aerolinea/indicadores.py.
Solo el fondo del mapa (calles/paises de CARTO) se descarga de internet.

Fuente: MySQL si hay .env (como main.py); si no, los CSV del dataset.
"""
import json
import os
from datetime import datetime

import pandas as pd

from aerolinea import analisis as A
from aerolinea import indicadores as I
from aerolinea.config import CARPETA_SALIDAS, FECHA_CORTE, RAIZ
from aerolinea.geo import CIUDADES, COORDENADAS, pais
from aerolinea.patrones.reserva_builder import TIPO_CAMBIO_PEN

PLANTILLA = RAIZ / "aerolinea" / "plantilla_dashboard.html"
DESTINO = CARPETA_SALIDAS / "dashboard.html"
DIMENSIONES = {"clase": "clase", "canal": "canal", "tarifa": "tarifa", "tramo": "tramo_anticipacion"}


def elegir_repositorio():
    if os.getenv("AEROLINEA_DB_CLAVE") is not None:
        try:
            from aerolinea.repositorios import AnalisisRepository
            repo = AnalisisRepository()
            repo.cn.consultar("SELECT 1")
            return repo, "MySQL"
        except Exception as e:
            print(f"No se pudo conectar a MySQL ({getattr(e, 'orig', e)}); se usan los CSV.")
    from aerolinea.fuente_csv import AnalisisCSV
    return AnalisisCSV(), "archivos CSV"


def construir_datos() -> dict:
    repo, fuente = elegir_repositorio()
    todos = I.preparar_vuelos(repo.vuelos())
    hist = I.historico(todos).sort_values("salida_prog").reset_index(drop=True)

    rutas = (hist[["ruta", "origen", "destino", "mercado"]].drop_duplicates("ruta")
             .sort_values("ruta").reset_index(drop=True))
    idx_ruta = {r: i for i, r in enumerate(rutas["ruta"])}
    idx_vuelo = {v: i for i, v in enumerate(hist["id_vuelo"])}

    # Tabla de vuelos en columnas (mas compacto que una lista de objetos)
    v = {
        "t": hist["salida_prog"].dt.strftime("%Y-%m-%d %H:%M").tolist(),
        "r": [idx_ruta[x] for x in hist["ruta"]],
        "e": hist["cancelado"].astype(int).tolist(),            # 0 aterrizado, 1 cancelado
        "b": hist["boletos"].astype(int).tolist(),
        "c": hist["capacidad"].astype(int).tolist(),
        "ib": hist["ingresos_boletos"].round(2).tolist(),
        "ie": hist["ingresos_equipaje"].astype(float).round(2).tolist(),
        "rt": [None if pd.isna(x) or c else round(float(x), 1)
               for x, c in zip(hist["retraso_min"], hist["cancelado"])],
    }

    # Ventas de vuelos aterrizados, agregadas por vuelo y por categoria
    ventas = A.preparar_ventas(repo.ventas())
    aterrizados = set(hist.loc[hist["aterrizado"], "id_vuelo"])
    ventas = ventas[ventas["id_vuelo"].isin(aterrizados)]
    dims, filas = {}, []
    for d, (nombre, columna) in enumerate(DIMENSIONES.items()):
        valores = (A.ETIQUETAS_ANTICIPACION if nombre == "tramo"
                   else sorted(ventas[columna].dropna().astype(str).unique()))
        dims[nombre] = valores
        pos = {x: k for k, x in enumerate(valores)}
        g = (ventas.assign(_v=ventas[columna].astype(str))
             .groupby(["id_vuelo", "_v"], observed=True)["precio"].agg(["count", "sum"]).reset_index())
        for idv, val, n, s in g.itertuples(index=False):
            if val in pos:
                filas += [idx_vuelo[idv], d, pos[val], int(n), int(round(s * 100))]

    pax = repo.pasajeros_millas()
    niv = A.pasajeros_por_nivel(pax).reset_index()
    nac = pax.groupby("nacionalidad")["gasto_usd"].sum().sort_values(ascending=False).head(8)
    usados = sorted(set(rutas["origen"]) | set(rutas["destino"]))

    return {
        "generado": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "fuente": fuente,
        "corte": FECHA_CORTE.strftime("%Y-%m-%d"),
        "fmin": hist["salida_prog"].min().strftime("%Y-%m-%d"),
        "fx": TIPO_CAMBIO_PEN,
        "rutas": [{"ruta": r.ruta, "o": r.origen, "d": r.destino, "m": r.mercado}
                  for r in rutas.itertuples()],
        "v": v,
        "dims": dims,
        "ventas": filas,
        "anticipadas": I.ventas_anticipadas(todos),
        "niveles": niv.to_dict(orient="records"),
        "nacionalidad": [{"pais": p, "gasto": round(float(g), 2)} for p, g in nac.items()],
        "aeropuertos": {c: {"lat": COORDENADAS[c][0], "lon": COORDENADAS[c][1],
                            "ciudad": CIUDADES.get(c, c), "pais": pais(c)} for c in usados},
    }


def main():
    datos = construir_datos()
    texto = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    mapa_js = (RAIZ / "aerolinea" / "mapa_vuelos.js").read_text(encoding="utf-8")
    html = (PLANTILLA.read_text(encoding="utf-8").replace("__MAPA_JS__", mapa_js)
            .replace("__DATOS__", texto))
    CARPETA_SALIDAS.mkdir(exist_ok=True)
    DESTINO.write_text(html, encoding="utf-8")
    print(f"Listo: {DESTINO} ({DESTINO.stat().st_size / 1e6:.1f} MB, fuente: {datos['fuente']})")


if __name__ == "__main__":
    main()
