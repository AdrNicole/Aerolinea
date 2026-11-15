"""Patron REPOSITORY: cada repositorio encapsula el SQL de una entidad.

El resto del sistema pide "los vuelos de LIM a CUZ" o "la reserva
AVX8DH" sin escribir SQL; recibe DataFrames u objetos del dominio. Si
cambia el esquema o el motor, solo se tocan estas clases.

Todos reciben la conexion por parametro (por defecto, el Singleton), lo
que permite usar una conexion de prueba en los tests.
"""
import random
import re
import string
from datetime import date, datetime

import pandas as pd

from .conexion import ConexionMySQL
from .modelos import Pasajero, Reserva, Tarifa, Vuelo


def _orden_asiento(asiento: str):
    """'12A' -> (12, 'A') para ordenar asientos como en el avion."""
    m = re.match(r"(\d+)([A-Z]*)", str(asiento))
    return (int(m.group(1)), m.group(2)) if m else (9999, str(asiento))


class RepositorioBase:
    def __init__(self, conexion=None):
        self.cn = conexion or ConexionMySQL()

    def _df(self, sql: str, **params) -> pd.DataFrame:
        return self.cn.consultar(sql, params)


# ----------------------------------------------------------------------
class VueloRepository(RepositorioBase):

    _SQL_VUELO = """
        SELECT o.id_vuelo, o.numero_vuelo, o.origen, o.destino, o.salida_prog,
               o.estado, o.capacidad, o.asientos_ocupados,
               r.duracion_min, v.salida_real, v.id_ruta
        FROM v_ocupacion_vuelo o
        JOIN vuelos v ON v.id_vuelo = o.id_vuelo
        JOIN rutas  r ON r.id_ruta  = v.id_ruta
    """

    @staticmethod
    def _a_vuelo(fila) -> Vuelo:
        salida_real = fila["salida_real"]
        return Vuelo(
            id_vuelo=int(fila["id_vuelo"]), numero_vuelo=fila["numero_vuelo"],
            origen=fila["origen"], destino=fila["destino"],
            salida_prog=pd.Timestamp(fila["salida_prog"]).to_pydatetime(),
            estado=fila["estado"], capacidad=int(fila["capacidad"]),
            asientos_ocupados=int(fila["asientos_ocupados"]),
            duracion_min=int(fila["duracion_min"]),
            salida_real=None if pd.isna(salida_real) else pd.Timestamp(salida_real).to_pydatetime(),
            id_ruta=int(fila["id_ruta"]),
        )

    def buscar(self, origen: str, destino: str, fecha: date | str | None = None,
               solo_programados: bool = True) -> pd.DataFrame:
        """Vuelos de una ruta; si se da fecha, solo los de ese dia."""
        sql = self._SQL_VUELO + """
            WHERE o.origen = :origen AND o.destino = :destino
              AND (:fecha IS NULL OR DATE(o.salida_prog) = :fecha)
              AND (:solo = 0 OR o.estado = 'programado')
            ORDER BY o.salida_prog"""
        return self._df(sql, origen=origen.upper(), destino=destino.upper(),
                        fecha=None if fecha is None else str(fecha),
                        solo=int(solo_programados))

    def obtener(self, id_vuelo: int) -> Vuelo:
        df = self._df(self._SQL_VUELO + " WHERE o.id_vuelo = :id", id=id_vuelo)
        if df.empty:
            raise LookupError(f"No existe el vuelo {id_vuelo}")
        return self._a_vuelo(df.iloc[0])

    def asientos_libres(self, id_vuelo: int) -> list[str]:
        """Mapa de asientos del modelo (deducido de los boletos de ese
        modelo, no hay tabla de asientos) menos los ya vendidos."""
        sql = """
            SELECT DISTINCT b2.asiento
            FROM boletos b2
            JOIN vuelos  v2  ON v2.id_vuelo  = b2.id_vuelo
            JOIN aviones av2 ON av2.id_avion = v2.id_avion
            WHERE av2.id_modelo = (SELECT av.id_modelo FROM vuelos v
                                   JOIN aviones av ON av.id_avion = v.id_avion
                                   WHERE v.id_vuelo = :id)
              AND b2.asiento NOT IN (SELECT asiento FROM boletos WHERE id_vuelo = :id)"""
        asientos = self._df(sql, id=id_vuelo)["asiento"].tolist()
        return sorted(asientos, key=_orden_asiento)

    def tripulacion(self, id_vuelo: int) -> pd.DataFrame:
        sql = """
            SELECT tv.rol, t.id_tripulante, t.nombre, t.cargo, t.horas_vuelo
            FROM tripulacion_vuelo tv
            JOIN tripulantes t ON t.id_tripulante = tv.id_tripulante
            WHERE tv.id_vuelo = :id
            ORDER BY FIELD(tv.rol, 'Capitán', 'Primer Oficial', 'Jefe de cabina', 'TCP'), t.nombre"""
        return self._df(sql, id=id_vuelo)

    def pasajeros_del_vuelo(self, id_vuelo: int) -> pd.DataFrame:
        sql = """
            SELECT p.id_pasajero, p.nombre, r.codigo_pnr, b.asiento
            FROM boletos b
            JOIN pasajeros p ON p.id_pasajero = b.id_pasajero
            JOIN reservas  r ON r.id_reserva  = b.id_reserva
            WHERE b.id_vuelo = :id
            ORDER BY r.codigo_pnr, p.nombre"""
        return self._df(sql, id=id_vuelo)

    def actualizar_estado(self, id_vuelo: int, estado: str,
                          salida_real: datetime | None = None) -> None:
        """Persiste el cambio de estado. El trigger
        trg_vuelos_transicion_estado vuelve a validar la transicion."""
        from sqlalchemy import text

        with self.cn.transaccion() as cx:
            cx.execute(text("""
                UPDATE vuelos
                SET estado = :estado,
                    salida_real = COALESCE(:salida_real, salida_real)
                WHERE id_vuelo = :id"""),
                {"estado": estado, "salida_real": salida_real, "id": id_vuelo})


# ----------------------------------------------------------------------
class TarifaRepository(RepositorioBase):

    def listar(self) -> list[Tarifa]:
        df = self._df("SELECT * FROM tarifas ORDER BY id_tarifa")
        return [Tarifa(int(f.id_tarifa), f.clase, f.nombre,
                       bool(f.equipaje_incluido), bool(f.reembolsable))
                for f in df.itertuples()]

    def precio_base(self, id_ruta: int, id_tarifa: int) -> float:
        """Precio de referencia de una tarifa en una ruta: mediana de lo
        pagado comprando con 61-120 dias de anticipacion fuera de
        temporada alta (el escenario "neutro" del modelo de precios)."""
        sql = """
            SELECT b.precio
            FROM boletos b
            JOIN vuelos   v ON v.id_vuelo   = b.id_vuelo
            JOIN reservas r ON r.id_reserva = b.id_reserva
            WHERE v.id_ruta = :ruta AND b.id_tarifa = :tarifa
              AND DATEDIFF(v.salida_prog, r.fecha_compra) BETWEEN 61 AND 120
              AND MONTH(v.salida_prog) NOT IN (7, 12)"""
        precios = self._df(sql, ruta=id_ruta, tarifa=id_tarifa)["precio"]
        if precios.empty:  # ruta/tarifa sin historial: mediana general de la tarifa
            precios = self._df("SELECT precio FROM boletos WHERE id_tarifa = :t",
                               t=id_tarifa)["precio"]
        return round(float(precios.median()), 2)


# ----------------------------------------------------------------------
class PasajeroRepository(RepositorioBase):

    def por_documento(self, documento: str) -> pd.DataFrame:
        """Puede devolver mas de una fila: hay documentos repetidos."""
        sql = """
            SELECT p.*, cm.nivel, cm.millas
            FROM pasajeros p
            LEFT JOIN cuentas_millas cm ON cm.id_pasajero = p.id_pasajero
            WHERE p.documento = :doc"""
        return self._df(sql, doc=str(documento))

    def obtener(self, id_pasajero: int) -> Pasajero:
        df = self._df("SELECT * FROM pasajeros WHERE id_pasajero = :id", id=id_pasajero)
        if df.empty:
            raise LookupError(f"No existe el pasajero {id_pasajero}")
        f = df.iloc[0]
        return Pasajero(int(f.id_pasajero), str(f.documento), f.nombre, f.nacionalidad)

    def registrar(self, documento: str, nombre: str, nacionalidad: str) -> int:
        """Registra un pasajero nuevo y devuelve su id (no es AUTO_INCREMENT)."""
        from sqlalchemy import text

        with self.cn.transaccion() as cx:
            nuevo = cx.execute(text(
                "SELECT COALESCE(MAX(id_pasajero), 0) + 1 FROM pasajeros FOR UPDATE")).scalar()
            cx.execute(text("""INSERT INTO pasajeros (id_pasajero, documento, nombre, nacionalidad)
                               VALUES (:id, :doc, :nom, :nac)"""),
                       {"id": nuevo, "doc": documento, "nom": nombre, "nac": nacionalidad})
        return int(nuevo)


# ----------------------------------------------------------------------
class ReservaRepository(RepositorioBase):

    def itinerario(self, codigo_pnr: str) -> pd.DataFrame:
        sql = """
            SELECT rs.codigo_pnr, rs.fecha_compra, rs.canal, pv.nombre AS pasajero,
                   v.numero_vuelo, CONCAT(ao.codigo_iata, '-', ad.codigo_iata) AS ruta,
                   v.salida_prog, b.asiento, t.clase, t.nombre AS tarifa, b.precio,
                   v.estado AS estado_vuelo
            FROM reservas rs
            JOIN boletos     b  ON b.id_reserva     = rs.id_reserva
            JOIN pasajeros   pv ON pv.id_pasajero   = b.id_pasajero
            JOIN vuelos      v  ON v.id_vuelo       = b.id_vuelo
            JOIN rutas       r  ON r.id_ruta        = v.id_ruta
            JOIN aeropuertos ao ON ao.id_aeropuerto = r.id_origen
            JOIN aeropuertos ad ON ad.id_aeropuerto = r.id_destino
            JOIN tarifas     t  ON t.id_tarifa      = b.id_tarifa
            WHERE rs.codigo_pnr = :pnr
            ORDER BY v.salida_prog, b.id_boleto"""
        return self._df(sql, pnr=codigo_pnr.upper())

    def pagos(self, codigo_pnr: str) -> pd.DataFrame:
        sql = """SELECT p.* FROM pagos p JOIN reservas r ON r.id_reserva = p.id_reserva
                 WHERE r.codigo_pnr = :pnr ORDER BY p.id_pago"""
        return self._df(sql, pnr=codigo_pnr.upper())

    def guardar(self, reserva: Reserva) -> int:
        """Guarda reserva, boletos y pagos en UNA transaccion.
        Si algo falla (asiento repetido, vuelo lleno o no programado:
        lo valida el trigger trg_boletos_validar_venta) no se guarda nada.
        Devuelve el id_reserva."""
        from sqlalchemy import text

        with self.cn.transaccion() as cx:
            # PNR unico: si el generado ya existe, se genera otro
            while cx.execute(text("SELECT 1 FROM reservas WHERE codigo_pnr = :p"),
                             {"p": reserva.codigo_pnr}).first():
                reserva.codigo_pnr = generar_pnr()

            id_reserva = cx.execute(text(
                "SELECT COALESCE(MAX(id_reserva), 0) + 1 FROM reservas FOR UPDATE")).scalar()
            cx.execute(text("""
                INSERT INTO reservas (id_reserva, id_pasajero, codigo_pnr, fecha_compra, canal)
                VALUES (:id, :tit, :pnr, :fecha, :canal)"""),
                {"id": id_reserva, "tit": reserva.id_titular, "pnr": reserva.codigo_pnr,
                 "fecha": reserva.fecha_compra, "canal": reserva.canal})

            id_boleto = cx.execute(text(
                "SELECT COALESCE(MAX(id_boleto), 0) FROM boletos FOR UPDATE")).scalar()
            for b in reserva.boletos:
                id_boleto += 1
                cx.execute(text("""
                    INSERT INTO boletos (id_boleto, id_reserva, id_vuelo, id_tarifa,
                                         asiento, precio, id_pasajero)
                    VALUES (:id, :res, :vuelo, :tarifa, :asiento, :precio, :pas)"""),
                    {"id": id_boleto, "res": id_reserva, "vuelo": b.id_vuelo,
                     "tarifa": b.id_tarifa, "asiento": b.asiento, "precio": b.precio,
                     "pas": b.id_pasajero})

            id_pago = cx.execute(text(
                "SELECT COALESCE(MAX(id_pago), 0) FROM pagos FOR UPDATE")).scalar()
            for p in reserva.pagos:
                id_pago += 1
                cx.execute(text("""
                    INSERT INTO pagos (id_pago, id_reserva, monto, moneda, metodo)
                    VALUES (:id, :res, :monto, :moneda, :metodo)"""),
                    {"id": id_pago, "res": id_reserva, "monto": p.monto,
                     "moneda": p.moneda, "metodo": p.metodo})
        return int(id_reserva)


def generar_pnr(rng: random.Random | None = None) -> str:
    """Codigo de reserva de 6 caracteres (letras y digitos)."""
    rng = rng or random.Random()
    return "".join(rng.choices(string.ascii_uppercase + string.digits, k=6))


# ----------------------------------------------------------------------
class AnalisisRepository(RepositorioBase):
    """Extrae los datos crudos para el analisis con pandas."""

    def vuelos(self) -> pd.DataFrame:
        """Tabla de hechos por vuelo (base del dashboard de negocio):
        boletos, ingresos por boletos, cargos de equipaje (35 USD por
        maleta de bodega en tarifas sin equipaje) y retraso."""
        sql = """
            SELECT v.id_vuelo, v.numero_vuelo, v.salida_prog, v.salida_real, v.estado,
                   ao.codigo_iata AS origen, ad.codigo_iata AS destino,
                   CONCAT(ao.codigo_iata, '-', ad.codigo_iata) AS ruta,
                   ao.pais AS pais_origen, ad.pais AS pais_destino, r.distancia_km, m.capacidad,
                   COALESCE(b.boletos, 0)  AS boletos,
                   COALESCE(b.ingresos, 0) AS ingresos_boletos,
                   COALESCE(e.cargo, 0)    AS ingresos_equipaje,
                   TIMESTAMPDIFF(MINUTE, v.salida_prog, v.salida_real) AS retraso_min
            FROM vuelos v
            JOIN rutas         r  ON r.id_ruta        = v.id_ruta
            JOIN aeropuertos   ao ON ao.id_aeropuerto = r.id_origen
            JOIN aeropuertos   ad ON ad.id_aeropuerto = r.id_destino
            JOIN aviones       av ON av.id_avion      = v.id_avion
            JOIN modelos_avion m  ON m.id_modelo      = av.id_modelo
            LEFT JOIN (SELECT id_vuelo, COUNT(*) AS boletos, SUM(precio) AS ingresos
                       FROM boletos GROUP BY id_vuelo) b ON b.id_vuelo = v.id_vuelo
            LEFT JOIN (SELECT bo.id_vuelo, 35 * COUNT(*) AS cargo
                       FROM boletos bo
                       JOIN tarifas   t  ON t.id_tarifa  = bo.id_tarifa AND t.equipaje_incluido = 0
                       JOIN equipajes eq ON eq.id_boleto = bo.id_boleto AND eq.tipo = 'Bodega'
                       GROUP BY bo.id_vuelo) e ON e.id_vuelo = v.id_vuelo"""
        return self._df(sql)

    def puntualidad(self) -> pd.DataFrame:
        return self._df("SELECT * FROM v_puntualidad_vuelo")

    def ocupacion(self) -> pd.DataFrame:
        return self._df("SELECT * FROM v_ocupacion_vuelo WHERE estado = 'aterrizado'")

    def ventas(self) -> pd.DataFrame:
        """Un registro por boleto (~487 mil filas, tarda unos segundos)."""
        sql = """
            SELECT b.id_boleto, b.id_vuelo, b.id_tarifa, t.clase, t.nombre AS tarifa,
                   b.precio, r.fecha_compra, r.canal, v.salida_prog, v.estado,
                   v.id_ruta, ao.codigo_iata AS origen, ad.codigo_iata AS destino,
                   m.capacidad
            FROM boletos b
            JOIN reservas      r  ON r.id_reserva     = b.id_reserva
            JOIN vuelos        v  ON v.id_vuelo       = b.id_vuelo
            JOIN rutas         ru ON ru.id_ruta       = v.id_ruta
            JOIN aeropuertos   ao ON ao.id_aeropuerto = ru.id_origen
            JOIN aeropuertos   ad ON ad.id_aeropuerto = ru.id_destino
            JOIN aviones       av ON av.id_avion      = v.id_avion
            JOIN modelos_avion m  ON m.id_modelo      = av.id_modelo
            JOIN tarifas       t  ON t.id_tarifa      = b.id_tarifa"""
        return self._df(sql)

    def pasajeros_millas(self) -> pd.DataFrame:
        """Un registro por pasajero que viajo: nivel de millas (NULL = no
        afiliado), vuelos realizados y gasto."""
        sql = """
            SELECT p.id_pasajero, p.nacionalidad, cm.nivel, cm.millas,
                   COUNT(*)      AS vuelos,
                   SUM(b.precio) AS gasto_usd
            FROM boletos b
            JOIN vuelos v           ON v.id_vuelo     = b.id_vuelo AND v.estado = 'aterrizado'
            JOIN pasajeros p        ON p.id_pasajero  = b.id_pasajero
            LEFT JOIN cuentas_millas cm ON cm.id_pasajero = p.id_pasajero
            GROUP BY p.id_pasajero, p.nacionalidad, cm.nivel, cm.millas"""
        return self._df(sql)

    def horas_tripulantes(self) -> pd.DataFrame:
        return self._df("SELECT * FROM v_horas_tripulante")
