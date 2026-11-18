import tomllib
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL

RUTA_SECRETS = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"


class ConexionMySQL:
    """Singleton: una sola conexión (engine) para toda la aplicación."""
    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            if not RUTA_SECRETS.is_file():
                raise FileNotFoundError(
                    f"Falta {RUTA_SECRETS}. Copia .streamlit/secrets.toml.example "
                    "como .streamlit/secrets.toml y configura MySQL."
                )
            with open(RUTA_SECRETS, "rb") as f:
                cfg = tomllib.load(f)["mysql"]
            url = URL.create(
                "mysql+pymysql",
                username=cfg["user"], password=cfg.get("password", ""),
                host=cfg.get("host", "localhost"), port=int(cfg.get("port", 3306)),
                database=cfg.get("database", "aerolinea"),
                query={"charset": "utf8mb4"},
            )
            obj = super().__new__(cls)
            obj.engine = create_engine(url, pool_pre_ping=True)

            @event.listens_for(obj.engine, "connect")
            def _collation(dbapi_con, _):          # misma collation que las tablas
                with dbapi_con.cursor() as cur:
                    cur.execute("SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci")
            cls._instancia = obj
        return cls._instancia


class AeropuertoRepository:
    """Repository: aeropuertos (para llenar los selectbox)."""
    def __init__(self):
        self.engine = ConexionMySQL().engine

    def listar(self):
        sql = text("SELECT codigo_iata, ciudad, pais FROM aeropuertos ORDER BY ciudad")
        return pd.read_sql(sql, self.engine)


class VueloRepository:
    """Repository: encapsula el SQL de vuelos y devuelve DataFrames."""
    def __init__(self):
        self.engine = ConexionMySQL().engine

    def vuelos_disponibles(self, origen, destino, fecha, pasajeros=1,
                          momento_actual=None, limite=30):
        """Consulta 1: vuelos reservables en UNA fecha, sin alternativas mezcladas.

        Un vuelo reservable debe estar programado, salir después de la fecha/hora
        actual local y tener plazas suficientes para todos los viajeros.
        La capacidad es global; la BD no diferencia plazas disponibles por cabina.
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo

        if fecha is None:
            raise ValueError("La fecha de viaje es obligatoria")
        if not isinstance(pasajeros, int) or not 1 <= pasajeros <= 9:
            raise ValueError("Pasajeros debe estar entre 1 y 9")
        if origen == destino:
            raise ValueError("El origen debe ser distinto del destino")
        limite = max(1, min(int(limite), 30))
        if momento_actual is None:
            momento_actual = datetime.now(ZoneInfo("America/Lima")).replace(tzinfo=None)

        sql = text("""
            SELECT v.id_vuelo, v.numero_vuelo,
                   ao.codigo_iata AS origen, ao.ciudad AS ciudad_origen,
                   ad.codigo_iata AS destino, ad.ciudad AS ciudad_destino,
                   v.salida_prog,
                   DATE_ADD(v.salida_prog, INTERVAL r.duracion_min MINUTE) AS llegada_prog,
                   r.duracion_min, v.estado,
                   m.capacidad - (SELECT COUNT(*) FROM boletos b
                                 WHERE b.id_vuelo = v.id_vuelo) AS asientos_disponibles
            FROM vuelos v
            JOIN rutas r ON r.id_ruta = v.id_ruta
            JOIN aeropuertos ao ON ao.id_aeropuerto = r.id_origen
            JOIN aeropuertos ad ON ad.id_aeropuerto = r.id_destino
            JOIN aviones av ON av.id_avion = v.id_avion
            JOIN modelos_avion m ON m.id_modelo = av.id_modelo
            WHERE ao.codigo_iata = :origen
              AND ad.codigo_iata = :destino
              AND v.estado = 'programado'
              AND v.salida_prog >= :momento_actual
              AND v.salida_prog >= :fecha
              AND v.salida_prog < DATE_ADD(:fecha, INTERVAL 1 DAY)
              AND m.capacidad - (SELECT COUNT(*) FROM boletos b
                                WHERE b.id_vuelo = v.id_vuelo) >= :pasajeros
            ORDER BY v.salida_prog, v.id_vuelo
            LIMIT :limite
        """)
        return pd.read_sql(sql, self.engine, params={
            "origen": origen, "destino": destino, "fecha": fecha,
            "pasajeros": pasajeros, "momento_actual": momento_actual,
            "limite": limite,
        })

    def fechas_disponibles(self, origen, destino, pasajeros=1,
                          momento_actual=None, horizonte_dias=365):
        """Fechas con al menos un vuelo futuro con N plazas libres (calendario)."""
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        if not isinstance(pasajeros, int) or not 1 <= pasajeros <= 9:
            raise ValueError("Pasajeros debe estar entre 1 y 9")
        if origen == destino:
            return pd.DataFrame(columns=["fecha", "cantidad_vuelos", "plazas_maximas"])
        if momento_actual is None:
            momento_actual = datetime.now(ZoneInfo("America/Lima")).replace(tzinfo=None)
        horizonte_dias = max(1, min(int(horizonte_dias), 730))
        hasta_exclusiva = momento_actual.date() + timedelta(days=horizonte_dias + 1)
        sql = text("""
            SELECT DATE(v.salida_prog) AS fecha,
                   COUNT(*) AS cantidad_vuelos,
                   MAX(m.capacidad - (SELECT COUNT(*) FROM boletos b
                                     WHERE b.id_vuelo = v.id_vuelo)) AS plazas_maximas
            FROM vuelos v
            JOIN rutas r ON r.id_ruta = v.id_ruta
            JOIN aeropuertos ao ON ao.id_aeropuerto = r.id_origen
            JOIN aeropuertos ad ON ad.id_aeropuerto = r.id_destino
            JOIN aviones av ON av.id_avion = v.id_avion
            JOIN modelos_avion m ON m.id_modelo = av.id_modelo
            WHERE ao.codigo_iata = :origen
              AND ad.codigo_iata = :destino
              AND v.estado = 'programado'
              AND v.salida_prog >= :momento_actual
              AND v.salida_prog < :hasta_exclusiva
              AND m.capacidad - (SELECT COUNT(*) FROM boletos b
                                WHERE b.id_vuelo = v.id_vuelo) >= :pasajeros
            GROUP BY DATE(v.salida_prog)
            ORDER BY fecha
        """)
        return pd.read_sql(sql, self.engine, params={
            "origen": origen, "destino": destino, "pasajeros": pasajeros,
            "momento_actual": momento_actual, "hasta_exclusiva": hasta_exclusiva,
        })

    def horarios_vuelos(self, origen, destino, fecha):
        """Consulta 2 (seguimiento, incluso vuelos históricos o cancelados).
        llegada_real es un CALCULO por duración media, no el aterrizaje registrado."""
        sql = text("""
            SELECT v.id_vuelo,
                   v.numero_vuelo,
                   ao.codigo_iata AS origen,
                   ad.codigo_iata AS destino,
                   r.duracion_min,
                   v.salida_prog,
                   DATE_ADD(v.salida_prog, INTERVAL r.duracion_min MINUTE) AS llegada_prog,
                   v.salida_real,
                   DATE_ADD(v.salida_real, INTERVAL r.duracion_min MINUTE) AS llegada_real,
                   v.estado
            FROM vuelos v
            JOIN rutas       r  ON r.id_ruta        = v.id_ruta
            JOIN aeropuertos ao ON ao.id_aeropuerto = r.id_origen
            JOIN aeropuertos ad ON ad.id_aeropuerto = r.id_destino
            WHERE ao.codigo_iata = :origen
              AND ad.codigo_iata = :destino
              AND v.salida_prog >= :fecha
              AND v.salida_prog <  DATE_ADD(:fecha, INTERVAL 1 DAY)
            ORDER BY v.salida_prog""")
        return pd.read_sql(sql, self.engine,
                           params={"origen": origen, "destino": destino, "fecha": fecha})


    def estado_vuelo(self, numero_vuelo, fecha):
        """Consulta 3. Estado de un vuelo por numero y fecha (retraso_min negativo = salio antes)."""
        sql = text("""
            SELECT v.id_vuelo,
                   v.numero_vuelo,
                   ao.codigo_iata AS origen,
                   ad.codigo_iata AS destino,
                   v.salida_prog,
                   v.salida_real,
                   v.estado,
                   TIMESTAMPDIFF(MINUTE, v.salida_prog, v.salida_real) AS retraso_min,
                   CASE
                       WHEN v.estado = 'cancelado'    THEN 'Cancelado'
                       WHEN v.salida_real IS NULL     THEN 'Aun no sale'
                       WHEN v.salida_real > v.salida_prog THEN 'Retrasado'
                       WHEN v.salida_real < v.salida_prog THEN 'Salio antes de hora'
                       ELSE 'Puntual'
                   END AS situacion
            FROM vuelos v
            JOIN rutas       r  ON r.id_ruta        = v.id_ruta
            JOIN aeropuertos ao ON ao.id_aeropuerto = r.id_origen
            JOIN aeropuertos ad ON ad.id_aeropuerto = r.id_destino
            WHERE v.numero_vuelo = :numero_vuelo
              AND v.salida_prog >= :fecha
              AND v.salida_prog <  DATE_ADD(:fecha, INTERVAL 1 DAY)
            ORDER BY v.salida_prog""")
        return pd.read_sql(sql, self.engine, params={"numero_vuelo": numero_vuelo, "fecha": fecha})
######################################
    def informacion_vuelo(self, id_vuelo):
        """Consulta 4. Ruta, horarios y avion de un vuelo (una fila)."""
        sql = text("""
            SELECT v.id_vuelo,
                   v.id_ruta,
                   v.numero_vuelo,
                   v.estado,
                   -- ruta
                   ao.codigo_iata AS origen,
                   ao.ciudad      AS ciudad_origen,
                   ao.pais        AS pais_origen,
                   ad.codigo_iata AS destino,
                   ad.ciudad      AS ciudad_destino,
                   ad.pais        AS pais_destino,
                   r.distancia_km,
                   r.duracion_min,
                   -- horarios
                   v.salida_prog,
                   DATE_ADD(v.salida_prog, INTERVAL r.duracion_min MINUTE) AS llegada_prog,
                   v.salida_real,
                   DATE_ADD(v.salida_real, INTERVAL r.duracion_min MINUTE) AS llegada_real,
                   -- avion
                   av.id_avion,
                   av.matricula,
                   m.fabricante,
                   m.nombre       AS modelo,
                   m.capacidad,
                   av.anio_fabricacion
            FROM vuelos v
            JOIN rutas         r  ON r.id_ruta         = v.id_ruta
            JOIN aeropuertos   ao ON ao.id_aeropuerto  = r.id_origen
            JOIN aeropuertos   ad ON ad.id_aeropuerto  = r.id_destino
            JOIN aviones       av ON av.id_avion       = v.id_avion
            JOIN modelos_avion m  ON m.id_modelo       = av.id_modelo
            WHERE v.id_vuelo = :id_vuelo""")
        return pd.read_sql(sql, self.engine, params={"id_vuelo": id_vuelo})


class TarifaRepository:
    """Repository: tarifas y precios (consulta 5)."""
    def __init__(self):
        self.engine = ConexionMySQL().engine

    def por_vuelo(self, id_vuelo):
        """Precio minimo, promedio y maximo de cada tarifa. Si no se vendio en el
        vuelo se usa la ruta completa como referencia (base_del_precio)."""
        sql = text("""
            SELECT t.id_tarifa,
                   t.clase,
                   t.nombre                                   AS tarifa,
                   IF(t.equipaje_incluido = 1, 'Si', 'No')    AS equipaje_incluido,
                   IF(t.reembolsable      = 1, 'Si', 'No')    AS reembolsable,
                   COALESCE(pv.precio_min, pr.precio_min)             AS precio_desde,
                   ROUND(COALESCE(pv.precio_prom, pr.precio_prom), 2) AS precio_promedio,
                   COALESCE(pv.precio_max, pr.precio_max)             AS precio_maximo,
                   IF(pv.id_tarifa IS NOT NULL, 'Vuelo', 'Ruta')      AS base_del_precio
            FROM tarifas t
            LEFT JOIN (
                    SELECT id_tarifa,
                           MIN(precio) AS precio_min,
                           AVG(precio) AS precio_prom,
                           MAX(precio) AS precio_max
                    FROM boletos
                    WHERE id_vuelo = :id_vuelo
                    GROUP BY id_tarifa
                 ) pv ON pv.id_tarifa = t.id_tarifa
            LEFT JOIN (
                    SELECT b.id_tarifa,
                           MIN(b.precio) AS precio_min,
                           AVG(b.precio) AS precio_prom,
                           MAX(b.precio) AS precio_max
                    FROM boletos b
                    JOIN vuelos vr ON vr.id_vuelo = b.id_vuelo
                    WHERE vr.id_ruta = (SELECT id_ruta FROM vuelos WHERE id_vuelo = :id_vuelo)
                    GROUP BY b.id_tarifa
                 ) pr ON pr.id_tarifa = t.id_tarifa
            ORDER BY t.id_tarifa""")
        return pd.read_sql(sql, self.engine, params={"id_vuelo": id_vuelo})


class AsientoRepository:
    """Repository: asientos y ocupacion (consulta 6)."""
    def __init__(self):
        self.engine = ConexionMySQL().engine

    def ocupacion(self, id_vuelo):
        """Consulta 6a. disponibles = capacidad del modelo - boletos emitidos."""
        sql = text("""
            SELECT v.id_vuelo,
                   v.numero_vuelo,
                   v.estado,
                   m.nombre                                   AS modelo,
                   m.capacidad,
                   COUNT(b.id_boleto)                         AS asientos_ocupados,
                   m.capacidad - COUNT(b.id_boleto)           AS asientos_disponibles,
                   ROUND(COUNT(b.id_boleto) / m.capacidad * 100, 1) AS ocupacion_pct
            FROM vuelos v
            JOIN aviones       av ON av.id_avion = v.id_avion
            JOIN modelos_avion m  ON m.id_modelo = av.id_modelo
            LEFT JOIN boletos  b  ON b.id_vuelo  = v.id_vuelo
            WHERE v.id_vuelo = :id_vuelo
            GROUP BY v.id_vuelo, v.numero_vuelo, v.estado, m.nombre, m.capacidad""")
        return pd.read_sql(sql, self.engine, params={"id_vuelo": id_vuelo})




class TarifaCatalogoRepository:
    """Características contractuales de las seis tarifas; no calcula precios."""

    def __init__(self):
        self.engine = ConexionMySQL().engine

    def listar(self):
        return pd.read_sql(text("""
            SELECT id_tarifa, clase, nombre, equipaje_incluido, reembolsable
            FROM tarifas
            ORDER BY id_tarifa
        """), self.engine)


class MapaAsientosRepository:
    """Asientos observados por modelo y ocupados en un vuelo.

    La BD NO tiene asignación de asientos por cabina: este mapa es global.
    La estructura procede de las etiquetas de asientos existentes en boletos.
    """

    def __init__(self):
        self.engine = ConexionMySQL().engine

    def etiquetas_modelo(self, id_vuelo):
        sql = text("""
            SELECT s.asiento FROM (
                SELECT DISTINCT b.asiento
                FROM boletos b
                JOIN vuelos v_hist ON v_hist.id_vuelo = b.id_vuelo
                JOIN aviones av_hist ON av_hist.id_avion = v_hist.id_avion
                WHERE av_hist.id_modelo = (
                    SELECT av.id_modelo FROM vuelos v
                    JOIN aviones av ON av.id_avion = v.id_avion
                    WHERE v.id_vuelo = :id_vuelo
                )
            ) s
            ORDER BY CAST(s.asiento AS UNSIGNED), SUBSTR(s.asiento, -1)
        """)
        return pd.read_sql(sql, self.engine, params={"id_vuelo": int(id_vuelo)})

    def ocupados(self, id_vuelo):
        sql = text("""
            SELECT asiento FROM boletos WHERE id_vuelo = :id_vuelo
            ORDER BY CAST(asiento AS UNSIGNED), SUBSTR(asiento, -1)
        """)
        return pd.read_sql(sql, self.engine, params={"id_vuelo": int(id_vuelo)})
