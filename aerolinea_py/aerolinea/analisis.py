"""Analisis con pandas (merge, groupby, pivot_table, series de tiempo).

Todas las funciones reciben DataFrames (los que entrega
AnalisisRepository) y devuelven DataFrames o diccionarios: no tocan la
base de datos, por eso se pueden probar con datos pequenos en pytest.
"""
import numpy as np
import pandas as pd
from scipy import stats

DIAS = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
NIVELES = ["Sin cuenta", "Clásica", "Plata", "Oro", "Platino"]
TRAMOS_ANTICIPACION = [-1, 3, 7, 14, 30, 60, 120, np.inf]
ETIQUETAS_ANTICIPACION = ["0-3", "4-7", "8-14", "15-30", "31-60", "61-120", ">120"]
TRAMOS_OCUPACION = [-0.001, 0.50, 0.70, 0.85, 0.95, np.inf]
ETIQUETAS_OCUPACION = ["<50%", "50-70%", "70-85%", "85-95%", ">95%"]
MESES_ALTA = (7, 12)


# ======================================================================
# Preparacion
# ======================================================================
def preparar_ventas(ventas: pd.DataFrame) -> pd.DataFrame:
    """Agrega a cada boleto:
      dias_anticipacion     dias entre la compra y la salida
      ocupacion_al_comprar  % del avion ya vendido cuando se compro
                            (orden de compra dentro del vuelo / capacidad)
      tramo_anticipacion, tramo_ocupacion, mes, temporada_alta, ruta
    Excluye vuelos cancelados (sus boletos se reembolsan)."""
    df = ventas[ventas["estado"] != "cancelado"].copy()
    df["fecha_compra"] = pd.to_datetime(df["fecha_compra"])
    df["salida_prog"] = pd.to_datetime(df["salida_prog"])
    df["dias_anticipacion"] = (df["salida_prog"] - df["fecha_compra"]).dt.days
    df = df.sort_values(["id_vuelo", "fecha_compra", "id_boleto"])
    df["ocupacion_al_comprar"] = df.groupby("id_vuelo").cumcount() / df["capacidad"]
    df["tramo_anticipacion"] = pd.cut(df["dias_anticipacion"], TRAMOS_ANTICIPACION,
                                      labels=ETIQUETAS_ANTICIPACION)
    df["tramo_ocupacion"] = pd.cut(df["ocupacion_al_comprar"], TRAMOS_OCUPACION,
                                   labels=ETIQUETAS_OCUPACION)
    df["mes"] = df["salida_prog"].dt.month
    df["temporada_alta"] = df["mes"].isin(MESES_ALTA)
    df["ruta"] = df["origen"] + "-" + df["destino"]
    return df.sort_values("id_boleto").reset_index(drop=True)


# ======================================================================
# Puntualidad (fuente: v_puntualidad_vuelo)
# ======================================================================
def _dia_es(serie_fechas: pd.Series) -> pd.Categorical:
    return pd.Categorical(serie_fechas.dt.dayofweek.map(dict(enumerate(DIAS))),
                          categories=DIAS, ordered=True)


def retraso_por_ruta(punt: pd.DataFrame, min_vuelos: int = 10) -> pd.DataFrame:
    """Ranking de rutas por puntualidad (peor primero)."""
    g = punt.groupby("ruta").agg(
        vuelos=("id_vuelo", "count"),
        retraso_prom=("retraso_min", "mean"),
        retraso_p90=("retraso_min", lambda s: s.quantile(0.9)),
        pct_retrasados=("es_retrasado", "mean"),
    )
    g["pct_retrasados"] *= 100
    g = g[g["vuelos"] >= min_vuelos].round(1)
    return g.sort_values(["retraso_prom", "pct_retrasados"], ascending=False)


def retraso_hora_dia(punt: pd.DataFrame) -> pd.DataFrame:
    """pivot_table: retraso promedio por franja horaria (filas) y dia
    de la semana (columnas)."""
    df = punt.copy()
    df["salida_prog"] = pd.to_datetime(df["salida_prog"])
    df["dia"] = _dia_es(df["salida_prog"])
    df["franja"] = pd.cut(df["salida_prog"].dt.hour, [0, 6, 9, 12, 15, 18, 24], right=False,
                          labels=["00-06", "06-09", "09-12", "12-15", "15-18", "18-24"])
    return df.pivot_table(index="franja", columns="dia", values="retraso_min",
                          aggfunc="mean", observed=False).round(1)


def retraso_por_dia(punt: pd.DataFrame) -> pd.DataFrame:
    df = punt.copy()
    df["dia"] = _dia_es(pd.to_datetime(df["salida_prog"]))
    g = df.groupby("dia", observed=False).agg(vuelos=("id_vuelo", "count"),
                                              retraso_prom=("retraso_min", "mean"),
                                              pct_retrasados=("es_retrasado", "mean"))
    g["pct_retrasados"] *= 100
    return g.round(1)


def retraso_mensual(punt: pd.DataFrame) -> pd.DataFrame:
    """Serie de tiempo mensual (resample) con media movil de 3 meses y
    marca de temporada de lluvias (dic-mar)."""
    s = (punt.assign(salida_prog=pd.to_datetime(punt["salida_prog"]))
             .set_index("salida_prog").sort_index())
    m = s.resample("MS").agg({"retraso_min": "mean", "es_retrasado": "mean", "id_vuelo": "count"})
    m.columns = ["retraso_prom", "pct_retrasados", "vuelos"]
    m["pct_retrasados"] *= 100
    m["media_movil_3m"] = m["retraso_prom"].rolling(3, min_periods=1).mean()
    m["lluvias"] = m.index.month.isin([12, 1, 2, 3])
    return m.round(1)


# ======================================================================
# Ocupacion (fuente: v_ocupacion_vuelo, solo aterrizados)
# ======================================================================
def ocupacion_por_ruta(ocup: pd.DataFrame) -> pd.DataFrame:
    g = ocup.groupby("ruta").agg(vuelos=("id_vuelo", "count"),
                                 ocupacion_prom=("factor_ocupacion_pct", "mean"),
                                 vuelos_llenos=("asientos_libres", lambda s: int((s == 0).sum())))
    g["pct_llenos"] = g["vuelos_llenos"] / g["vuelos"] * 100
    return g.round(1).sort_values("ocupacion_prom", ascending=False)


def ocupacion_mensual(ocup: pd.DataFrame) -> pd.DataFrame:
    s = ocup.assign(salida_prog=pd.to_datetime(ocup["salida_prog"])).set_index("salida_prog")
    m = s.resample("MS").agg({"factor_ocupacion_pct": "mean", "id_vuelo": "count"})
    m.columns = ["ocupacion_prom", "vuelos"]
    return m.round(1)


# ======================================================================
# Precios
# ======================================================================
def curva_precio_anticipacion(v: pd.DataFrame, ruta: str | None = None) -> pd.DataFrame:
    """Precio promedio por tramo de anticipacion (filas) y clase
    (columnas). v = preparar_ventas(...)."""
    df = v if ruta is None else v[v["ruta"] == ruta]
    return df.pivot_table(index="tramo_anticipacion", columns="clase", values="precio",
                          aggfunc="mean", observed=False).round(1)


def comparar_anticipacion(v: pd.DataFrame, ruta: str = "LIM-CUZ",
                          corto=(0, 3), largo=(28, 32)) -> dict:
    """Pregunta del enunciado: ¿cuanto mas paga quien compra 3 dias
    antes frente a quien compra con 30 dias, en Lima-Cusco?

    - corto/largo: ventanas de dias (por defecto 0-3 y 28-32).
    - Prueba de Mann-Whitney (no asume normalidad: los precios son
      asimetricos) y t de Welch (varianzas distintas).
    - Ademas compara POR TARIFA, para descartar que la diferencia se
      deba a que en cada grupo se compran tarifas distintas."""
    df = v[v["ruta"] == ruta]
    a = df[df["dias_anticipacion"].between(*corto)]
    b = df[df["dias_anticipacion"].between(*largo)]
    if a.empty or b.empty:
        raise ValueError("No hay boletos en alguna de las dos ventanas")
    mw = stats.mannwhitneyu(a["precio"], b["precio"], alternative="greater")
    tt = stats.ttest_ind(a["precio"], b["precio"], equal_var=False)
    por_tarifa = pd.DataFrame({
        f"prom_{corto[0]}_{corto[1]}d": a.groupby("tarifa")["precio"].mean(),
        f"prom_{largo[0]}_{largo[1]}d": b.groupby("tarifa")["precio"].mean(),
        "n_corto": a.groupby("tarifa").size(), "n_largo": b.groupby("tarifa").size(),
    })
    por_tarifa["veces"] = por_tarifa.iloc[:, 0] / por_tarifa.iloc[:, 1]
    return {
        "ruta": ruta,
        "prom_corto": round(float(a["precio"].mean()), 2),
        "prom_largo": round(float(b["precio"].mean()), 2),
        "diferencia_usd": round(float(a["precio"].mean() - b["precio"].mean()), 2),
        "veces": round(float(a["precio"].mean() / b["precio"].mean()), 2),
        "n_corto": len(a), "n_largo": len(b),
        "p_mann_whitney": float(mw.pvalue), "p_welch": float(tt.pvalue),
        "por_tarifa": por_tarifa.round(2),
    }


def calibrar_factores_precio(v: pd.DataFrame) -> dict:
    """Ajusta el modelo multiplicativo que usa la estrategia PrecioDinamico:

        precio / mediana(ruta, tarifa) = k * f_anticipacion * f_ocupacion * f_temporada

    con minimos cuadrados sobre log(precio relativo). Referencias
    (factor 1): 61-120 dias, ocupacion < 50%, temporada normal.
    Devuelve tablas listas para PrecioDinamico.desde_calibracion()."""
    df = v.dropna(subset=["tramo_anticipacion", "tramo_ocupacion"]).copy()
    rel = df["precio"] / df.groupby(["id_ruta", "id_tarifa"])["precio"].transform("median")
    X = pd.concat([
        pd.get_dummies(df["tramo_anticipacion"], prefix="a").drop(columns="a_61-120"),
        pd.get_dummies(df["tramo_ocupacion"], prefix="o").drop(columns="o_<50%"),
        df["temporada_alta"].astype(int).rename("t_alta"),
    ], axis=1).astype(float)
    A = np.column_stack([np.ones(len(X)), X.to_numpy()])
    y = np.log(rel.to_numpy())
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    pred = A @ coef
    r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    f = dict(zip(X.columns, np.exp(coef[1:])))
    limites_a = [3, 7, 14, 30, 60, 120, np.inf]
    limites_o = [0.50, 0.70, 0.85, 0.95, np.inf]
    return {
        "anticipacion": [(lim, round(float(f.get(f"a_{et}", 1.0)), 2))
                         for lim, et in zip(limites_a, ETIQUETAS_ANTICIPACION)],
        "ocupacion": [(lim, round(float(f.get(f"o_{et}", 1.0)), 2))
                      for lim, et in zip(limites_o, ETIQUETAS_OCUPACION)],
        "temporada_alta": round(float(f["t_alta"]), 2),
        "k": round(float(np.exp(coef[0])), 3),
        "r2_log": round(float(r2), 3),
    }


# ======================================================================
# Pasajeros frecuentes (fuente: AnalisisRepository.pasajeros_millas)
# ======================================================================
def pasajeros_por_nivel(pax: pd.DataFrame) -> pd.DataFrame:
    df = pax.copy()
    df["nivel"] = pd.Categorical(df["nivel"].fillna("Sin cuenta"), categories=NIVELES, ordered=True)
    g = df.groupby("nivel", observed=False).agg(
        pasajeros=("id_pasajero", "count"),
        vuelos_prom=("vuelos", "mean"),
        vuelos_mediana=("vuelos", "median"),
        gasto_prom_usd=("gasto_usd", "mean"),
        millas_prom=("millas", "mean"),
    )
    g["pct_pasajeros"] = g["pasajeros"] / g["pasajeros"].sum() * 100
    g["pct_gasto"] = (df.groupby("nivel", observed=False)["gasto_usd"].sum()
                      / df["gasto_usd"].sum() * 100)
    return g.round(1)


def ingresos_ruta_clase(v: pd.DataFrame) -> pd.DataFrame:
    """Tabla dinamica de ingresos por ruta y clase con totales (margins)."""
    return v.pivot_table(index="ruta", columns="clase", values="precio", aggfunc="sum",
                         margins=True, margins_name="TOTAL", fill_value=0).round(0) \
            .sort_values("TOTAL", ascending=False)
