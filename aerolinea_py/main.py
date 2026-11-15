"""Menu de consola del sistema de la aerolinea.

Uso:  python main.py
Requiere la base 'aerolinea' cargada con data_base.sql y el archivo
.env con los datos de conexion (ver .env.ejemplo).
"""
from datetime import datetime, timedelta

import pandas as pd

from aerolinea.config import FECHA_CORTE
from aerolinea.patrones.estado_vuelo import TransicionInvalida
from aerolinea.patrones.precio import (CalculadoraPrecio, ContextoPrecio, PrecioDinamico,
                                       PrecioFijo, PrecioPorAnticipacion, PrecioPorOcupacion)
from aerolinea.patrones.reserva_builder import METODOS_PAGO, ErrorReserva
from aerolinea.repositorios import (PasajeroRepository, ReservaRepository,
                                    TarifaRepository, VueloRepository)
from aerolinea.servicios import ServicioReservas, ServicioVuelos

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)


# --- utilidades de entrada ----------------------------------------------
def pedir(texto: str, defecto: str | None = None) -> str:
    sufijo = f" [{defecto}]" if defecto is not None else ""
    valor = input(f"{texto}{sufijo}: ").strip()
    return valor or (defecto or "")


def pedir_int(texto: str, defecto: int | None = None) -> int:
    return int(pedir(texto, None if defecto is None else str(defecto)))


def pedir_fecha(texto: str, defecto: datetime | None = None) -> datetime | None:
    valor = pedir(texto + " (AAAA-MM-DD [HH:MM])", defecto.strftime("%Y-%m-%d %H:%M") if defecto else "")
    if not valor:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(valor, fmt)
        except ValueError:
            pass
    raise ValueError(f"Fecha invalida: {valor}")


def titulo(texto: str):
    print("\n" + "=" * 70 + f"\n {texto}\n" + "=" * 70)


# --- opciones -------------------------------------------------------------
def buscar_vuelos():
    titulo("BUSCAR VUELOS")
    origen = pedir("Origen (IATA)", "LIM")
    destino = pedir("Destino (IATA)", "CUZ")
    fecha = pedir("Fecha AAAA-MM-DD (Enter = todas)", "")
    df = VueloRepository().buscar(origen, destino, fecha or None)
    if df.empty:
        print("No hay vuelos programados para esa busqueda.")
        return
    df["ocupacion_%"] = (df["asientos_ocupados"] / df["capacidad"] * 100).round(1)
    df["libres"] = df["capacidad"] - df["asientos_ocupados"]
    print(df[["id_vuelo", "numero_vuelo", "origen", "destino", "salida_prog",
              "capacidad", "libres", "ocupacion_%"]].to_string(index=False))
    print(f"\n{len(df)} vuelo(s)")


def detalle_vuelo():
    titulo("DETALLE DE VUELO")
    repo = VueloRepository()
    id_vuelo = pedir_int("Id del vuelo", 3079)
    v = repo.obtener(id_vuelo)
    print(f"\n{v}\nLlegada programada: {v.llegada_prog:%d/%m/%Y %H:%M} "
          f"| Ocupacion: {v.ocupacion:.1%}")
    print("\nTripulacion:")
    print(repo.tripulacion(id_vuelo).to_string(index=False))
    libres = repo.asientos_libres(id_vuelo)
    print(f"\nAsientos libres ({len(libres)}): {', '.join(libres[:30])}"
          f"{' ...' if len(libres) > 30 else ''}")


def cotizar_precio():
    titulo("COTIZAR PRECIO  (patron Strategy)")
    id_vuelo = pedir_int("Id del vuelo", 3079)
    for t in TarifaRepository().listar():
        print(f"  {t.id_tarifa}. {t.clase} - {t.nombre}")
    id_tarifa = pedir_int("Tarifa", 1)
    v = VueloRepository().obtener(id_vuelo)
    fecha = pedir_fecha("Fecha de compra (Enter = 30 dias antes del vuelo)") \
        or v.salida_prog - timedelta(days=30)
    base = TarifaRepository().precio_base(v.id_ruta, id_tarifa)
    ctx = ContextoPrecio(base, (v.salida_prog - fecha).days, v.ocupacion, v.salida_prog)
    print(f"\n{v}\nCompra: {fecha:%d/%m/%Y} ({ctx.dias_anticipacion} dias antes) | "
          f"Ocupacion: {ctx.ocupacion:.1%} | Precio base: {base:.2f} USD\n")
    calc = CalculadoraPrecio()
    for estrategia in (PrecioFijo(), PrecioPorAnticipacion(), PrecioPorOcupacion(), PrecioDinamico()):
        calc.cambiar_estrategia(estrategia)
        print(f"  {estrategia.nombre:<18} {calc.cotizar(ctx):>10.2f} USD")
    f = PrecioDinamico().factores(ctx)
    print(f"\n  Factores del precio dinamico: anticipacion x{f['anticipacion']}, "
          f"ocupacion x{f['ocupacion']}, temporada x{f['temporada']}")


def crear_reserva():
    titulo("CREAR RESERVA  (patron Builder + Strategy)")
    serv = ServicioReservas()
    fecha = pedir_fecha("Fecha de compra", FECHA_CORTE)
    b = serv.nuevo_builder(fecha_compra=fecha)
    b.para_titular(pedir_int("Id del titular", 58162))
    for p in pedir("Ids de pasajeros que viajan, separados por coma", "58162,1805").split(","):
        b.agregar_pasajero(int(p))
    tarifa = pedir_int("Tarifa para todos los tramos (1-6)", 3)
    print("  (busca los ids con la opcion 1; ej. LIM-CUZ 08/10/2026 y vuelta CUZ-LIM 09/10/2026)")
    for idv in pedir("Ids de vuelos en orden (ida,vuelta,...)", "3079,3084").split(","):
        if idv.strip():
            print(f"  + tramo {serv.tramo(b, int(idv), tarifa)}")
    b.por_canal(pedir("Canal (Web/App/Agencia/Call center/Aeropuerto)", "Web"))
    print("Metodos de pago: " + ", ".join(METODOS_PAGO))
    b.con_pago(pedir("Metodo de pago", METODOS_PAGO[0]), pedir("Moneda (USD/PEN)", "USD"))
    reserva = b.construir()
    print(f"\nReserva armada: PNR {reserva.codigo_pnr} | {len(reserva.boletos)} boleto(s) | "
          f"total {reserva.total_usd:.2f} USD")
    print(reserva.resumen().to_string(index=False))
    if pedir("\n¿Guardar en la base de datos? (s/n)", "n").lower() == "s":
        id_res = serv.guardar(reserva)
        print(f"Guardada: id_reserva {id_res}, PNR {reserva.codigo_pnr}")
    else:
        print("No se guardo (simulacion).")


def operar_vuelo():
    titulo("OPERAR VUELO  (patrones State + Observer)")
    id_vuelo = pedir_int("Id del vuelo", 3079)
    guardar = pedir("¿Guardar los cambios en la BD? (s = si, n = simulacion)", "n").lower() == "s"
    op, panel, notif = ServicioVuelos().operar(id_vuelo, guardar_en_bd=guardar)
    print(f"Vuelo {op} | salida programada {op.salida_prog:%d/%m/%Y %H:%M}")
    acciones = {
        "1": ("Iniciar embarque", lambda: op.iniciar_embarque()),
        "2": ("Despegar", lambda: op.despegar(
            op.salida_prog + timedelta(minutes=pedir_int("Minutos de retraso al despegar", 0)))),
        "3": ("Aterrizar", lambda: op.aterrizar()),
        "4": ("Cancelar", lambda: op.cancelar(pedir("Motivo", "Condiciones meteorologicas"))),
        "5": ("Anunciar retraso", lambda: op.anunciar_retraso(pedir_int("Minutos", 30))),
    }
    while True:
        print(f"\nEstado actual: {op.estado}")
        for k, (nombre, _) in acciones.items():
            print(f"  {k}. {nombre}")
        print("  0. Terminar")
        opcion = pedir("Accion", "0")
        if opcion == "0":
            break
        if opcion in acciones:
            try:
                acciones[opcion][1]()
            except TransicionInvalida as e:
                print(f"  ✗ {e}")
    print(f"\nHistorial: {' -> '.join(op.historial)}")
    print(f"Avisos a pasajeros generados: {len(notif.mensajes)}")
    for m in notif.mensajes[:3]:
        print(f"  · {m}")
    if len(notif.mensajes) > 3:
        print(f"  ... y {len(notif.mensajes) - 3} mas")


def consultar_reserva():
    titulo("CONSULTAR RESERVA")
    pnr = pedir("Codigo PNR", "AVX8DH")
    repo = ReservaRepository()
    itin = repo.itinerario(pnr)
    if itin.empty:
        print("No existe esa reserva.")
        return
    print(itin.to_string(index=False))
    print("\nPagos:")
    print(repo.pagos(pnr).to_string(index=False))


def buscar_pasajero():
    titulo("BUSCAR PASAJERO")
    df = PasajeroRepository().por_documento(pedir("Documento", "26787167"))
    print(df.to_string(index=False) if not df.empty else "No encontrado.")


def generar_analisis():
    titulo("ANALISIS Y GRAFICOS")
    import generar_analisis
    generar_analisis.ejecutar()


OPCIONES = {
    "1": ("Buscar vuelos", buscar_vuelos),
    "2": ("Detalle de vuelo (tripulacion y asientos)", detalle_vuelo),
    "3": ("Cotizar precio (Strategy)", cotizar_precio),
    "4": ("Crear reserva (Builder)", crear_reserva),
    "5": ("Operar vuelo (State + Observer)", operar_vuelo),
    "6": ("Consultar reserva por PNR", consultar_reserva),
    "7": ("Buscar pasajero por documento", buscar_pasajero),
    "8": ("Generar analisis y graficos (pandas)", generar_analisis),
}


def main():
    while True:
        titulo("AEROLINEA - Reservas, Vuelos y Puntualidad")
        for k, (nombre, _) in OPCIONES.items():
            print(f"  {k}. {nombre}")
        print("  0. Salir")
        opcion = pedir("Opcion", "0")
        if opcion == "0":
            break
        if opcion not in OPCIONES:
            continue
        try:
            OPCIONES[opcion][1]()
        except (ErrorReserva, LookupError, ValueError) as e:
            print(f"\n✗ {e}")
        except Exception as e:  # errores de MySQL (trigger, conexion, etc.)
            print(f"\n✗ Error: {getattr(e, 'orig', e)}")
        input("\nEnter para continuar...")


if __name__ == "__main__":
    main()
