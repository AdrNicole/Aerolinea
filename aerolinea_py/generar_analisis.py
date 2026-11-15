"""Genera todo el analisis: lee MySQL, calcula con pandas y guarda en
la carpeta salidas/:
    - 8 graficos PNG (01_... a 08_...)
    - analisis_aerolinea.xlsx con una hoja por tabla

Uso:  python generar_analisis.py
"""
from pathlib import Path

import pandas as pd

from aerolinea import analisis as A
from aerolinea import graficos as G
from aerolinea.config import CARPETA_SALIDAS


def formato_p(p: float) -> str:
    """p-valores tan chicos que se redondean a 0 se muestran como < 1e-300."""
    return "< 1e-300" if p == 0 else f"= {p:.1e}"


def ejecutar(repo=None, carpeta: Path = CARPETA_SALIDAS, imprimir: bool = True) -> dict:
    if repo is None:
        from aerolinea.repositorios import AnalisisRepository
        repo = AnalisisRepository()

    log = print if imprimir else (lambda *a, **k: None)
    log("Leyendo datos de MySQL...")
    punt = repo.puntualidad()
    ocup = repo.ocupacion()
    ventas = A.preparar_ventas(repo.ventas())
    pax = repo.pasajeros_millas()

    log("Calculando...")
    t = {
        "retraso_por_ruta": A.retraso_por_ruta(punt),
        "retraso_por_dia": A.retraso_por_dia(punt),
        "retraso_hora_dia": A.retraso_hora_dia(punt),
        "retraso_mensual": A.retraso_mensual(punt),
        "ocupacion_por_ruta": A.ocupacion_por_ruta(ocup),
        "ocupacion_mensual": A.ocupacion_mensual(ocup),
        "precio_anticipacion": A.curva_precio_anticipacion(ventas, "LIM-CUZ"),
        "pasajeros_por_nivel": A.pasajeros_por_nivel(pax),
        "ingresos_ruta_clase": A.ingresos_ruta_clase(ventas),
    }
    comp = A.comparar_anticipacion(ventas, "LIM-CUZ")
    cal = A.calibrar_factores_precio(ventas)
    t["compra_3_vs_30_por_tarifa"] = comp["por_tarifa"]

    log("Guardando graficos...")
    graficos = [
        G.retraso_por_dia(t["retraso_por_dia"], carpeta),
        G.retraso_hora_dia(t["retraso_hora_dia"], carpeta),
        G.retraso_mensual(t["retraso_mensual"], carpeta),
        G.retraso_por_ruta(t["retraso_por_ruta"], carpeta),
        G.ocupacion_por_ruta(t["ocupacion_por_ruta"], carpeta),
        G.precio_anticipacion(t["precio_anticipacion"], "LIM-CUZ", carpeta),
        G.comparacion_3_vs_30(comp, carpeta),
        G.pasajeros_por_nivel(t["pasajeros_por_nivel"], carpeta),
    ]

    excel = carpeta / "analisis_aerolinea.xlsx"
    with pd.ExcelWriter(excel) as w:
        resumen = pd.DataFrame({
            "indicador": ["Precio prom. 0-3 dias (LIM-CUZ)", "Precio prom. 28-32 dias (LIM-CUZ)",
                          "Veces mas caro", "p-valor Mann-Whitney", "R2 modelo de precios (log)",
                          "Factor temporada alta"],
            "valor": [comp["prom_corto"], comp["prom_largo"], comp["veces"],
                      comp["p_mann_whitney"], cal["r2_log"], cal["temporada_alta"]],
        })
        resumen.to_excel(w, sheet_name="resumen", index=False)
        for nombre, df in t.items():
            df.to_excel(w, sheet_name=nombre[:31])
        pd.DataFrame(cal["anticipacion"], columns=["hasta_dias", "factor"]).to_excel(
            w, sheet_name="factores_anticipacion", index=False)
        pd.DataFrame(cal["ocupacion"], columns=["hasta_ocupacion", "factor"]).to_excel(
            w, sheet_name="factores_ocupacion", index=False)

    d = t["retraso_por_dia"]["retraso_prom"]
    log("\n=== HALLAZGOS PRINCIPALES ===")
    log(f"- Peor dia: {d.idxmax()} ({d.max()} min); mejor: {d.idxmin()} ({d.min()} min)")
    r = t["retraso_por_ruta"].iloc[0]
    log(f"- Ruta con mas retraso: {t['retraso_por_ruta'].index[0]} ({r.retraso_prom} min, "
        f"{r.pct_retrasados}% de vuelos retrasados)")
    log(f"- {comp['ruta']}: comprar con 0-3 dias cuesta {comp['prom_corto']} USD vs "
        f"{comp['prom_largo']} con 28-32 dias -> {comp['veces']} veces "
        f"(Mann-Whitney p {formato_p(comp['p_mann_whitney'])})")
    log(f"- Modelo de precios: R2 = {cal['r2_log']}, temporada alta x{cal['temporada_alta']}")
    n = t["pasajeros_por_nivel"]
    log(f"- Platino: {n.loc['Platino', 'pct_pasajeros']}% de los pasajeros y "
        f"{n.loc['Platino', 'pct_gasto']}% del gasto")
    log(f"\nArchivos en: {carpeta}")
    return {"tablas": t, "comparacion": comp, "calibracion": cal,
            "graficos": graficos, "excel": excel}


if __name__ == "__main__":
    ejecutar()
