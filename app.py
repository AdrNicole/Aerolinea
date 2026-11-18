"""
app.py - SOLO la interfaz (Streamlit). Aquí NO hay SQL ni conexiones:
todo dato se pide a un Repository (db_sqlalchemy.py y los que agreguen).

Ejecutar:   py -m streamlit run app.py
"""
import pandas as pd
import streamlit as st
from datetime import date, datetime
from zoneinfo import ZoneInfo

from db_sqlalchemy import (
    AeropuertoRepository, VueloRepository, TarifaCatalogoRepository,
    AsientoRepository, MapaAsientosRepository,
)
from servicio_precios import ServicioPrecios, total_en_moneda, ultimo_ipc_disponible
from reportes import ReporteVuelo

st.set_page_config(page_title="Aerolínea", page_icon="✈️", layout="wide")


# ---------- datos (con caché para no consultar en cada clic) ----------
@st.cache_data(ttl=600)
def cargar_aeropuertos() -> pd.DataFrame:
    return AeropuertoRepository().listar()


# ---------- pantalla 1: búsqueda y selección de pasajeros / trayecto ----------
# No se mezclan SQL ni conexiones con los elementos visuales.
ZONA_HORARIA = ZoneInfo("America/Lima")
@st.cache_data(ttl=120)
def cargar_fechas_disponibles(origen, destino, plazas, minuto_consulta):
    """Obtiene del repository los días reservables de los próximos 365 días."""
    return VueloRepository().fechas_disponibles(
        origen, destino, pasajeros=plazas,
        momento_actual=minuto_consulta, horizonte_dias=365,
    )


def _actualizar_busqueda_por_fecha():
    """Marca un cambio de fecha para consultar vuelos en el siguiente rerun."""
    st.session_state["actualizar_busqueda_por_fecha"] = True


def _elegir_fecha(clave_fecha, valor):
    """Actualiza el calendario nativo y solicita buscar esa fecha automáticamente."""
    st.session_state[clave_fecha] = valor
    _actualizar_busqueda_por_fecha()


def selector_calendario(titulo, clave_fecha, min_fecha, fechas_con_vuelos):
    """Selector nativo de Streamlit; muestra fechas disponibles como texto aparte.

    st.date_input no permite sombrear días individualmente sin sustituir
    el calendario nativo por un componente personalizado.
    """
    valor = st.session_state.get(clave_fecha)
    if not isinstance(valor, date) or valor < min_fecha:
        # El valor debe corregirse antes de instanciar el widget con su key.
        st.session_state[clave_fecha] = min_fecha

    fecha_elegida = st.date_input(
        titulo,
        min_value=min_fecha,
        key=clave_fecha,
        format="DD/MM/YYYY",
        on_change=_actualizar_busqueda_por_fecha,
    )

    proximas = sorted(d for d in fechas_con_vuelos if d >= min_fecha)
    if proximas:
        resumen = ", ".join(f"{d:%d/%m/%Y}" for d in proximas[:5])
        st.caption(f"Próximas fechas con vuelos y plazas: {resumen}")
    else:
        st.caption("No hay fechas con plazas disponibles en los próximos 365 días para esta ruta.")
    return fecha_elegida


def _abrir_detalle(id_vuelo, numero_vuelo, fecha):
    """Conserva el detalle histórico para los siguientes pasos del proyecto."""
    st.session_state["vuelo_detalle"] = {
        "id_vuelo": id_vuelo, "numero_vuelo": numero_vuelo, "fecha": fecha,
    }
    st.session_state["d_numero"] = ""
    st.session_state["menu"] = "Detalle de vuelo"


def _intercambiar_aeropuertos():
    origen = st.session_state["origen_busqueda"]
    st.session_state["origen_busqueda"] = st.session_state["destino_busqueda"]
    st.session_state["destino_busqueda"] = origen


def _seleccionar_resultado(tramo, id_vuelo):
    """Guarda una fila concreta sin iniciar aún la compra."""
    seleccion = dict(st.session_state.get("selecciones_vuelos", {}))
    seleccion[tramo] = int(id_vuelo)
    st.session_state["selecciones_vuelos"] = seleccion


def _iniciar_comparacion(tramos, pasajeros, tipo, preferencia):
    """Crea un itinerario temporal, sin INSERT, bloqueo de plazas ni pagos."""
    ids = st.session_state.get("selecciones_vuelos", {})
    if not all(nombre in ids for nombre in tramos):
        return
    st.session_state["itinerario"] = {
        "tramos": [{"nombre": nombre, "id_vuelo": ids[nombre]} for nombre in tramos],
        "indice": 0,
        "pasajeros": pasajeros,
        "tipo": tipo,
        "preferencia": preferencia,
        "tarifas": {},
        "asientos": {},
        "resumen_listo": False,
    }
    st.session_state.pop("d_numero", None)
    st.session_state["menu"] = "Comparar tarifas"


def _elegir_tarifa(indice, tarifa, precio):
    viaje = st.session_state["itinerario"]
    tarifas = dict(viaje["tarifas"])
    tarifas[indice] = {
        "id_tarifa": int(tarifa["id_tarifa"]),
        "clase": str(tarifa["clase"]),
        "nombre": str(tarifa["nombre"]),
        "equipaje_incluido": bool(tarifa["equipaje_incluido"]),
        "reembolsable": bool(tarifa["reembolsable"]),
        "precio_usd": precio["precio_usd"],
        "precio_pen": precio["precio_pen"],
        "tipo_cambio": float(precio["tipo_cambio"]),
        "ipc_periodo": precio["ipc_periodo"],
        "ipc_valor": float(precio["ipc_valor"]),
        "multiplicador": precio["multiplicador"],
        "dias_anticipacion": precio["dias_anticipacion"],
        "ocupacion_pct": precio["ocupacion_pct"],
    }
    viaje["tarifas"] = tarifas
    # Tras modificar la tarifa se solicita confirmar nuevamente los asientos.
    viaje["asientos"].pop(indice, None)
    st.session_state["itinerario"] = viaje
    st.session_state["menu"] = "Plaza"


def _alternar_asiento(indice, asiento):
    viaje = st.session_state["itinerario"]
    actuales = list(viaje["asientos"].get(indice, []))
    if asiento in actuales:
        actuales.remove(asiento)
    elif len(actuales) < viaje["pasajeros"]:
        actuales.append(asiento)
    viaje["asientos"][indice] = actuales
    st.session_state["itinerario"] = viaje


def _continuar_tramo(indice):
    viaje = st.session_state["itinerario"]
    cantidad = viaje["pasajeros"]
    vuelo = viaje["tramos"][indice]["id_vuelo"]
    ocupados = set(MapaAsientosRepository().ocupados(vuelo)["asiento"].astype(str))
    elegidos = viaje["asientos"].get(indice, [])
    info = VueloRepository().informacion_vuelo(vuelo)
    ahora = datetime.now(ZONA_HORARIA).replace(tzinfo=None)
    if (len(elegidos) != cantidad or any(a in ocupados for a in elegidos)
            or info.empty or info.iloc[0]["estado"] != "programado"
            or pd.Timestamp(info.iloc[0]["salida_prog"]) <= ahora):
        st.session_state["error_plazas"] = (
            "La disponibilidad cambió o el vuelo ya no es reservable. "
            "Revisa los asientos y vuelve a intentarlo."
        )
        return
    if indice + 1 < len(viaje["tramos"]):
        viaje["indice"] = indice + 1
        st.session_state["itinerario"] = viaje
        st.session_state["menu"] = "Comparar tarifas"
    else:
        viaje["resumen_listo"] = True
        st.session_state["itinerario"] = viaje
        st.session_state["menu"] = "Detalle de vuelo"


def _volver_a_comparar():
    st.session_state["menu"] = "Comparar tarifas"


def _volver_a_buscar():
    st.session_state["menu"] = "Buscar vuelos"


def _mostrar_tramo(nombre, df, fecha, origen, destino,
                   fechas_posibles=None, clave_fecha=None, fecha_minima=None):
    st.subheader(nombre)
    if df.empty:
        st.info(f"No hay vuelos reservables de {origen} a {destino} el "
                f"{fecha:%d/%m/%Y}, con las plazas solicitadas.")
        alternativas = sorted(
            (d for d in (fechas_posibles or set())
             if d != fecha and (fecha_minima is None or d >= fecha_minima)),
            key=lambda d: (abs((d - fecha).days), d),
        )[:5]
        if alternativas and clave_fecha:
            st.caption("Fechas cercanas con plazas (pulsa una para actualizar la búsqueda):")
            opciones = st.columns(len(alternativas))
            for columna, alternativa in zip(opciones, alternativas):
                columna.button(f"{alternativa:%d/%m/%Y}",
                               key=f"alternativa_{nombre}_{alternativa.isoformat()}",
                               on_click=_elegir_fecha, args=(clave_fecha, alternativa),
                               use_container_width=True)
        return

    salida = pd.to_datetime(df["salida_prog"])
    llegada = pd.to_datetime(df["llegada_prog"])
    tabla = pd.DataFrame({
        "Vuelo": df["numero_vuelo"],
        "Ruta": df["ciudad_origen"] + " (" + df["origen"] + ") → "
                + df["ciudad_destino"] + " (" + df["destino"] + ")",
        "Fecha": salida.dt.strftime("%d/%m/%Y"),
        "Salida": salida.dt.strftime("%H:%M"),
        "Llegada programada": llegada.dt.strftime("%d/%m %H:%M"),
        "Plazas libres": df["asientos_disponibles"].astype(int),
    })
    evento = st.dataframe(
        tabla, hide_index=True, width="stretch", on_select="rerun",
        selection_mode="single-row",
        key=f"seleccion_{nombre}_{fecha.isoformat()}_{origen}_{destino}",
    )
    seleccion = evento.selection.rows
    if seleccion:
        pos = seleccion[0]
        st.button(f"Elegir vuelo {df.iloc[pos]['numero_vuelo']} · "
                  f"{salida.iloc[pos]:%H:%M}",
                  key=f"elegir_{nombre}_{int(df.iloc[pos]['id_vuelo'])}",
                  on_click=_seleccionar_resultado,
                  args=(nombre, int(df.iloc[pos]["id_vuelo"])), type="primary")
    elegido = st.session_state.get("selecciones_vuelos", {}).get(nombre)
    if elegido is not None and elegido in df["id_vuelo"].to_numpy():
        registro = df.loc[df["id_vuelo"] == elegido].iloc[0]
        st.success(f"{nombre}: seleccionado {registro['numero_vuelo']}. "
                   "Puedes elegir otro vuelo antes de continuar.")
    st.caption("Se muestran como máximo 30 vuelos por tramo. "
               "Las categorías y los precios se comparan en el paso siguiente.")



def pantalla_buscar_vuelos():
    st.markdown("#### ✈️ Arma tu viaje  ·  Vuelos")
    ahora = datetime.now(ZONA_HORARIA).replace(tzinfo=None)
    # Fecha/hora real del servidor en Lima; NO se muestra como filtro al cliente.
    minuto_consulta = ahora.replace(second=0, microsecond=0)
    hoy = ahora.date()

    aeropuertos = cargar_aeropuertos()
    if aeropuertos.empty:
        st.error("No se encontraron aeropuertos en la base de datos.")
        return
    opciones = dict(zip(aeropuertos["codigo_iata"],
                        aeropuertos["ciudad"] + " (" + aeropuertos["codigo_iata"] + ")"))
    claves = list(opciones)
    if "origen_busqueda" not in st.session_state:
        st.session_state["origen_busqueda"] = "LIM" if "LIM" in opciones else claves[0]
    if "destino_busqueda" not in st.session_state:
        st.session_state["destino_busqueda"] = (
            "CUZ" if "CUZ" in opciones and st.session_state["origen_busqueda"] != "CUZ"
            else next((iata for iata in claves if iata != st.session_state["origen_busqueda"]), claves[0])
        )

    with st.container(border=True):
        encab, eleccion = st.columns([1.2, 2], vertical_alignment="center")
        with encab:
            st.markdown("### ¿A dónde quieres ir?")
        with eleccion:
            tipo = st.radio("Tipo de viaje",
                            ["Ida y vuelta", "Solo ida", "Multidestino"],
                            horizontal=True, key="tipo_viaje", label_visibility="collapsed")

        c_origen, c_cambio, c_destino = st.columns([5, 1, 5], vertical_alignment="bottom")
        with c_origen:
            st.selectbox("Desde", claves, format_func=opciones.get, key="origen_busqueda")
        with c_cambio:
            st.button("⇄", help="Intercambiar origen y destino", on_click=_intercambiar_aeropuertos,
                      use_container_width=True)
        with c_destino:
            st.selectbox("Hacia", claves, format_func=opciones.get, key="destino_busqueda")

        origen = st.session_state["origen_busqueda"]
        destino = st.session_state["destino_busqueda"]
        col_cabina, col_ida, col_vuelta = st.columns([2, 1, 1])
        with col_cabina:
            cabina = st.selectbox("Cabina", ["Económica", "Premium Economy", "Business"],
                                  key="cabina_busqueda")

        plazas = (st.session_state.get("n_adultos", 1)
                  + st.session_state.get("n_ninos", 0)
                  + st.session_state.get("n_bebes", 0))
        plazas = min(9, max(1, plazas))

        fechas_ida_df = cargar_fechas_disponibles(origen, destino, plazas, minuto_consulta) \
            if origen != destino else pd.DataFrame(columns=["fecha"])
        fechas_ida = set(pd.to_datetime(fechas_ida_df["fecha"]).dt.date)
        with col_ida:
            st.write("**Ida**")
            ida = selector_calendario("Ida", "fecha_ida", hoy, fechas_ida)

        vuelta = None
        destino_final = None
        fechas_vuelta = set()
        if tipo != "Solo ida":
            if tipo == "Ida y vuelta":
                siguiente_origen, siguiente_destino = destino, origen
            else:
                ultimo = [c for c in claves if c not in (origen, destino)]
                if "destino_final_busqueda" not in st.session_state:
                    st.session_state["destino_final_busqueda"] = ultimo[0] if ultimo else origen
                siguiente_origen = destino
                siguiente_destino = st.session_state["destino_final_busqueda"]
            fechas_vuelta_df = cargar_fechas_disponibles(
                siguiente_origen, siguiente_destino, plazas, minuto_consulta,
            ) if siguiente_origen != siguiente_destino else pd.DataFrame(columns=["fecha"])
            fechas_vuelta = set(pd.to_datetime(fechas_vuelta_df["fecha"]).dt.date)
            with col_vuelta:
                st.write("**Vuelta**" if tipo == "Ida y vuelta" else "**Segundo tramo**")
                vuelta = selector_calendario("Vuelta" if tipo == "Ida y vuelta" else "Tramo 2",
                                             "fecha_vuelta", ida, fechas_vuelta)

        c_pasajeros, c_promo = st.columns(2)
        with c_pasajeros:
            with st.popover(f"👥 Pasajeros: {plazas}", use_container_width=True):
                st.number_input("Adultos", min_value=1, max_value=9, value=1,
                                step=1, key="n_adultos")
                st.number_input("Niños", min_value=0, max_value=8, value=0,
                                step=1, key="n_ninos")
                st.number_input("Bebés", min_value=0, max_value=8, value=0,
                                step=1, key="n_bebes")
                st.caption("Prototipo: se reserva una plaza por persona, incluidos bebés. "
                           "Todavía no hay reglas especiales por edad en la BD.")
        with c_promo:
            st.text_input("Código promocional", placeholder="No disponible todavía",
                          disabled=True)

        if tipo == "Multidestino":
            st.caption("Multidestino: esta etapa admite dos tramos consecutivos; "
                       "la reserva conjunta se implementará más adelante.")
            col_dest_final, _ = st.columns([1, 1])
            with col_dest_final:
                destino_final = st.selectbox("Destino del segundo tramo", claves,
                                            format_func=opciones.get,
                                            key="destino_final_busqueda")
                # El destino del segundo tramo acaba de elegirse: se obtiene de la misma clave

        st.divider()
        zona_millas, zona_buscar = st.columns([3, 1], vertical_alignment="center")
        with zona_millas:
            st.checkbox("Usar millas + dinero (próxima etapa)", disabled=True)
        with zona_buscar:
            buscar = st.button("🔍 Buscar vuelos", type="primary", use_container_width=True)

    if not fechas_ida:
        st.caption("No hay fechas con plazas para esta ruta dentro de los próximos 365 días "
                   "con la base de datos actualmente cargada.")
    st.caption("La cabina se conserva como preferencia. No existe un inventario de "
               "plazas separado por clase en los datos; se seleccionará la tarifa después.")

    total_pasajeros = (st.session_state.get("n_adultos", 1)
                       + st.session_state.get("n_ninos", 0)
                       + st.session_state.get("n_bebes", 0))
    destino_vuelta = origen if tipo == "Ida y vuelta" else destino_final
    firma = (tipo, origen, destino, ida, vuelta, destino_vuelta, cabina, total_pasajeros)

    # Los widgets con on_change y los botones de fechas alternativas activan
    # una nueva búsqueda sin exigir otro clic en «Buscar vuelos».
    actualizar_por_fecha = st.session_state.pop("actualizar_busqueda_por_fecha", False)
    if buscar or actualizar_por_fecha:
        st.session_state.pop("resultados_busqueda", None)
        if buscar:
            # Una búsqueda manual inicia una selección nueva de vuelos.
            st.session_state["selecciones_vuelos"] = {}
        # Un cambio de fechas invalida un itinerario temporal ya cotizado,
        # pero conservamos la elección del otro tramo si aún existe.
        st.session_state.pop("itinerario", None)
        if origen == destino:
            st.warning("El origen y el destino deben ser distintos.")
            return
        if total_pasajeros > 9:
            st.warning("En esta etapa se admiten como máximo 9 pasajeros por búsqueda.")
            return
        if vuelta is not None and vuelta < ida:
            st.warning("La segunda fecha no puede ser anterior a la primera.")
            return
        if tipo == "Multidestino" and destino_final == destino:
            st.warning("El segundo tramo debe tener aeropuertos de origen y destino distintos.")
            return
        if tipo == "Multidestino" and destino_final is None:
            st.warning("Selecciona el destino del segundo tramo.")
            return

        repositorio = VueloRepository()
        resultado_ida = repositorio.vuelos_disponibles(
            origen, destino, ida, pasajeros=total_pasajeros,
            momento_actual=ahora, limite=30,
        )
        resultado_vuelta = None
        if vuelta is not None:
            resultado_vuelta = repositorio.vuelos_disponibles(
                destino, destino_vuelta, vuelta, pasajeros=total_pasajeros,
                momento_actual=ahora, limite=30,
            )
        st.session_state["resultados_busqueda"] = {
            "firma": firma, "ida": resultado_ida, "vuelta": resultado_vuelta,
        }
        # Evita conservar selecciones de una fecha anterior. Cuando cambia
        # solo la vuelta, por ejemplo, la ida ya elegida permanece seleccionada.
        nombres_tramos = {"Ida": resultado_ida}
        if resultado_vuelta is not None:
            nombres_tramos["Vuelta" if tipo == "Ida y vuelta" else "Segundo tramo"] = resultado_vuelta
        selecciones_previas = st.session_state.get("selecciones_vuelos", {})
        st.session_state["selecciones_vuelos"] = {
            tramo: id_vuelo
            for tramo, id_vuelo in selecciones_previas.items()
            if tramo in nombres_tramos
            and id_vuelo in nombres_tramos[tramo]["id_vuelo"].to_numpy()
        }

    res = st.session_state.get("resultados_busqueda")
    if res is None or res["firma"] != firma:
        return  # Evita mostrar datos de una búsqueda anterior con nuevos filtros.
    st.subheader("Resultados de la búsqueda")
    st.caption(f"{tipo} · {total_pasajeros} pasajero(s) · cabina preferida: {cabina}")
    _mostrar_tramo("Ida", res["ida"], ida, origen, destino,
                   fechas_posibles=fechas_ida, clave_fecha="fecha_ida")
    if res["vuelta"] is not None:
        _mostrar_tramo("Vuelta" if tipo == "Ida y vuelta" else "Segundo tramo",
                      res["vuelta"], vuelta, destino, destino_vuelta,
                      fechas_posibles=fechas_vuelta, clave_fecha="fecha_vuelta",
                      fecha_minima=ida)

    nombres = ["Ida"]
    if res["vuelta"] is not None:
        nombres.append("Vuelta" if tipo == "Ida y vuelta" else "Segundo tramo")
    elegidos = st.session_state.get("selecciones_vuelos", {})
    completos = all(nombre in elegidos and elegidos[nombre] in
                    (res["ida"] if nombre == "Ida" else res["vuelta"])["id_vuelo"].to_numpy()
                    for nombre in nombres)
    st.button("Comparar categorías y tarifas", type="primary",
              disabled=not completos, on_click=_iniciar_comparacion,
              args=(nombres, total_pasajeros, tipo, cabina))
    if not completos:
        st.caption("Selecciona un vuelo por cada tramo para continuar.")


# ---------- pantalla 2: comparación de categorías con Strategy ----------
@st.cache_data(ttl=600)
def cargar_tarifas_catalogo():
    return TarifaCatalogoRepository().listar()


@st.cache_data(ttl=600)
def cargar_asientos_modelo(id_vuelo):
    return MapaAsientosRepository().etiquetas_modelo(id_vuelo)


def _actualizar_info_vuelo(viaje):
    indice = viaje["indice"]
    id_vuelo = viaje["tramos"][indice]["id_vuelo"]
    info = VueloRepository().informacion_vuelo(id_vuelo)
    ocup = AsientoRepository().ocupacion(id_vuelo)
    if info.empty or ocup.empty:
        st.error("El vuelo seleccionado no existe en MySQL.")
        st.stop()
    fila = info.iloc[0].to_dict()
    ahora = datetime.now(ZONA_HORARIA).replace(tzinfo=None)
    if fila["estado"] != "programado" or pd.Timestamp(fila["salida_prog"]) <= ahora:
        st.error("Este vuelo ya no admite reservas: ha salido o ha cambiado de estado.")
        st.stop()
    ocupacion = ocup.iloc[0].to_dict()
    if int(ocupacion["asientos_disponibles"]) < viaje["pasajeros"]:
        st.error("No quedan plazas suficientes para todos los pasajeros.")
        st.stop()
    return fila, ocupacion, ahora


def pantalla_comparar_tarifas():
    st.header("Comparar categorías, tarifas y precios")
    viaje = st.session_state.get("itinerario")
    if not viaje:
        st.info("Primero busca y selecciona tus vuelos.")
        st.button("Ir a Buscar vuelos", on_click=_volver_a_buscar)
        return
    indice = viaje["indice"]
    info, ocup, ahora = _actualizar_info_vuelo(viaje)
    st.caption(f"Tramo {indice + 1}/{len(viaje['tramos'])} · {viaje['tramos'][indice]['nombre']} · "
               f"{viaje['pasajeros']} pasajero(s) · Preferencia inicial: {viaje['preferencia']}")
    st.subheader(f"{info['ciudad_origen']} ({info['origen']}) → "
                 f"{info['ciudad_destino']} ({info['destino']})")
    st.write(f"Vuelo {info['numero_vuelo']} · Salida {_fmt(info['salida_prog'], '%d/%m/%Y %H:%M')} · "
             f"Llegada programada {_fmt(info['llegada_prog'], '%d/%m/%Y %H:%M')}")
    st.caption(f"Avión: {info['modelo']} · Plazas libres globales: "
               f"{int(ocup['asientos_disponibles'])}/{int(info['capacidad'])}")

    # No se consulta internet ni se supone un tipo de cambio real actualizado.
    tc = st.number_input("Tipo de cambio de simulación (PEN por USD)",
                         min_value=2.0, max_value=6.0, value=3.75, step=0.01,
                         format="%.2f", key=f"tc_simulado_{indice}")
    st.caption("3,75 procede de la simulación histórica. No es un tipo de cambio "
               "actual garantizado. Cambia el valor para comparar importes en soles.")

    tarifas_df = cargar_tarifas_catalogo()
    try:
        cotizaciones = ServicioPrecios().cotizar_tarifas(
            info, tarifas_df.to_dict("records"), int(ocup["asientos_ocupados"]),
            ahora, float(tc),
        )
    except (KeyError, ValueError) as e:
        st.error(f"No es posible cotizar las tarifas: {e}")
        return
    precios = {int(x["id_tarifa"]): x for x in cotizaciones}
    if not cotizaciones:
        st.warning("No hay tarifas configuradas.")
        return
    st.info(f"Precios estimados con Strategy y el IPC de {cotizaciones[0]['ipc_periodo']} "
            f"({cotizaciones[0]['ipc_valor']}). No son tarifas comerciales verificadas.")
    st.caption("Las categorías corresponden a tarifas de la BD; no hay distribución "
               "física de asientos por cabina. La elección de categoría NO garantiza "
               "una plaza en una zona específica del avión.")

    nombres = ["Económica", "Premium Economy", "Business"]
    descripciones = {
        "Económica": "Cuatro tarifas: desde Básica hasta Full. Equipaje y devolución según opción.",
        "Premium Economy": "Tarifa registrada con equipaje incluido y reembolso.",
        "Business": "Tarifa registrada con equipaje incluido y reembolso.",
    }
    columnas = st.columns(3)
    for columna, categoria in zip(columnas, nombres):
        opciones = [r for r in cotizaciones if r["clase"] == categoria]
        with columna:
            with st.container(border=True):
                st.markdown(f"### {categoria}")
                st.write(descripciones[categoria])
                if not opciones:
                    st.warning("No se ofrece esta categoría")
                    continue
                desde = min(opciones, key=lambda r: float(r["precio_usd"]))
                st.metric("Desde / persona", f"USD {desde['precio_usd']}")
                st.caption(f"S/ {desde['precio_pen']} por persona · "
                           f"{viaje['pasajeros']} viajero(s)")
                if len(opciones) > 1:
                    ids = [int(f["id_tarifa"]) for f in opciones]
                    elegido = st.radio("Selecciona una tarifa", ids,
                                      format_func=lambda i: (
                                          f"{precios[i]['nombre']} · USD {precios[i]['precio_usd']}"),
                                      key=f"categoria_econ_{indice}")
                    opcion = precios[elegido]
                else:
                    opcion = opciones[0]
                st.caption("Equipaje incluido: " + ("Sí" if opcion["equipaje_incluido"] else "No"))
                st.caption("Reembolsable: " + ("Sí" if opcion["reembolsable"] else "No"))
                usd_total, pen_total = total_en_moneda(
                    opcion["precio_usd"], viaje["pasajeros"], float(tc))
                st.write(f"**Total estimado: USD {usd_total} / S/ {pen_total}**")
                st.button(f"Elegir {categoria} y seleccionar plazas", type="primary",
                          key=f"elegir_cat_{categoria}_{indice}",
                          use_container_width=True, on_click=_elegir_tarifa,
                          args=(indice, opcion, opcion))

    with st.expander("Comparar las seis tarifas en una tabla"):
        tabla = pd.DataFrame([{
            "Categoría": t["clase"], "Tarifa": t["nombre"],
            "USD/persona": float(t["precio_usd"]),
            "PEN/persona": float(t["precio_pen"]),
            "Equipaje incluido": "Sí" if t["equipaje_incluido"] else "No",
            "Reembolsable": "Sí" if t["reembolsable"] else "No",
        } for t in cotizaciones])
        st.dataframe(tabla, hide_index=True, width="stretch")
    st.button("Volver a buscar vuelos", on_click=_volver_a_buscar)


def pantalla_plaza():
    st.header("Plaza · Selección de asientos")
    viaje = st.session_state.get("itinerario")
    if not viaje or viaje["indice"] not in viaje["tarifas"]:
        st.info("Primero selecciona una categoría y tarifa.")
        st.button("Comparar tarifas", on_click=_volver_a_comparar)
        return
    indice = viaje["indice"]
    info, ocup, _ = _actualizar_info_vuelo(viaje)
    elegidos = list(viaje["asientos"].get(indice, []))
    mapa = cargar_asientos_modelo(int(info["id_vuelo"]))
    etiquetas = mapa["asiento"].astype(str).tolist() if not mapa.empty else []
    ocupados = set(MapaAsientosRepository().ocupados(int(info["id_vuelo"]))["asiento"].astype(str))
    if not etiquetas:
        st.error("No existe un mapa histórico de asientos para el modelo seleccionado.")
        return
    if len(etiquetas) != int(info["capacidad"]):
        st.warning("El mapa inferido contiene un número de plazas distinto de la capacidad "
                   "registrada. No puede utilizarse para seleccionar asientos con seguridad.")
        return
    # El usuario puede ver si un asiento elegido ha pasado a estar ocupado.
    incompatibles = sorted(set(elegidos) & ocupados)
    if incompatibles:
        st.error("Algunas plazas elegidas han pasado a estar ocupadas: "
                 + ", ".join(incompatibles) + ". Desmárcalas y selecciona otras.")
    tarifa = viaje["tarifas"][indice]
    st.subheader(f"{info['numero_vuelo']} · {info['origen']} → {info['destino']}")
    st.caption(f"{info['fabricante']} {info['modelo']} · {tarifa['clase']} / {tarifa['nombre']}")
    st.metric("Asientos seleccionados", f"{len(elegidos)}/{viaje['pasajeros']}")
    st.progress(min(1.0, len(elegidos) / viaje["pasajeros"]))
    st.caption(f"Ocupación global registrada: {int(ocup['asientos_ocupados'])}/"
               f"{int(info['capacidad'])} plazas. "
               "✓ = elegido; × = ocupado; número/letra = libre.")
    st.warning("Distribución física por cabina no disponible en la BD. "
               "Mapa obtenido de las etiquetas históricas del mismo modelo. "
               "La selección es temporal y NO bloquea plazas en MySQL.")
    etiquetas_set = set(etiquetas)
    filas = sorted({int(a[:-1]) for a in etiquetas if a[:-1].isdigit()})
    for fila in filas:
        columnas = st.columns([0.65, 1, 1, 1, 0.65, 1, 1, 1], gap="small")
        columnas[0].caption(f"{fila:02d}")
        columnas[4].write(" ")
        for letra, c in zip("ABCDEF", (1, 2, 3, 5, 6, 7)):
            asiento = f"{fila}{letra}"
            if asiento not in etiquetas_set:
                columnas[c].write("—")
                continue
            no_disponible = asiento in ocupados
            marcado = asiento in elegidos
            columnas[c].button("×" if no_disponible else ("✓ " + letra if marcado else letra),
                               key=f"plaza_{int(info['id_vuelo'])}_{asiento}",
                               type="primary" if marcado else "secondary",
                               disabled=(no_disponible or
                                         (not marcado and len(elegidos) >= viaje['pasajeros'])),
                               use_container_width=True,
                               on_click=_alternar_asiento, args=(indice, asiento))
    st.write("**Tu selección:** " + (", ".join(elegidos) if elegidos else "ninguna"))
    usd_total, pen_total = total_en_moneda(
        tarifa["precio_usd"], viaje["pasajeros"], tarifa["tipo_cambio"])
    st.write(f"Total estimado de este tramo: **USD {usd_total} / S/ {pen_total}**")
    if st.session_state.get("error_plazas"):
        st.error(st.session_state.pop("error_plazas"))
    if indice + 1 == len(viaje["tramos"]):
        etiqueta_boton = "Resumen del viaje"
    else:
        etiqueta_boton = "Continuar al siguiente tramo"
    st.button(etiqueta_boton, type="primary",
              disabled=(len(elegidos) != viaje["pasajeros"] or bool(incompatibles)),
              on_click=_continuar_tramo, args=(indice,))
    st.button("Cambiar categoría o tarifa", on_click=_volver_a_comparar)


def resumen_itinerario(viaje):
    st.subheader("Resumen del viaje · selección provisional")
    from decimal import Decimal
    total_usd = Decimal("0")
    total_pen = Decimal("0")
    for indice, tramo in enumerate(viaje["tramos"]):
        info = VueloRepository().informacion_vuelo(tramo["id_vuelo"])
        if info.empty or indice not in viaje["tarifas"]:
            st.warning("El itinerario está incompleto.")
            return
        v = info.iloc[0]
        tarifa = viaje["tarifas"][indice]
        usd, pen = total_en_moneda(
            tarifa["precio_usd"], viaje["pasajeros"], tarifa["tipo_cambio"])
        total_usd += Decimal(usd)
        total_pen += Decimal(pen)
        with st.container(border=True):
            st.markdown(f"**{tramo['nombre']} — {v['numero_vuelo']}: "
                        f"{v['origen']} → {v['destino']}**")
            st.write(f"Salida: {_fmt(v['salida_prog'], '%d/%m/%Y %H:%M')} · "
                     f"Llegada programada: {_fmt(v['llegada_prog'], '%d/%m/%Y %H:%M')}")
            st.write(f"Categoría y tarifa: **{tarifa['clase']} · {tarifa['nombre']}**")
            st.write(f"Asientos: **{', '.join(viaje['asientos'].get(indice, []))}**")
            st.write(f"{viaje['pasajeros']} pasajero(s) · **USD {usd} / S/ {pen}**")
    st.metric("Total estimado del itinerario", f"USD {total_usd:,.2f}")
    st.write(f"Equivalente estimado en soles: **S/ {total_pen:,.2f}**")
    st.caption("Cálculo Strategy + inflación conocida a fecha de cotización; "
               "tipo de cambio simulado. Los asientos no están bloqueados, "
               "no se ha creado reserva, boleto ni pago, y el precio no es una oferta definitiva.")
    st.info("El registro de pasajeros, la reserva y el pago se desarrollarán en una etapa posterior.")
    st.button("Volver a Buscar vuelos", on_click=_volver_a_buscar)


# ---------- pantalla 2: horarios y vuelos por hora (consulta 2) ----------
def pantalla_horarios():
    st.header("Horarios de salida y llegada")
    aeropuertos = cargar_aeropuertos()
    opciones = dict(zip(aeropuertos["codigo_iata"],
                        aeropuertos["ciudad"] + " (" + aeropuertos["codigo_iata"] + ")"))

    col1, col2, col3 = st.columns(3)
    origen = col1.selectbox("Origen", opciones, format_func=opciones.get, key="h_origen")
    destino = col2.selectbox("Destino", opciones, format_func=opciones.get, index=1, key="h_destino")
    fecha = col3.date_input("Fecha", value=date.today(), key="h_fecha")

    if st.button("Ver horarios", type="primary"):
        if origen == destino:
            st.warning("El origen y el destino deben ser distintos.")
            return
        df = VueloRepository().horarios_vuelos(origen, destino, fecha)
        if df.empty:
            st.info(f"No hay vuelos el {fecha:%d/%m/%Y} para esa ruta.")
            return

        # ---- tabla de horarios (formato de presentacion) ----
        def hhmm(col):
            return pd.to_datetime(df[col]).dt.strftime("%H:%M").fillna("—")

        tabla = pd.DataFrame({
            "Vuelo": df["numero_vuelo"],
            "Ruta": df["origen"] + " → " + df["destino"],
            "Salida prog.": hhmm("salida_prog"),
            "Llegada prog.": hhmm("llegada_prog"),
            "Salida real": hhmm("salida_real"),
            "Llegada calculada*": hhmm("llegada_real"),
            "Duración": (df["duracion_min"] // 60).astype(str) + " h "
                        + (df["duracion_min"] % 60).astype(str).str.zfill(2) + " min",
            "Estado": df["estado"],
        })
        st.subheader("Detalle")
        st.dataframe(tabla, hide_index=True, width="stretch")
        st.caption("* La llegada se calcula con la duración media de la ruta. "
                   "No es una hora real de aterrizaje registrada.")


# ---------- pantalla 3: detalle de un vuelo (consultas 3, 4, 5 y 6a) ----------
def _fmt(valor, formato):
    """Fecha/hora para mostrar; '—' si es NULL."""
    return "—" if pd.isna(valor) else pd.Timestamp(valor).strftime(formato)


def pantalla_detalle_vuelo():
    st.header("Detalle de un vuelo")
    viaje = st.session_state.get("itinerario")
    if viaje and viaje.get("resumen_listo"):
        resumen_itinerario(viaje)
        return
    sel = st.session_state.get("vuelo_detalle")          # lo deja «Buscar vuelos»

    with st.expander("Buscar por número de vuelo y fecha", expanded=sel is None):
        col1, col2 = st.columns(2)
        numero = col1.text_input("Número de vuelo", placeholder="Ej: LP2414",
                                 key="d_numero").strip().upper()
        fecha_manual = col2.date_input("Fecha del vuelo", value=date.today(), key="d_fecha")
    if numero:                                           # la busqueda manual tiene prioridad
        sel = {"id_vuelo": None, "numero_vuelo": numero, "fecha": fecha_manual}
    if sel is None:
        st.info("Elige un vuelo en «Buscar vuelos» (botón «Ver detalle») "
                "o búscalo aquí por número de vuelo y fecha.")
        return

    estados = VueloRepository().estado_vuelo(sel["numero_vuelo"], sel["fecha"])   # consulta 3
    if sel["id_vuelo"] is not None:
        estados = estados[estados["id_vuelo"] == sel["id_vuelo"]]
    if estados.empty:
        st.warning(f"No hay un vuelo {sel['numero_vuelo']} el {sel['fecha']:%d/%m/%Y}.")
        return
    if len(estados) > 1:                                 # mismo numero, misma fecha
        fila = st.selectbox("Hay varios vuelos ese día, elige uno", estados.index,
                            format_func=lambda i: f"{estados.loc[i, 'origen']} → {estados.loc[i, 'destino']} "
                                                  f"({_fmt(estados.loc[i, 'salida_prog'], '%H:%M')})")
    else:
        fila = estados.index[0]
    est = estados.loc[fila]

    # ---------- tarjetas de estado (parte superior) ----------
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Situación", est["situacion"])
    if pd.isna(est["retraso_min"]):
        m2.metric("Retraso", "—")
    else:
        m2.metric("Retraso", f"{int(est['retraso_min'])} min",
                  delta=f"{int(est['retraso_min'])} min", delta_color="inverse")
    m3.metric("Salida programada", _fmt(est["salida_prog"], "%H:%M"))
    m4.metric("Salida real", _fmt(est["salida_real"], "%H:%M"))

    # ---------- ficha del vuelo: ReporteVuelo = consulta 4 + 6a + 5 (merge) ----------
    completo = ReporteVuelo(est["id_vuelo"]).generar()
    v = completo.iloc[0]
    st.divider()
    c1, c2, c3, c4 = st.columns(4)

    c1.subheader("Ruta")
    c1.markdown(f"**Origen:** {v['ciudad_origen']} ({v['origen']}), {v['pais_origen']}  \n"
                f"**Destino:** {v['ciudad_destino']} ({v['destino']}), {v['pais_destino']}  \n"
                f"**Distancia:** {v['distancia_km']:,.0f} km  \n"
                f"**Duración:** {v['duracion_min'] // 60} h {v['duracion_min'] % 60:02d} min")

    c2.subheader("Horarios")
    c2.markdown(f"**Salida prog.:** {_fmt(v['salida_prog'], '%d/%m/%Y %H:%M')}  \n"
                f"**Llegada prog.:** {_fmt(v['llegada_prog'], '%d/%m/%Y %H:%M')}  \n"
                f"**Salida real:** {_fmt(v['salida_real'], '%d/%m/%Y %H:%M')}  \n"
                f"**Llegada calculada:** {_fmt(v['llegada_real'], '%d/%m/%Y %H:%M')}")

    c3.subheader("Avión")
    c3.markdown(f"**Matrícula:** {v['matricula']}  \n"
                f"**Modelo:** {v['fabricante']} {v['modelo']}  \n"
                f"**Capacidad:** {v['capacidad']} asientos  \n"
                f"**Año:** {v['anio_fabricacion']}")

    c4.subheader("Ocupación")
    c4.progress(min(float(v["ocupacion_pct"]) / 100, 1.0))
    c4.markdown(f"**Ocupados:** {v['asientos_ocupados']}  \n"
                f"**Disponibles:** {v['asientos_disponibles']}  \n"
                f"**Ocupación:** {v['ocupacion_pct']}%")

    # ---------- tarifas del vuelo ----------
    st.subheader("Tarifas")
    tarifas = completo[["clase", "tarifa", "equipaje_incluido", "reembolsable",
                        "precio_desde", "precio_promedio", "precio_maximo", "base_del_precio"]]
    st.dataframe(tarifas, hide_index=True, width="stretch", column_config={
        "clase": "Clase", "tarifa": "Tarifa", "equipaje_incluido": "Equipaje",
        "reembolsable": "Reembolsable", "base_del_precio": "Base del precio",
        "precio_desde": st.column_config.NumberColumn("Desde", format="%.2f"),
        "precio_promedio": st.column_config.NumberColumn("Promedio", format="%.2f"),
        "precio_maximo": st.column_config.NumberColumn("Máximo", format="%.2f"),
    })
    st.caption("Los precios salen de los boletos vendidos (no indican moneda). "
               "«Ruta» en la base del precio significa que esa tarifa no se vendió en este vuelo.")
    st.download_button("Descargar ficha (CSV)", completo.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"ficha_{v['numero_vuelo']}.csv", mime="text/csv")


# ---------- pantallas de los demás integrantes ----------
def pantalla_reserva_pago():
    st.header("Reserva y pago")
    st.info("En construcción (consultas 7, 10, 11, 12).")


def pantalla_mis_reservas():
    st.header("Mis reservas y equipaje")
    st.info("En construcción (consultas 13, 14, 16).")


# ---------- menú lateral ----------
PANTALLAS = {
    "Buscar vuelos": pantalla_buscar_vuelos,
    "Comparar tarifas": pantalla_comparar_tarifas,
    "Plaza": pantalla_plaza,
    "Horarios": pantalla_horarios,
    "Detalle de vuelo": pantalla_detalle_vuelo,
    "Reserva y pago": pantalla_reserva_pago,
    "Mis reservas": pantalla_mis_reservas,
}
st.sidebar.title("✈️ Aerolínea")
eleccion = st.sidebar.radio("Menú", list(PANTALLAS), key="menu")
PANTALLAS[eleccion]()
