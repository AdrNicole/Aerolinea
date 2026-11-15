"""Indicadores de negocio del historico (vista de la empresa).

Definiciones (las mismas en el dashboard Streamlit y en el informe):
  Periodo historico  vuelos con salida hasta FECHA_CORTE (30/09/2026):
                     aterrizados y cancelados. Los 'programado' son
                     ventas anticipadas y se reportan aparte.
  Ingresos           boletos + cargos de equipaje de vuelos ATERRIZADOS
                     (los boletos de vuelos cancelados se reembolsan).
  Ocupacion          boletos / asientos ofrecidos (load factor).
  Puntualidad        % de vuelos aterrizados con retraso < 15 min.
  Tasa cancelacion   vuelos cancelados / vuelos del periodo.
  Ingreso x asiento  ingresos / asientos ofrecidos.

Todas las funciones son puras (DataFrame -> DataFrame/dict): se prueban
sin base de datos.
"""
import pandas as pd

from .config import FECHA_CORTE

UMBRAL_RETRASO = 15


def preparar_vuelos(vuelos: pd.DataFrame) -> pd.DataFrame:
    """Normaliza la tabla de hechos por vuelo (AnalisisRepository.vuelos)."""
    df = vuelos.copy()
    df["salida_prog"] = pd.to_datetime(df["salida_prog"])
    df["salida_real"] = pd.to_datetime(df["salida_real"])
    df["mes"] = df["salida_prog"].dt.to_period("M").dt.to_timestamp()
    df["anio"] = df["salida_prog"].dt.year
    df["aterrizado"] = df["estado"].eq("aterrizado")
    df["cancelado"] = df["estado"].eq("cancelado")
    df["ingresos"] = (df["ingresos_boletos"] + df["ingresos_equipaje"]).where(df["aterrizado"], 0.0)
    df["boletos_volados"] = df["boletos"].where(df["aterrizado"], 0)
    df["asientos_ofrecidos"] = df["capacidad"].where(df["aterrizado"], 0)
    df["puntual"] = (df["retraso_min"] < UMBRAL_RETRASO).where(df["aterrizado"])
    df["mercado"] = (df["pais_origen"].ne("Perú") | df["pais_destino"].ne("Perú")).map(
        {True: "Internacional", False: "Nacional"})
    return df


def historico(vuelos: pd.DataFrame) -> pd.DataFrame:
    return vuelos[vuelos["salida_prog"] <= FECHA_CORTE]


def filtrar(vuelos: pd.DataFrame, desde=None, hasta=None, rutas=None) -> pd.DataFrame:
    df = vuelos
    if desde is not None:
        df = df[df["salida_prog"] >= pd.Timestamp(desde)]
    if hasta is not None:
        df = df[df["salida_prog"] < pd.Timestamp(hasta) + pd.Timedelta(days=1)]
    if rutas:
        df = df[df["ruta"].isin(rutas)]
    return df


def _agregar(df: pd.DataFrame) -> pd.Series:
    asientos = df["asientos_ofrecidos"].sum()
    volados = df["boletos_volados"].sum()
    return pd.Series({
        "vuelos": len(df),
        "vuelos_operados": int(df["aterrizado"].sum()),
        "cancelados": int(df["cancelado"].sum()),
        "ingresos": df["ingresos"].sum(),
        "ingresos_equipaje": df["ingresos_equipaje"].where(df["aterrizado"], 0).sum(),
        "pasajeros": volados,
        "asientos": asientos,
        "ocupacion_pct": volados / asientos * 100 if asientos else float("nan"),
        "puntualidad_pct": df["puntual"].mean() * 100 if df["aterrizado"].any() else float("nan"),
        "retraso_prom": df.loc[df["aterrizado"], "retraso_min"].mean(),
        "cancelacion_pct": df["cancelado"].mean() * 100 if len(df) else float("nan"),
        "ticket_prom": df["ingresos_boletos"].where(df["aterrizado"], 0).sum() / volados if volados else float("nan"),
        "ingreso_por_asiento": df["ingresos"].sum() / asientos if asientos else float("nan"),
    })


def kpis(vuelos: pd.DataFrame) -> dict:
    """Indicadores principales del periodo (vuelos ya filtrados)."""
    return _agregar(vuelos).to_dict()


def serie_mensual(vuelos: pd.DataFrame) -> pd.DataFrame:
    return vuelos.groupby("mes").apply(_agregar, include_groups=False)


def serie(vuelos: pd.DataFrame, por: str = "mes") -> pd.DataFrame:
    """Indicadores por periodo: por="mes" o por="dia". Indice: periodo."""
    clave = vuelos["mes"] if por == "mes" else vuelos["salida_prog"].dt.normalize()
    return (vuelos.assign(periodo=clave)
                  .groupby("periodo").apply(_agregar, include_groups=False))


def por_ruta(vuelos: pd.DataFrame) -> pd.DataFrame:
    g = vuelos.groupby("ruta").apply(_agregar, include_groups=False)
    g["pct_ingresos"] = g["ingresos"] / g["ingresos"].sum() * 100
    return g.sort_values("ingresos", ascending=False)


def comparativo_anual(vuelos: pd.DataFrame, hasta_mes: int | None = None) -> pd.DataFrame:
    """Compara anios en el MISMO periodo (enero a hasta_mes; por defecto
    el mes de corte) para que 2026, que esta incompleto, sea comparable.
    Agrega la variacion % frente al anio anterior."""
    mes = hasta_mes or FECHA_CORTE.month
    df = vuelos[vuelos["salida_prog"].dt.month <= mes]
    g = df.groupby("anio").apply(_agregar, include_groups=False)
    for col in ("ingresos", "pasajeros", "vuelos_operados"):
        g[f"var_{col}_pct"] = g[col].pct_change() * 100
    return g


def mezcla(ventas: pd.DataFrame, columna: str) -> pd.DataFrame:
    """Participacion de ingresos y boletos por una dimension (clase,
    tarifa, canal...). ventas = analisis.preparar_ventas(...) de vuelos
    aterrizados."""
    g = ventas.groupby(columna, observed=True).agg(boletos=("id_boleto", "count"),
                                                   ingresos=("precio", "sum"),
                                                   precio_prom=("precio", "mean"))
    g["pct_ingresos"] = g["ingresos"] / g["ingresos"].sum() * 100
    g["pct_boletos"] = g["boletos"] / g["boletos"].sum() * 100
    return g.sort_values("ingresos", ascending=False)


def ventas_anticipadas(vuelos: pd.DataFrame) -> dict:
    """Vuelos 'programado' (posteriores al corte): lo ya vendido."""
    p = vuelos[vuelos["estado"] == "programado"]
    return {"vuelos": len(p), "boletos": int(p["boletos"].sum()),
            "ingresos": float(p["ingresos_boletos"].sum()),
            "ocupacion_pct": float(p["boletos"].sum() / p["capacidad"].sum() * 100) if len(p) else 0.0}


def mismo_periodo_anio_anterior(desde, hasta):
    """Ventana de comparacion: las mismas fechas, un anio antes."""
    return (pd.Timestamp(desde) - pd.DateOffset(years=1),
            pd.Timestamp(hasta) - pd.DateOffset(years=1))


def variacion_pct(actual: float, anterior: float) -> float | None:
    if anterior in (0, None) or pd.isna(anterior) or pd.isna(actual):
        return None
    return (actual - anterior) / anterior * 100


def nombre_par(origen: str, destino: str) -> str:
    """Ruta sin sentido: 'LIM ⇄ CUZ' (Lima primero; si no, orden alfabetico).
    Ida y vuelta se dibujan como un solo arco en el mapa."""
    a, b = sorted([origen, destino], key=lambda x: (x != "LIM", x))
    return f"{a} ⇄ {b}"


def por_par(vuelos: pd.DataFrame) -> pd.DataFrame:
    """Indicadores por par de ciudades (ida + vuelta juntas), con los
    codigos de ambos extremos para ubicarlos en el mapa."""
    if vuelos.empty:
        return pd.DataFrame(columns=["par", "a", "b"])
    df = vuelos.assign(par=[nombre_par(o, d) for o, d in zip(vuelos["origen"], vuelos["destino"])])
    g = df.groupby("par").apply(_agregar, include_groups=False).reset_index()
    g[["a", "b"]] = g["par"].str.split(" ⇄ ", expand=True)
    g["pct_ingresos"] = g["ingresos"] / g["ingresos"].sum() * 100 if g["ingresos"].sum() else 0.0
    return g.sort_values("ingresos", ascending=False).reset_index(drop=True)


def por_dia(vuelos: pd.DataFrame) -> pd.DataFrame:
    """Un registro por dia con vuelos: vuelos programados ese dia,
    pasajeros e ingresos (vuelos aterrizados)."""
    df = vuelos.assign(fecha=vuelos["salida_prog"].dt.normalize())
    return df.groupby("fecha").agg(vuelos=("id_vuelo", "count"),
                                   pasajeros=("boletos_volados", "sum"),
                                   ingresos=("ingresos", "sum")).reset_index()
