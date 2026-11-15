"""Analisis con pandas sobre datos pequenos construidos a mano."""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from aerolinea import analisis as A


def ventas_sinteticas(n=3000, semilla=0):
    """Boletos con un precio generado con factores conocidos, para
    comprobar que la calibracion los recupera."""
    rng = np.random.default_rng(semilla)
    salida = datetime(2025, 3, 10, 9, 0)
    filas = []
    for i in range(n):
        id_vuelo = i // 100
        fecha_vuelo = salida + timedelta(days=int(id_vuelo) * 15)
        dias = int(rng.integers(0, 200))
        filas.append({"id_boleto": i, "id_vuelo": id_vuelo, "id_tarifa": 1, "clase": "Económica",
                      "tarifa": "Básica", "id_ruta": 1, "origen": "LIM", "destino": "CUZ",
                      "capacidad": 100, "estado": "aterrizado",
                      "salida_prog": fecha_vuelo, "fecha_compra": fecha_vuelo - timedelta(days=dias)})
    df = pd.DataFrame(filas)
    prep = A.preparar_ventas(df.assign(precio=1.0))
    f_ant = prep["dias_anticipacion"].apply(lambda d: 2.0 if d <= 3 else 1.0)
    f_tem = np.where(prep["temporada_alta"], 1.2, 1.0)
    df = df.sort_values("id_boleto")
    df["precio"] = (100 * f_ant * f_tem * rng.lognormal(0, 0.02, n)).to_numpy()
    return df


def test_preparar_ventas_calcula_anticipacion_y_ocupacion():
    v = A.preparar_ventas(ventas_sinteticas(200))
    assert (v["dias_anticipacion"] >= 0).all()
    primer = v[v["id_vuelo"] == 0].sort_values("fecha_compra")
    assert primer["ocupacion_al_comprar"].iloc[0] == 0
    assert primer["ocupacion_al_comprar"].iloc[-1] == pytest.approx(0.99)


def test_excluye_vuelos_cancelados():
    df = ventas_sinteticas(200)
    df.loc[df["id_vuelo"] == 0, "estado"] = "cancelado"
    assert 0 not in A.preparar_ventas(df)["id_vuelo"].values


def test_comparar_anticipacion():
    v = A.preparar_ventas(ventas_sinteticas())
    r = A.comparar_anticipacion(v, "LIM-CUZ")
    assert r["veces"] == pytest.approx(2.0, rel=0.1)
    assert r["p_mann_whitney"] < 0.001
    assert set(r["por_tarifa"].index) == {"Básica"}


def test_calibracion_recupera_factores_conocidos():
    cal = A.calibrar_factores_precio(A.preparar_ventas(ventas_sinteticas(6000)))
    assert dict(cal["anticipacion"])[3] == pytest.approx(2.0, rel=0.05)
    assert cal["temporada_alta"] == pytest.approx(1.2, rel=0.05)
    assert cal["r2_log"] > 0.9


def test_retraso_hora_dia_y_por_dia():
    punt = pd.DataFrame({
        "id_vuelo": [1, 2, 3, 4], "ruta": ["LIM-CUZ"] * 4,
        "salida_prog": pd.to_datetime(["2025-01-03 07:00", "2025-01-03 19:00",   # viernes
                                       "2025-01-06 07:00", "2025-01-06 07:30"]),  # lunes
        "retraso_min": [10, 30, 0, 4], "es_retrasado": [0, 1, 0, 0]})
    piv = A.retraso_hora_dia(punt)
    assert piv.loc["06-09", "Viernes"] == 10 and piv.loc["18-24", "Viernes"] == 30
    assert piv.loc["06-09", "Lunes"] == 2
    dia = A.retraso_por_dia(punt)
    assert list(dia.index) == A.DIAS
    assert dia.loc["Viernes", "pct_retrasados"] == 50


def test_retraso_mensual_media_movil():
    punt = pd.DataFrame({"id_vuelo": range(3), "salida_prog": pd.to_datetime(
        ["2025-01-05", "2025-02-05", "2025-03-05"]), "retraso_min": [10, 20, 30],
        "es_retrasado": [0, 1, 1]})
    m = A.retraso_mensual(punt)
    assert m["media_movil_3m"].tolist() == [10, 15, 20]
    assert m["lluvias"].all()


def test_pasajeros_por_nivel_incluye_no_afiliados():
    pax = pd.DataFrame({"id_pasajero": [1, 2, 3], "nivel": [None, "Oro", "Oro"],
                        "millas": [None, 40000, 50000], "vuelos": [1, 5, 7],
                        "gasto_usd": [100.0, 400.0, 500.0]})
    t = A.pasajeros_por_nivel(pax)
    assert list(t.index) == A.NIVELES
    assert t.loc["Oro", "pasajeros"] == 2 and t.loc["Oro", "pct_gasto"] == 90
