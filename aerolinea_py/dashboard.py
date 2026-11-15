"""Dashboard de negocio (vista de la empresa) con Streamlit.

Uso:  streamlit run dashboard.py
Fuente de datos:
  - MySQL si hay credenciales (archivo .env, como en main.py);
  - si no, los 14 CSV del dataset (aerolinea/fuente_csv.py). Asi funciona
    publicado en Streamlit Community Cloud, donde no hay MySQL.
Muestra el historico hasta la fecha de corte del dataset (30/09/2026).
Definiciones de cada indicador: aerolinea/indicadores.py.
Tema oscuro: .streamlit/config.toml.
"""
import math
import os

import altair as alt
import pandas as pd
import streamlit as st

from aerolinea import analisis as A
from aerolinea import indicadores as I
from aerolinea.config import FECHA_CORTE, RAIZ
from aerolinea.geo import CIUDADES, lon_lat
from aerolinea.patrones.reserva_builder import TIPO_CAMBIO_PEN

try:
    import pydeck as pdk          # viene instalado con Streamlit
except ImportError:               # pragma: no cover
    pdk = None

# Paleta para fondo oscuro
AZUL, NARANJA, VERDE, AMARILLO, ROJO, GRIS = (
    "#3d9cf5", "#f2803c", "#2fbf71", "#f0c247", "#ef5b5b", "#8b95a7")
FONDO = "#0b1220"
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_LARGOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                "septiembre", "octubre", "noviembre", "diciembre"]
DIAS_LARGOS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
# Ejes de fecha en espanol (Vega usa ingles por defecto)
EJE_MES = alt.Axis(labelExpr="['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']"
                             "[month(datum.value)] + ' ' + timeFormat(datum.value, '%y')")
EJE_DIA = alt.Axis(labelExpr="date(datum.value) + ' ' + ['ene','feb','mar','abr','may','jun','jul',"
                             "'ago','sep','oct','nov','dic'][month(datum.value)]")


def mes_es(fecha) -> str:
    return f"{MESES[fecha.month - 1]} {fecha.year}"


def dia_es(fecha) -> str:
    return f"{fecha.day} {MESES[fecha.month - 1]} {fecha.year}"


st.set_page_config(page_title="Aerolínea · Centro de control", page_icon="✈️", layout="wide")

st.markdown("""
<style>
  .block-container { padding-top: 1.6rem; }
  .ae-hero { background: linear-gradient(120deg, #123a6b 0%, #0f2747 45%, #0b1220 100%);
             border: 1px solid #1f3355; border-radius: 16px; padding: 22px 28px; margin-bottom: 14px; }
  .ae-hero h1 { color: #ffffff; font-size: 2.1rem; margin: 0 0 4px 0; letter-spacing: -0.5px; }
  .ae-hero .sub { color: #b9c7dd; font-size: 1.02rem; margin: 0; }
  .ae-hero .chips { margin-top: 12px; }
  .ae-chip { display: inline-block; background: rgba(61,156,245,.15); color: #9fd3ff;
             border: 1px solid rgba(61,156,245,.35); border-radius: 999px; padding: 2px 10px;
             font-size: .78rem; margin-right: 6px; }
  .ae-insight { background: #131c2e; border: 1px solid #1f2b42; border-left: 4px solid #3d9cf5;
                border-radius: 10px; padding: 12px 14px; height: 100%; }
  .ae-insight .t { color: #8b95a7; font-size: .78rem; text-transform: uppercase; letter-spacing: .6px; }
  .ae-insight .v { color: #e6edf7; font-size: .98rem; margin-top: 4px; line-height: 1.35; }
  .ae-leyenda { display: flex; align-items: center; gap: 10px; color: #b9c7dd; font-size: .82rem; }
  .ae-barra { height: 10px; width: 220px; border-radius: 6px; }
  div[data-testid="stMetricValue"] { font-size: 1.9rem; }
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------------
# Datos (se leen una vez y quedan en cache 1 hora)
# ----------------------------------------------------------------------
def elegir_repositorio():
    """MySQL si hay credenciales; si falla o no las hay, los CSV.
    fuente_csv solo se importa cuando hace falta."""
    if os.getenv("AEROLINEA_DB_CLAVE") is not None:     # hay .env (se lee en config.py)
        try:
            from aerolinea.repositorios import AnalisisRepository
            repo = AnalisisRepository()
            repo.cn.consultar("SELECT 1")
            return repo, "MySQL"
        except Exception as e:
            error_mysql = getattr(e, "orig", e)
            from aerolinea.fuente_csv import AnalisisCSV
            try:
                return AnalisisCSV(), f"No se pudo conectar a MySQL ({error_mysql}); se usan los CSV."
            except FileNotFoundError:
                raise RuntimeError(f"No se pudo conectar a MySQL: {error_mysql}") from None
    from aerolinea.fuente_csv import AnalisisCSV
    try:
        return AnalisisCSV(), "archivos CSV"
    except FileNotFoundError:
        raise RuntimeError("No se encontró el archivo .env con la clave de MySQL en "
                           f"{RAIZ} ni los CSV del dataset.") from None


@st.cache_data(ttl=3600, show_spinner="Leyendo datos...")
def cargar():
    repo, fuente = elegir_repositorio()
    vuelos = I.preparar_vuelos(repo.vuelos())
    ventas = A.preparar_ventas(repo.ventas())
    ventas = ventas.merge(vuelos[["id_vuelo", "mercado"]], on="id_vuelo", how="left")
    pax = repo.pasajeros_millas()
    return vuelos, ventas, pax, fuente


try:
    vuelos, ventas, pax, fuente = cargar()
except Exception as e:  # ni MySQL ni CSV
    st.error(f"No se pudieron cargar los datos: {getattr(e, 'orig', e)}\n\n"
             f"En tu PC: el archivo .env debe estar en {RAIZ} (ver .env.ejemplo). "
             "Publicado: los CSV del dataset deben estar en el repositorio.")
    st.stop()

hist = I.historico(vuelos)


# ----------------------------------------------------------------------
# Filtros
# ----------------------------------------------------------------------
st.sidebar.markdown("## ✈️ Filtros")
fecha_min = hist["salida_prog"].min().date()
fecha_max = FECHA_CORTE.date()
rango = st.sidebar.date_input("Periodo (fecha del vuelo)", value=(fecha_min, fecha_max),
                              min_value=fecha_min, max_value=fecha_max)
desde, hasta = (rango if isinstance(rango, (list, tuple)) and len(rango) == 2
                else (fecha_min, fecha_max))
mercado = st.sidebar.radio("Mercado", ["Todos", "Nacional", "Internacional"], horizontal=True)
base = hist if mercado == "Todos" else hist[hist["mercado"] == mercado]
moneda = st.sidebar.radio("Moneda", ["USD", "PEN"], horizontal=True,
                          help=f"PEN convierte con el tipo de cambio del dataset: {TIPO_CAMBIO_PEN}")
# Los precios del dataset estan en USD; para soles se multiplica por el tipo de cambio
FX = TIPO_CAMBIO_PEN if moneda == "PEN" else 1.0
SIM = "S/" if moneda == "PEN" else "US$"
rutas = st.sidebar.multiselect("Rutas (vacío = todas)", sorted(base["ruta"].unique()),
                               placeholder="Elige una o más rutas")
st.sidebar.caption(f"Datos históricos hasta el {FECHA_CORTE:%d/%m/%Y} (fecha de corte del dataset).")
if fuente in ("MySQL", "archivos CSV"):
    st.sidebar.caption(f"Fuente: {fuente}")
else:
    st.sidebar.warning(fuente)

actual = I.filtrar(base, desde, hasta, rutas)
ant_desde, ant_hasta = I.mismo_periodo_anio_anterior(desde, hasta)
# Solo se compara si el anio anterior completo esta dentro de los datos
hay_comparacion = ant_desde.date() >= fecha_min
anterior = I.filtrar(base, ant_desde, ant_hasta, rutas) if hay_comparacion else base.iloc[0:0]
v_act = ventas[ventas["id_vuelo"].isin(actual.loc[actual["aterrizado"], "id_vuelo"])]

if actual.empty:
    st.warning("No hay vuelos para esos filtros.")
    st.stop()

k, k_ant = I.kpis(actual), I.kpis(anterior) if not anterior.empty else {}

# Detalle de las series: por dia si el periodo es corto (hasta ~3 meses), si no por mes
POR_DIA = (pd.Timestamp(hasta) - pd.Timestamp(desde)).days <= 92
UNIDAD = "día" if POR_DIA else "mes"
SERIE = I.serie(actual, "dia" if POR_DIA else "mes").reset_index()
SERIE["periodo_txt"] = SERIE["periodo"].map(dia_es if POR_DIA else mes_es)
EJE_X = alt.X("yearmonthdate(periodo):T" if POR_DIA else "yearmonth(periodo):T",
              title=None, axis=EJE_DIA if POR_DIA else EJE_MES)
ANCHO_BARRA = max(3, min(28, 900 // max(len(SERIE), 1)))
MENSUAL = I.serie(actual, "mes").reset_index()            # para las mini tendencias

# Calculos que usan varias secciones
punt = actual[actual["aterrizado"]].copy()
punt["es_retrasado"] = (punt["retraso_min"] >= I.UMBRAL_RETRASO).astype(int)
por_ruta = I.por_ruta(actual).reset_index()
precio_antic = v_act.groupby("tramo_anticipacion", observed=True)["precio"].mean()


def fmt(valor, plantilla):
    """Formatea un indicador; si no hay datos (NaN) muestra una raya."""
    return "—" if valor is None or pd.isna(valor) else plantilla.format(valor)


def dinero(valor_usd) -> str:
    """Monto en la moneda elegida, abreviado en millones si corresponde."""
    if valor_usd is None or pd.isna(valor_usd):
        return "—"
    v = valor_usd * FX
    return f"{SIM} {v / 1e6:,.1f} M" if abs(v) >= 1e6 else f"{SIM} {v:,.0f}"


# ----------------------------------------------------------------------
# Portada
# ----------------------------------------------------------------------
periodo_txt = f"Del {dia_es(desde)} al {dia_es(hasta)}"
alcance = {"Todos": "toda la red", "Nacional": "vuelos nacionales",
           "Internacional": "vuelos internacionales"}[mercado]
resumen = (f"{periodo_txt}, en {alcance}{' (' + ', '.join(rutas) + ')' if rutas else ''}: "
           f"<b>{fmt(k['pasajeros'], '{:,.0f}')}</b> pasajeros, <b>{dinero(k['ingresos'])}</b> en ingresos, "
           f"<b>{fmt(k['ocupacion_pct'], '{:.1f}%')}</b> de ocupación y "
           f"<b>{fmt(k['puntualidad_pct'], '{:.1f}%')}</b> de vuelos puntuales.")
chips = "".join(f'<span class="ae-chip">{t}</span>' for t in [
    f"Fuente: {fuente if fuente in ('MySQL', 'archivos CSV') else 'CSV'}", f"Moneda: {moneda}",
    "Comparado con el año anterior" if hay_comparacion else "Sin comparación (elige un periodo desde 2025)"])
st.markdown(f"""<div class="ae-hero"><h1>✈️ Centro de control de negocio</h1>
<p class="sub">{resumen}</p><div class="chips">{chips}</div></div>""", unsafe_allow_html=True)


# ----------------------------------------------------------------------
# Indicadores con mini tendencia mensual
# ----------------------------------------------------------------------
def delta(clave, pp=False):
    """Texto de variacion. pp=True: diferencia en puntos porcentuales."""
    if clave not in k_ant or pd.isna(k_ant.get(clave)) or pd.isna(k.get(clave)):
        return None
    if pp:
        return f"{k[clave] - k_ant[clave]:+.1f} pp"
    v = I.variacion_pct(k[clave], k_ant[clave])
    return None if v is None else f"{v:+.1f}%"


def mini_tendencia(columna, color, factor=1.0):
    datos = MENSUAL[["periodo", columna]].dropna().assign(valor=lambda d: d[columna] * factor)
    if len(datos) < 2:
        return
    st.altair_chart(
        alt.Chart(datos).mark_area(color=color, opacity=0.25, line={"color": color, "strokeWidth": 1.5})
        .encode(x=alt.X("periodo:T", axis=None),
                y=alt.Y("valor:Q", axis=None, scale=alt.Scale(zero=False)),
                tooltip=[alt.Tooltip("yearmonth(periodo):T", title="Mes", format="%m/%Y"),
                         alt.Tooltip("valor:Q", title="Valor", format=",.1f")])
        .properties(height=48), use_container_width=True)


TARJETAS = [
    ("Ingresos", dinero(k["ingresos"]), delta("ingresos"), "normal", "ingresos", AZUL, FX),
    ("Pasajeros transportados", fmt(k["pasajeros"], "{:,.0f}"), delta("pasajeros"), "normal",
     "pasajeros", AZUL, 1.0),
    ("Ticket promedio", fmt(k["ticket_prom"] * FX, SIM + " {:,.0f}"), delta("ticket_prom"), "normal",
     "ticket_prom", AZUL, FX),
    ("Ocupación", fmt(k["ocupacion_pct"], "{:.1f}%"), delta("ocupacion_pct", pp=True), "normal",
     "ocupacion_pct", VERDE, 1.0),
    ("Puntualidad (<15 min)", fmt(k["puntualidad_pct"], "{:.1f}%"), delta("puntualidad_pct", pp=True),
     "normal", "puntualidad_pct", NARANJA, 1.0),
    ("Cancelación", fmt(k["cancelacion_pct"], "{:.1f}%"), delta("cancelacion_pct", pp=True), "inverse",
     "cancelacion_pct", ROJO, 1.0),
]
columnas = st.columns(3) + st.columns(3)   # dos filas de tres para que no se corten los montos
for col, (titulo, valor, var, sentido, serie_col, color, factor) in zip(columnas, TARJETAS):
    with col:
        with st.container(border=True):
            st.metric(titulo, valor, var, delta_color=sentido)
            mini_tendencia(serie_col, color, factor)


# ----------------------------------------------------------------------
# Hallazgos automaticos (se recalculan con los filtros)
# ----------------------------------------------------------------------
def plural(dia: str) -> str:
    return dia if dia.endswith("s") else dia + "s"   # sabado -> sabados


def hallazgos():
    out = []
    pr = por_ruta[por_ruta["ingresos"] > 0]
    if len(pr) > 1:
        t = pr.iloc[0]
        out.append(("💰 Ruta más rentable", f"<b>{t['ruta']}</b> genera el <b>{t['pct_ingresos']:.1f}%</b> "
                                           f"de los ingresos ({dinero(t['ingresos'])})."))
    m = MENSUAL[MENSUAL["ingresos"] > 0]
    if len(m) > 1:
        mejor = m.loc[m["ingresos"].idxmax()]
        out.append(("📈 Mejor mes", f"<b>{mes_es(mejor['periodo'])}</b>, con {dinero(mejor['ingresos'])} "
                                   f"y {mejor['ocupacion_pct']:.1f}% de ocupación."))
    if len(punt) >= 20:
        hm = A.retraso_hora_dia(punt).stack().dropna()
        if not hm.empty:
            (franja, dia), minutos = hm.idxmax(), hm.max()
            out.append(("⏱️ Momento con más retraso",
                        f"Los <b>{plural(DIAS_LARGOS[A.DIAS.index(dia)])} de {franja} h</b> salen con "
                        f"<b>{minutos:.0f} min</b> de retraso en promedio."))
    if {"0-3", "61-120"} <= set(precio_antic.index.astype(str)):
        veces = precio_antic["0-3"] / precio_antic["61-120"]
        out.append(("🛒 Compra de último momento",
                    f"Comprar con 0 a 3 días cuesta <b>{veces:.1f} veces</b> más que con 2 a 4 meses "
                    f"({dinero(precio_antic['0-3'])} vs {dinero(precio_antic['61-120'])})."))
    return out


lista = hallazgos()
if lista:
    for col, (titulo, texto) in zip(st.columns(len(lista)), lista):
        col.markdown(f'<div class="ae-insight"><div class="t">{titulo}</div>'
                     f'<div class="v">{texto}</div></div>', unsafe_allow_html=True)
st.write("")

tab_mapa, tab_res, tab_cal, tab_rutas, tab_ventas, tab_oper, tab_cli = st.tabs(
    ["🗺️ Mapa", "📊 Resumen", "📅 Calendario", "✈️ Rutas", "💰 Ventas", "⏱️ Operaciones", "👥 Clientes"])


# ----------------------------------------------------------------------
# Mapa de rutas
# ----------------------------------------------------------------------
METRICAS = {   # nombre visible: (columna, como mostrarla)
    "Ingresos": ("ingresos", dinero),
    "Puntualidad": ("puntualidad_pct", lambda v: fmt(v, "{:.1f}%")),
    "Ocupación": ("ocupacion_pct", lambda v: fmt(v, "{:.1f}%")),
    "Pasajeros": ("pasajeros", lambda v: fmt(v, "{:,.0f}")),
}
# Colores: secuencial azul -> ambar para magnitudes; rojo-amarillo-verde para puntualidad
BAJO, ALTO = (74, 128, 206), (255, 196, 61)
P_ROJO, P_AMARILLO, P_VERDE = (239, 91, 91), (240, 194, 71), (47, 191, 113)
PUNT_MIN, PUNT_MED, PUNT_MAX = 62.0, 72.0, 82.0     # escala fija: comparable entre meses


def mezclar(c1, c2, t):
    t = min(max(t, 0.0), 1.0)
    return [int(a + (b - a) * t) for a, b in zip(c1, c2)]


def color_de(valor, metrica, lo, hi):
    if pd.isna(valor):
        return [120, 130, 150, 160]
    if metrica == "Puntualidad":
        if valor <= PUNT_MED:
            rgb = mezclar(P_ROJO, P_AMARILLO, (valor - PUNT_MIN) / (PUNT_MED - PUNT_MIN))
        else:
            rgb = mezclar(P_AMARILLO, P_VERDE, (valor - PUNT_MED) / (PUNT_MAX - PUNT_MED))
    else:
        rgb = mezclar(BAJO, ALTO, 0.5 if hi == lo else (valor - lo) / (hi - lo))
    return rgb + [220]


def leyenda(metrica, lo, hi):
    if metrica == "Puntualidad":
        grad = "linear-gradient(90deg, rgb(239,91,91), rgb(240,194,71), rgb(47,191,113))"
        izq, der = f"≤{PUNT_MIN:.0f}% (con retrasos)", f"≥{PUNT_MAX:.0f}% (puntual)"
    else:
        grad = "linear-gradient(90deg, rgb(74,128,206), rgb(255,196,61))"
        f = METRICAS[metrica][1]
        izq, der = f(lo), f(hi)
    st.markdown(f'<div class="ae-leyenda"><span>{izq}</span><div class="ae-barra" '
                f'style="background:{grad}"></div><span>{der}</span>'
                f'<span style="margin-left:12px">Grosor del arco = pasajeros</span></div>',
                unsafe_allow_html=True)


with tab_mapa:
    c1, c2, c3 = st.columns([3, 1.1, 2.2])
    metrica = c1.radio("Colorear rutas por", list(METRICAS), horizontal=True)
    vista = c2.radio("Vista", ["Mundo", "Perú"], horizontal=True)
    meses = sorted(actual["mes"].unique())
    opciones = ["Todo el periodo"] + [mes_es(m) for m in meses]
    eleccion = (c3.select_slider("Mes (mueve para ver cómo cambia el tráfico)", options=opciones,
                                 value="Todo el periodo") if len(opciones) > 2 else "Todo el periodo")
    datos = actual if eleccion == "Todo el periodo" else actual[actual["mes"] == meses[opciones.index(eleccion) - 1]]
    if vista == "Perú":
        datos = datos[datos["mercado"] == "Nacional"]
    pares = I.por_par(datos)
    if not pares.empty:
        pares = pares[pares["vuelos_operados"] > 0].reset_index(drop=True)

    if pdk is None:
        st.warning("Falta la librería pydeck (viene con Streamlit): pip install pydeck")
    elif pares.empty:
        st.info("No hay vuelos operados para mostrar en el mapa con estos filtros.")
    else:
        columna, formato = METRICAS[metrica]
        lo, hi = pares[columna].min(), pares[columna].max()
        max_pax = max(pares["pasajeros"].max(), 1)
        arcos = pd.DataFrame({
            "desde": [lon_lat(a) for a in pares["a"]],
            "hacia": [lon_lat(b) for b in pares["b"]],
            "color": [color_de(v, metrica, lo, hi) for v in pares[columna]],
            "ancho": [1.5 + 10 * math.sqrt(p / max_pax) for p in pares["pasajeros"]],
            "titulo": pares["par"],
            "l1": [f"Pasajeros: {p:,.0f} · Vuelos: {v:,.0f}" for p, v in zip(pares["pasajeros"], pares["vuelos_operados"])],
            "l2": [f"Ingresos: {dinero(x)} ({pc:.1f}% del total)" for x, pc in zip(pares["ingresos"], pares["pct_ingresos"])],
            "l3": [f"Ocupación: {fmt(x, '{:.1f}%')}" for x in pares["ocupacion_pct"]],
            "l4": [f"Puntualidad: {fmt(x, '{:.1f}%')}" for x in pares["puntualidad_pct"]],
        })
        # aeropuertos: pasajeros que pasan por cada uno (llegan + salen)
        aero = (pd.concat([pares[["a", "pasajeros"]].rename(columns={"a": "iata"}),
                           pares[["b", "pasajeros"]].rename(columns={"b": "iata"})])
                .groupby("iata").agg(pasajeros=("pasajeros", "sum"), rutas=("pasajeros", "size"))
                .reset_index())
        escala = 1.0 if vista == "Mundo" else 0.25
        aero = aero.assign(
            pos=[lon_lat(i) for i in aero["iata"]],
            radio=[escala * (25000 + 160000 * math.sqrt(p / aero["pasajeros"].max())) for p in aero["pasajeros"]],
            titulo=[f"{i} · {CIUDADES.get(i, i)}" for i in aero["iata"]],
            l1=[f"Pasajeros (llegan + salen): {p:,.0f}" for p in aero["pasajeros"]],
            l2=[f"Rutas: {r}" for r in aero["rutas"]], l3="", l4="")

        capas = [
            pdk.Layer("ArcLayer", data=arcos, get_source_position="desde", get_target_position="hacia",
                      get_source_color="color", get_target_color="color", get_width="ancho",
                      get_height=0.45, great_circle=True, pickable=True, auto_highlight=True),
            pdk.Layer("ScatterplotLayer", data=aero, get_position="pos", get_radius="radio",
                      get_fill_color=[230, 237, 247, 200], get_line_color=[61, 156, 245, 255],
                      line_width_min_pixels=1, stroked=True, radius_min_pixels=3,
                      radius_max_pixels=28, pickable=True),
            pdk.Layer("TextLayer", data=aero, get_position="pos", get_text="iata", get_size=12,
                      get_color=[230, 237, 247, 230], get_pixel_offset=[0, -16],
                      font_weight="bold"),
        ]
        if vista == "Mundo":
            vista_ini = pdk.ViewState(latitude=6, longitude=-45, zoom=1.65, pitch=30, bearing=0)
        else:
            vista_ini = pdk.ViewState(latitude=-10, longitude=-75.5, zoom=4.4, pitch=40, bearing=-8)
        tooltip = {"html": "<b>{titulo}</b><br/>{l1}<br/>{l2}<br/>{l3}<br/>{l4}",
                   "style": {"backgroundColor": "#131c2e", "color": "#e6edf7", "fontSize": "12px",
                             "border": "1px solid #2a3b5c", "borderRadius": "8px"}}

        col_mapa, col_top = st.columns([3, 1.15])
        with col_mapa:
            deck = pdk.Deck(layers=capas, initial_view_state=vista_ini, tooltip=tooltip,
                            map_provider="carto", map_style="dark", height=560)
            try:
                st.pydeck_chart(deck, use_container_width=True, height=560)
            except TypeError:     # Streamlit antiguo (sin parametro height)
                st.pydeck_chart(deck, use_container_width=True)
            leyenda(metrica, lo, hi)
            st.caption(f"{eleccion} · {'Rutas nacionales' if vista == 'Perú' else 'Todas las rutas'} · "
                       "Ida y vuelta se muestran como un solo arco. Arrastra para mover, Ctrl + arrastrar "
                       "para rotar en 3D. Coordenadas aproximadas de los aeropuertos (no vienen en el dataset).")
        with col_top:
            st.markdown(f"**Ranking por {metrica.lower()}**")
            top = pares.sort_values(columna, ascending=False)[["par", columna]].head(12)
            if metrica == "Ingresos":
                top[columna] = top[columna] * FX / 1e6
                conf = st.column_config.ProgressColumn(f"{SIM} M", format="%.2f", min_value=0,
                                                       max_value=float(pares[columna].max() * FX / 1e6))
            elif metrica == "Pasajeros":
                conf = st.column_config.ProgressColumn("Pasajeros", format="%d", min_value=0,
                                                       max_value=int(pares[columna].max()))
            else:
                conf = st.column_config.ProgressColumn("%", format="%.1f", min_value=0, max_value=100)
            st.dataframe(top, hide_index=True, use_container_width=True, height=470,
                         column_config={"par": "Ruta", columna: conf})


# ----------------------------------------------------------------------
# Resumen
# ----------------------------------------------------------------------
with tab_res:
    m = SERIE.assign(ingresos=SERIE["ingresos"] * FX)
    st.subheader(f"Ingresos por {UNIDAD}")
    st.altair_chart(
        alt.Chart(m).mark_bar(color=AZUL, size=ANCHO_BARRA, cornerRadiusTopLeft=3,
                              cornerRadiusTopRight=3).encode(
            x=EJE_X,
            y=alt.Y("ingresos:Q", title=f"Ingresos ({moneda})", axis=alt.Axis(format="~s")),
            tooltip=[alt.Tooltip("periodo_txt:N", title=UNIDAD.capitalize()),
                     alt.Tooltip("ingresos:Q", title="Ingresos", format=",.0f"),
                     alt.Tooltip("pasajeros:Q", title="Pasajeros", format=",.0f")],
        ).properties(height=280), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader(f"Ocupación por {UNIDAD}")
        st.altair_chart(
            alt.Chart(m).mark_line(color=VERDE, point=True, strokeWidth=2).encode(
                x=EJE_X,
                y=alt.Y("ocupacion_pct:Q", title="Ocupación (%)", scale=alt.Scale(zero=False)),
                tooltip=[alt.Tooltip("periodo_txt:N", title=UNIDAD.capitalize()),
                         alt.Tooltip("ocupacion_pct:Q", title="Ocupación %", format=".1f")],
            ).properties(height=240), use_container_width=True)
    with col2:
        st.subheader(f"Puntualidad por {UNIDAD}")
        st.altair_chart(
            alt.Chart(m).mark_line(color=NARANJA, point=True, strokeWidth=2).encode(
                x=EJE_X,
                y=alt.Y("puntualidad_pct:Q", title="Vuelos puntuales (%)", scale=alt.Scale(zero=False)),
                tooltip=[alt.Tooltip("periodo_txt:N", title=UNIDAD.capitalize()),
                         alt.Tooltip("puntualidad_pct:Q", title="Puntualidad %", format=".1f")],
            ).properties(height=240), use_container_width=True)

    st.subheader(f"Comparativo anual (enero a {MESES_LARGOS[FECHA_CORTE.month - 1]}, "
                 "mismo periodo cada año)")
    comp = I.comparativo_anual(I.filtrar(base, rutas=rutas))
    comp["ingresos"] = comp["ingresos"] * FX
    st.dataframe(comp[["vuelos_operados", "pasajeros", "ingresos", "var_ingresos_pct",
                       "ocupacion_pct", "puntualidad_pct", "cancelacion_pct"]]
                 .rename(columns={"vuelos_operados": "Vuelos", "pasajeros": "Pasajeros",
                                  "ingresos": f"Ingresos ({moneda})", "var_ingresos_pct": "Var. ingresos %",
                                  "ocupacion_pct": "Ocupación %", "puntualidad_pct": "Puntualidad %",
                                  "cancelacion_pct": "Cancelación %"})
                 .style.format("{:,.1f}", na_rep="—"), use_container_width=True)

    va = I.ventas_anticipadas(vuelos)
    st.info(f"Ventas anticipadas (vuelos programados después del corte): {va['vuelos']} vuelos, "
            f"{va['boletos']:,} boletos, {SIM} {va['ingresos'] * FX:,.0f} ya vendidos "
            f"({va['ocupacion_pct']:.1f}% de ocupación).")


# ----------------------------------------------------------------------
# Calendario: ¿cuando se vuela mas?
# ----------------------------------------------------------------------
def calendario_anio(dias: pd.DataFrame, anio: int, columna: str, maximo: float, titulo: str):
    """Calendario tipo GitHub: columnas = semanas, filas = dias de la semana."""
    d = dias[dias["fecha"].dt.year == anio].copy()
    if d.empty:
        return
    ene1 = pd.Timestamp(anio, 1, 1)
    d["semana"] = ((d["fecha"] - ene1).dt.days + ene1.weekday()) // 7
    d["dia_sem"] = d["fecha"].dt.weekday.map(lambda i: DIAS_LARGOS[i][:3].capitalize())
    d["fecha_txt"] = [f"{DIAS_LARGOS[f.weekday()]} {dia_es(f)}" for f in d["fecha"]]
    # etiqueta de mes en la primera semana de cada mes
    inicios = {((pd.Timestamp(anio, mm, 1) - ene1).days + ene1.weekday()) // 7: MESES[mm - 1]
               for mm in range(1, 13)}
    expr = " : ".join(f"datum.value == {s} ? '{n}'" for s, n in inicios.items()) + " : ''"
    st.altair_chart(
        alt.Chart(d, title=str(anio)).mark_rect(cornerRadius=2, stroke=FONDO, strokeWidth=1.5).encode(
            x=alt.X("semana:O", title=None,
                    axis=alt.Axis(values=list(inicios), labelExpr=expr, labelAngle=0, ticks=False,
                                  domain=False)),
            y=alt.Y("dia_sem:O", title=None, sort=[x[:3].capitalize() for x in DIAS_LARGOS],
                    axis=alt.Axis(ticks=False, domain=False)),
            color=alt.Color(f"{columna}:Q", title=titulo,
                            scale=alt.Scale(domain=[0, maximo],
                                            range=["#16233a", "#1f4e8c", "#3d9cf5", "#9fd3ff"])),
            tooltip=[alt.Tooltip("fecha_txt:N", title="Fecha"),
                     alt.Tooltip("vuelos:Q", title="Vuelos"),
                     alt.Tooltip("pasajeros:Q", title="Pasajeros", format=",.0f"),
                     alt.Tooltip("ingresos:Q", title=f"Ingresos ({moneda})", format=",.0f")],
        ).properties(height=170), use_container_width=True)


with tab_cal:
    st.subheader("¿Cuándo se vuela más?")
    st.caption("Cada cuadrado es un día; más claro = más actividad. Pasa el mouse para ver la fecha. "
               "Los días sin vuelos quedan oscuros.")
    ver = st.radio("Mostrar", ["Pasajeros", "Vuelos", "Ingresos"], horizontal=True, key="cal_metrica")
    col_cal = {"Pasajeros": "pasajeros", "Vuelos": "vuelos", "Ingresos": "ingresos"}[ver]
    dias = I.por_dia(actual)
    dias["ingresos"] = dias["ingresos"] * FX
    todos = pd.DataFrame({"fecha": pd.date_range(pd.Timestamp(desde), pd.Timestamp(hasta), freq="D")})
    dias = todos.merge(dias, on="fecha", how="left").fillna({"vuelos": 0, "pasajeros": 0, "ingresos": 0})
    maximo = float(dias[col_cal].max()) or 1.0
    for anio in sorted(dias["fecha"].dt.year.unique()):
        calendario_anio(dias, int(anio), col_cal, maximo, ver)

    col1, col2 = st.columns([1.4, 1])
    with col1:
        st.markdown("**Los 10 días con más pasajeros**")
        top_dias = dias.sort_values(["pasajeros", "vuelos"], ascending=False).head(10).copy()
        top_dias["Fecha"] = [f"{DIAS_LARGOS[f.weekday()].capitalize()} {dia_es(f)}" for f in top_dias["fecha"]]
        st.dataframe(top_dias[["Fecha", "vuelos", "pasajeros", "ingresos"]], hide_index=True,
                     use_container_width=True,
                     column_config={
                         "vuelos": st.column_config.NumberColumn("Vuelos", format="%d"),
                         "pasajeros": st.column_config.ProgressColumn(
                             "Pasajeros", format="%d", min_value=0, max_value=int(dias["pasajeros"].max() or 1)),
                         "ingresos": st.column_config.NumberColumn(f"Ingresos ({moneda})", format="%.0f")})
    with col2:
        st.markdown("**Pasajeros promedio por día de la semana**")
        sem = (dias[dias["vuelos"] > 0].assign(dia=lambda d: d["fecha"].dt.weekday)
               .groupby("dia")["pasajeros"].mean().reindex(range(7)).reset_index())
        sem["nombre"] = [DIAS_LARGOS[i].capitalize() for i in sem["dia"]]
        st.altair_chart(
            alt.Chart(sem).mark_bar(color=AZUL, cornerRadiusEnd=3).encode(
                y=alt.Y("nombre:N", sort=[x.capitalize() for x in DIAS_LARGOS], title=None),
                x=alt.X("pasajeros:Q", title="Pasajeros por día (promedio)"),
                tooltip=["nombre", alt.Tooltip("pasajeros:Q", format=",.0f")],
            ).properties(height=260), use_container_width=True)


# ----------------------------------------------------------------------
# Rutas
# ----------------------------------------------------------------------
with tab_rutas:
    r = por_ruta.copy()
    r["ingresos"] = r["ingresos"] * FX
    r["ingreso_por_asiento"] = r["ingreso_por_asiento"] * FX
    st.subheader("Rutas por ingresos")
    # con 5 rutas o menos se muestran todas (el control necesita minimo < maximo)
    top = st.slider("Mostrar las primeras", 5, len(r), min(15, len(r))) if len(r) > 5 else len(r)
    st.altair_chart(
        alt.Chart(r.head(top)).mark_bar(color=AZUL, cornerRadiusEnd=3).encode(
            y=alt.Y("ruta:N", sort="-x", title=None),
            x=alt.X("ingresos:Q", title=f"Ingresos ({moneda})", axis=alt.Axis(format="~s")),
            tooltip=["ruta", alt.Tooltip("ingresos:Q", format=",.0f"),
                     alt.Tooltip("pct_ingresos:Q", title="% del total", format=".1f"),
                     alt.Tooltip("vuelos_operados:Q", title="Vuelos")],
        ).properties(height=max(200, 22 * min(top, len(r)))), use_container_width=True)

    st.subheader("Ocupación vs. puntualidad por ruta")
    st.caption("Cada punto es una ruta; el tamaño indica los ingresos. Arriba a la derecha: llenas y puntuales.")
    st.altair_chart(
        alt.Chart(r).mark_circle(color=AZUL, opacity=0.75, stroke=FONDO, strokeWidth=1).encode(
            x=alt.X("ocupacion_pct:Q", title="Ocupación (%)", scale=alt.Scale(zero=False)),
            y=alt.Y("puntualidad_pct:Q", title="Puntualidad (%)", scale=alt.Scale(zero=False)),
            size=alt.Size("ingresos:Q", legend=None, scale=alt.Scale(range=[40, 900])),
            tooltip=["ruta", alt.Tooltip("ocupacion_pct:Q", format=".1f"),
                     alt.Tooltip("puntualidad_pct:Q", format=".1f"),
                     alt.Tooltip("ingresos:Q", format=",.0f")],
        ).properties(height=380), use_container_width=True)

    st.caption(f"Montos en {moneda}.")
    st.dataframe(r[["ruta", "vuelos_operados", "pasajeros", "ingresos", "pct_ingresos",
                    "ocupacion_pct", "puntualidad_pct", "ingreso_por_asiento", "cancelados"]]
                 .style.format({"ingresos": "{:,.0f}", "pasajeros": "{:,.0f}",
                                "pct_ingresos": "{:.1f}", "ocupacion_pct": "{:.1f}",
                                "puntualidad_pct": "{:.1f}", "ingreso_por_asiento": "{:,.1f}",
                                "vuelos_operados": "{:,.0f}", "cancelados": "{:,.0f}"}),
                 use_container_width=True, hide_index=True)


# ----------------------------------------------------------------------
# Ventas
# ----------------------------------------------------------------------
def barras_mezcla(df, columna, titulo):
    df = df.assign(ingresos=df["ingresos"] * FX, precio_prom=df["precio_prom"] * FX)
    st.subheader(titulo)
    st.altair_chart(
        alt.Chart(df.reset_index()).mark_bar(color=AZUL, cornerRadiusEnd=3).encode(
            y=alt.Y(f"{columna}:N", sort="-x", title=None),
            x=alt.X("pct_ingresos:Q", title="% de los ingresos por boletos"),
            tooltip=[columna, alt.Tooltip("ingresos:Q", format=",.0f"),
                     alt.Tooltip("boletos:Q", format=",.0f"),
                     alt.Tooltip("precio_prom:Q", title=f"Precio prom. ({moneda})", format=",.1f")],
        ).properties(height=40 * len(df) + 40), use_container_width=True)


with tab_ventas:
    col1, col2 = st.columns(2)
    with col1:
        barras_mezcla(I.mezcla(v_act, "clase"), "clase", "Ingresos por clase")
        barras_mezcla(I.mezcla(v_act, "canal"), "canal", "Ingresos por canal de venta")
    with col2:
        barras_mezcla(I.mezcla(v_act, "tarifa"), "tarifa", "Ingresos por tarifa")
        st.subheader("Precio según anticipación de la compra")
        pa = (precio_antic * FX).rename("precio_prom").reset_index()
        st.altair_chart(
            alt.Chart(pa).mark_bar(color=NARANJA, cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
                x=alt.X("tramo_anticipacion:N", sort=A.ETIQUETAS_ANTICIPACION,
                        title="Días de anticipación"),
                y=alt.Y("precio_prom:Q", title=f"Precio promedio ({moneda})"),
                tooltip=[alt.Tooltip("precio_prom:Q", format=",.1f")],
            ).properties(height=260), use_container_width=True)
    st.caption(f"Ingresos por equipaje en el periodo: {SIM} {k['ingresos_equipaje'] * FX:,.0f} "
               f"({SIM} {35 * FX:,.2f} por maleta de bodega en tarifas sin equipaje).")


# ----------------------------------------------------------------------
# Operaciones
# ----------------------------------------------------------------------
with tab_oper:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Retraso promedio por día y hora")
        hm = A.retraso_hora_dia(punt).reset_index().melt(id_vars="franja", var_name="dia",
                                                          value_name="retraso")
        st.altair_chart(
            alt.Chart(hm).mark_rect(stroke=FONDO, strokeWidth=2, cornerRadius=3).encode(
                x=alt.X("dia:N", sort=A.DIAS, title=None),
                y=alt.Y("franja:N", title="Hora de salida"),
                color=alt.Color("retraso:Q", title="Min", scale=alt.Scale(scheme="orangered")),
                tooltip=["dia", "franja", alt.Tooltip("retraso:Q", format=".1f")],
            ).properties(height=300), use_container_width=True)
    with col2:
        st.subheader("Rutas con más retraso")
        rr = A.retraso_por_ruta(punt, min_vuelos=5).reset_index().head(12)
        st.altair_chart(
            alt.Chart(rr).mark_bar(color=NARANJA, cornerRadiusEnd=3).encode(
                y=alt.Y("ruta:N", sort="-x", title=None),
                x=alt.X("retraso_prom:Q", title="Retraso promedio (min)"),
                tooltip=["ruta", alt.Tooltip("retraso_prom:Q", format=".1f"),
                         alt.Tooltip("pct_retrasados:Q", title="% retrasados", format=".1f"),
                         alt.Tooltip("vuelos:Q")],
            ).properties(height=300), use_container_width=True)

    st.subheader(f"Cancelaciones por {UNIDAD}")
    st.altair_chart(
        alt.Chart(SERIE).mark_bar(color=ROJO, size=ANCHO_BARRA, cornerRadiusTopLeft=3,
                                  cornerRadiusTopRight=3).encode(
            x=EJE_X,
            y=alt.Y("cancelados:Q", title="Vuelos cancelados"),
            tooltip=[alt.Tooltip("periodo_txt:N", title=UNIDAD.capitalize()), "cancelados:Q",
                     alt.Tooltip("cancelacion_pct:Q", title=f"% del {UNIDAD}", format=".1f")],
        ).properties(height=220), use_container_width=True)


# ----------------------------------------------------------------------
# Clientes (todo el historico; no depende de los filtros)
# ----------------------------------------------------------------------
with tab_cli:
    st.caption("Esta pestaña usa todo el histórico de vuelos aterrizados (no aplica filtros, salvo la moneda).")
    niv = A.pasajeros_por_nivel(pax).reset_index()
    niv["gasto_prom_usd"] = niv["gasto_prom_usd"] * FX
    niv = niv.rename(columns={"gasto_prom_usd": f"gasto_prom_{moneda.lower()}"})
    largo = niv.melt(id_vars="nivel", value_vars=["pct_pasajeros", "pct_gasto"],
                     var_name="medida", value_name="pct")
    largo["medida"] = largo["medida"].map({"pct_pasajeros": "% de pasajeros", "pct_gasto": "% del gasto"})
    col1, col2 = st.columns([3, 2])
    with col1:
        st.subheader("Programa de millas: peso vs. gasto")
        st.altair_chart(
            alt.Chart(largo).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
                x=alt.X("nivel:N", sort=A.NIVELES, title=None),
                xOffset="medida:N",
                y=alt.Y("pct:Q", title="% del total"),
                color=alt.Color("medida:N", title=None,
                                scale=alt.Scale(range=[AZUL, NARANJA]),
                                legend=alt.Legend(orient="top")),
                tooltip=["nivel", "medida", alt.Tooltip("pct:Q", format=".1f")],
            ).properties(height=300), use_container_width=True)
    with col2:
        st.subheader("Gasto por nacionalidad")
        nac = ((pax.groupby("nacionalidad")["gasto_usd"].sum() * FX).sort_values(ascending=False)
                  .head(8).rename("gasto").reset_index())
        st.altair_chart(
            alt.Chart(nac).mark_bar(color=AZUL, cornerRadiusEnd=3).encode(
                y=alt.Y("nacionalidad:N", sort="-x", title=None),
                x=alt.X("gasto:Q", title=f"Gasto ({moneda})", axis=alt.Axis(format="~s")),
                tooltip=["nacionalidad", alt.Tooltip("gasto:Q", format=",.0f")],
            ).properties(height=300), use_container_width=True)
    st.dataframe(niv.set_index("nivel").style.format("{:,.1f}", na_rep="—"), use_container_width=True)
