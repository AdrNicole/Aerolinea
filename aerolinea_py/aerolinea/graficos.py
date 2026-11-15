"""Graficos con Matplotlib/Seaborn (PNG para el informe).

Criterios: un solo eje Y por grafico, marcas finas, cuadricula tenue,
color por funcion (un solo tono para magnitudes, tonos distintos solo
para series distintas) y etiquetas de valor solo donde ayudan.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # genera archivos sin abrir ventanas
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap

# Paleta (tema claro)
AZUL, NARANJA, AGUA = "#2a78d6", "#eb6834", "#1baf7a"
AZUL_OSCURO = "#184f95"
TINTA, TINTA_2, TENUE = "#0b0b0b", "#52514e", "#898781"
GRILLA, BASE, FONDO = "#e1e0d9", "#c3c2b7", "#fcfcfb"
SECUENCIAL = LinearSegmentedColormap.from_list(
    "azules", ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])
SERIES = [AZUL, NARANJA, AGUA]


def _estilo():
    plt.rcParams.update({
        "figure.facecolor": FONDO, "axes.facecolor": FONDO, "savefig.facecolor": FONDO,
        "axes.edgecolor": BASE, "axes.labelcolor": TINTA_2, "axes.titlecolor": TINTA,
        "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.labelsize": 10, "xtick.color": TENUE, "ytick.color": TENUE,
        "xtick.labelsize": 9, "ytick.labelsize": 9, "axes.grid": True,
        "grid.color": GRILLA, "grid.linewidth": 0.6, "axes.spines.top": False,
        "axes.spines.right": False, "legend.frameon": False, "legend.fontsize": 9,
        "font.family": "DejaVu Sans",
    })


def _guardar(fig, carpeta: Path, nombre: str) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{nombre}.png"
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    return ruta


def _subtitulo(ax, texto):
    ax.text(0, 1.02, texto, transform=ax.transAxes, color=TINTA_2, fontsize=9, va="bottom")


# ----------------------------------------------------------------------
def retraso_por_dia(tabla: pd.DataFrame, carpeta: Path) -> Path:
    _estilo()
    fig, ax = plt.subplots(figsize=(8, 4.2))
    peores = tabla["retraso_prom"].nlargest(2).index
    colores = [AZUL_OSCURO if d in peores else AZUL for d in tabla.index]
    barras = ax.bar(tabla.index.astype(str), tabla["retraso_prom"], color=colores, width=0.6)
    ax.bar_label(barras, fmt="%.1f", color=TINTA_2, fontsize=9, padding=3)
    ax.set_ylabel("Retraso promedio (min)")
    ax.grid(axis="x", visible=False)
    ax.set_title("Viernes y domingo son los días con más retraso", pad=22)
    _subtitulo(ax, "Retraso promedio de salida por día de la semana, vuelos aterrizados 2024-2026")
    return _guardar(fig, carpeta, "01_retraso_por_dia")


def retraso_hora_dia(pivot: pd.DataFrame, carpeta: Path) -> Path:
    _estilo()
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    sns.heatmap(pivot, ax=ax, cmap=SECUENCIAL, annot=True, fmt=".1f", linewidths=2,
                linecolor=FONDO, cbar_kws={"label": "Retraso promedio (min)", "shrink": 0.8},
                annot_kws={"fontsize": 8})
    ax.set_xlabel(""); ax.set_ylabel("Hora de salida programada")
    ax.grid(False)
    ax.set_title("El retraso crece a lo largo del día", pad=22)
    _subtitulo(ax, "Retraso promedio (min) por franja horaria y día de la semana")
    return _guardar(fig, carpeta, "02_retraso_hora_dia")


def retraso_mensual(serie: pd.DataFrame, carpeta: Path) -> Path:
    _estilo()
    fig, ax = plt.subplots(figsize=(9, 4.2))
    # sombrear meses de lluvia (dic-mar)
    for fecha, lluvia in serie["lluvias"].items():
        if lluvia:
            ax.axvspan(fecha, fecha + pd.offsets.MonthBegin(1), color="#f0efec", lw=0, zorder=0)
    ax.plot(serie.index, serie["retraso_prom"], color=AZUL, lw=1.5, marker="o", ms=3,
            label="Promedio mensual")
    ax.plot(serie.index, serie["media_movil_3m"], color=NARANJA, lw=2,
            label="Media móvil 3 meses")
    ax.set_ylabel("Retraso promedio (min)")
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper right")
    ax.set_title("Más retraso en la temporada de lluvias", pad=22)
    _subtitulo(ax, "Retraso promedio mensual; franjas grises = diciembre a marzo")
    return _guardar(fig, carpeta, "03_retraso_mensual")


def _barras_h(serie: pd.Series, titulo, subtitulo, xlabel, fmt, carpeta, nombre, top=12):
    _estilo()
    s = serie.head(top)[::-1]
    fig, ax = plt.subplots(figsize=(8, 0.38 * len(s) + 1.4))
    barras = ax.barh(s.index, s.values, color=AZUL, height=0.6)
    ax.bar_label(barras, fmt=fmt, color=TINTA_2, fontsize=8, padding=3)
    ax.set_xlabel(xlabel); ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", colors=TINTA_2)
    ax.set_title(titulo, pad=22); _subtitulo(ax, subtitulo)
    return _guardar(fig, carpeta, nombre)


def retraso_por_ruta(tabla: pd.DataFrame, carpeta: Path) -> Path:
    return _barras_h(tabla["retraso_prom"], "Rutas con más retraso",
                     "Retraso promedio de salida (min), rutas con 10+ vuelos",
                     "Retraso promedio (min)", "%.1f", carpeta, "04_retraso_por_ruta")


def ocupacion_por_ruta(tabla: pd.DataFrame, carpeta: Path) -> Path:
    return _barras_h(tabla["ocupacion_prom"], "Rutas con mayor factor de ocupación",
                     "Ocupación promedio (% de asientos vendidos), vuelos aterrizados",
                     "Ocupación promedio (%)", "%.1f", carpeta, "05_ocupacion_por_ruta")


def precio_anticipacion(pivot: pd.DataFrame, ruta: str, carpeta: Path) -> Path:
    _estilo()
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    x = range(len(pivot.index))
    for color, clase in zip(SERIES, pivot.columns):
        ax.plot(x, pivot[clase], color=color, lw=2, marker="o", ms=4, label=clase)
        ax.annotate(clase, (len(x) - 1, pivot[clase].iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=8, color=TINTA_2)
    ax.set_xticks(list(x), pivot.index.astype(str))
    ax.set_xlabel("Días de anticipación de la compra")
    ax.set_ylabel("Precio promedio (USD)")
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper right")
    ax.set_title(f"Comprar a último momento cuesta mucho más ({ruta})", pad=22)
    _subtitulo(ax, "Precio promedio del boleto por días de anticipación y clase")
    return _guardar(fig, carpeta, "06_precio_vs_anticipacion")


def comparacion_3_vs_30(res: dict, carpeta: Path) -> Path:
    _estilo()
    t = res["por_tarifa"].sort_values(res["por_tarifa"].columns[1])
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    x = range(len(t))
    ancho = 0.38
    b1 = ax.bar([i - ancho / 2 for i in x], t.iloc[:, 1], ancho, color=AZUL,
                label="Compra con 28-32 días", edgecolor=FONDO, linewidth=1.5)
    b2 = ax.bar([i + ancho / 2 for i in x], t.iloc[:, 0], ancho, color=NARANJA,
                label="Compra con 0-3 días", edgecolor=FONDO, linewidth=1.5)
    ax.bar_label(b2, labels=[f"{v:.1f}x" for v in t["veces"]], color=TINTA_2,
                 fontsize=8, padding=3)
    ax.set_xticks(list(x), t.index)
    ax.set_ylabel("Precio promedio (USD)")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left")
    ax.set_title(f"{res['ruta']}: comprar 3 días antes cuesta {res['veces']:.1f} veces más",
                 pad=22)
    _subtitulo(ax, "Precio promedio por tarifa; la etiqueta indica cuántas veces más cuesta")
    return _guardar(fig, carpeta, "07_compra_3_vs_30_dias")


def pasajeros_por_nivel(tabla: pd.DataFrame, carpeta: Path) -> Path:
    _estilo()
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x = range(len(tabla))
    ancho = 0.38
    b1 = ax.bar([i - ancho / 2 for i in x], tabla["pct_pasajeros"], ancho, color=AZUL,
                label="% de pasajeros", edgecolor=FONDO, linewidth=1.5)
    b2 = ax.bar([i + ancho / 2 for i in x], tabla["pct_gasto"], ancho, color=NARANJA,
                label="% del gasto", edgecolor=FONDO, linewidth=1.5)
    for b in (b1, b2):
        ax.bar_label(b, fmt="%.0f%%", color=TINTA_2, fontsize=8, padding=3)
    ax.set_xticks(list(x), tabla.index.astype(str))
    ax.set_ylabel("Porcentaje del total")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper right")
    ax.set_title("Los niveles altos gastan mucho más de lo que pesan", pad=22)
    _subtitulo(ax, "Participación en pasajeros y en gasto por nivel del programa de millas")
    return _guardar(fig, carpeta, "08_pasajeros_por_nivel")
