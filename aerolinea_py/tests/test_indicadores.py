"""Indicadores de negocio del dashboard."""
import pandas as pd
import pytest

from aerolinea import indicadores as I


def vuelos_ejemplo():
    filas = [
        # id, salida, estado, ruta, pais_dest, cap, boletos, ingresos, equipaje, retraso
        (1, "2025-01-10 08:00", "aterrizado", "LIM-CUZ", "Perú", 100, 90, 9000.0, 350.0, 5),
        (2, "2025-01-20 08:00", "aterrizado", "LIM-CUZ", "Perú", 100, 70, 7000.0, 0.0, 40),
        (3, "2025-02-05 08:00", "cancelado", "LIM-MIA", "Estados Unidos", 200, 150, 60000.0, 0.0, None),
        (4, "2025-02-07 08:00", "aterrizado", "LIM-MIA", "Estados Unidos", 200, 180, 72000.0, 700.0, 10),
        (5, "2024-01-15 08:00", "aterrizado", "LIM-CUZ", "Perú", 100, 80, 8000.0, 0.0, 0),
        (6, "2026-10-05 08:00", "programado", "LIM-CUZ", "Perú", 100, 30, 3000.0, 0.0, None),
    ]
    df = pd.DataFrame(filas, columns=["id_vuelo", "salida_prog", "estado", "ruta", "pais_destino",
                                      "capacidad", "boletos", "ingresos_boletos",
                                      "ingresos_equipaje", "retraso_min"])
    df["salida_real"] = None
    df["pais_origen"] = "Perú"
    df["origen"] = "LIM"
    return I.preparar_vuelos(df)


def test_historico_excluye_programados_posteriores_al_corte():
    v = vuelos_ejemplo()
    assert 6 not in I.historico(v)["id_vuelo"].values


def test_kpis_cuentan_solo_vuelos_aterrizados():
    k = I.kpis(I.filtrar(I.historico(vuelos_ejemplo()), "2025-01-01", "2025-12-31"))
    assert k["vuelos"] == 4 and k["vuelos_operados"] == 3 and k["cancelados"] == 1
    assert k["ingresos"] == pytest.approx(9000 + 350 + 7000 + 72000 + 700)   # el cancelado no suma
    assert k["pasajeros"] == 90 + 70 + 180
    assert k["ocupacion_pct"] == pytest.approx(340 / 400 * 100)
    assert k["puntualidad_pct"] == pytest.approx(200 / 3)                       # 2 de 3 con < 15 min
    assert k["cancelacion_pct"] == pytest.approx(25)
    assert k["ticket_prom"] == pytest.approx((9000 + 7000 + 72000) / 340)


def test_mercado_y_por_ruta():
    v = I.historico(vuelos_ejemplo())
    assert set(v.loc[v["ruta"] == "LIM-MIA", "mercado"]) == {"Internacional"}
    r = I.por_ruta(v)
    assert r.index[0] == "LIM-MIA" and r["pct_ingresos"].sum() == pytest.approx(100)


def test_comparativo_anual_mismo_periodo():
    c = I.comparativo_anual(I.historico(vuelos_ejemplo()), hasta_mes=2)
    assert list(c.index) == [2024, 2025]
    assert c.loc[2025, "var_pasajeros_pct"] == pytest.approx((340 - 80) / 80 * 100)


def test_ventas_anticipadas():
    va = I.ventas_anticipadas(vuelos_ejemplo())
    assert va["vuelos"] == 1 and va["boletos"] == 30 and va["ocupacion_pct"] == 30


def test_variacion_y_periodo_anterior():
    assert I.variacion_pct(110, 100) == pytest.approx(10)
    assert I.variacion_pct(5, 0) is None
    d, h = I.mismo_periodo_anio_anterior("2025-03-01", "2025-03-31")
    assert (d, h) == (pd.Timestamp("2024-03-01"), pd.Timestamp("2024-03-31"))


def test_por_par_une_ida_y_vuelta():
    v = vuelos_ejemplo()
    extra = v[v["id_vuelo"] == 1].assign(id_vuelo=99, origen="CUZ", ruta="CUZ-LIM", destino="LIM")
    v = I.historico(pd.concat([v.assign(destino=v["ruta"].str[-3:]), extra]))
    p = I.por_par(v).set_index("par")
    assert "LIM ⇄ CUZ" in p.index and "LIM ⇄ MIA" in p.index
    assert p.loc["LIM ⇄ CUZ", "vuelos_operados"] == 4          # 3 de ida + 1 de vuelta
    assert (p.loc["LIM ⇄ CUZ", "a"], p.loc["LIM ⇄ CUZ", "b"]) == ("LIM", "CUZ")
    assert p["pct_ingresos"].sum() == pytest.approx(100)


def test_nombre_par_pone_lima_primero():
    assert I.nombre_par("CUZ", "LIM") == "LIM ⇄ CUZ"
    assert I.nombre_par("CUZ", "AQP") == "AQP ⇄ CUZ"


def test_por_dia():
    d = I.por_dia(I.historico(vuelos_ejemplo())).set_index("fecha")
    assert d.loc[pd.Timestamp("2025-01-10"), "pasajeros"] == 90
    assert d.loc[pd.Timestamp("2025-02-05"), "ingresos"] == 0            # cancelado


def test_todos_los_aeropuertos_tienen_coordenadas():
    from aerolinea.geo import COORDENADAS, lon_lat
    iatas = ["LIM", "CUZ", "AQP", "PIU", "TRU", "IQT", "JUL", "TPP", "CIX", "PCL", "AYP", "TCQ",
             "PEM", "JAU", "TBP", "CJA", "SCL", "BOG", "EZE", "GRU", "MIA", "MEX", "PTY", "UIO", "MAD"]
    assert set(iatas) == set(COORDENADAS)
    lon, lat = lon_lat("LIM")
    assert -80 < lon < -76 and -13 < lat < -11
