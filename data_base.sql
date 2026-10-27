-- ============================================================
--  AEROLINEA - Script de creación e importación (MUESTRA: tabla 1 de 14)
--  Motor: MySQL 8 / Workbench
-- ============================================================
--  ANTES DE EJECUTAR:
--  1) Cambia RUTA_CSV por la carpeta donde guardaste los CSV,
--  RUTA_CSV: C:/P6_aerolinea/
--     usando "/" (ejemplo: C:/proyecto/csv/). Debe terminar en "/".
--  2) Habilita la carga local (una sola vez):
--       SET GLOBAL local_infile = 1;
--     y en Workbench: Database > Manage Connections > Advanced > Others
--       OPT_LOCAL_INFILE=1
--     Luego reconecta.
-- si deseas borrar todas las tablas ejecuta:
 /*
USE aerolinea;
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS pagos, equipajes, boletos, tarifas, reservas,
                     cuentas_millas, pasajeros, tripulacion_vuelo,
                     tripulantes, vuelos, aviones, modelos_avion,
                     rutas, aeropuertos;
SET FOREIGN_KEY_CHECKS = 1; */
-- ============================================================
SET GLOBAL local_infile = 1;
 
CREATE DATABASE IF NOT EXISTS aerolinea
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE aerolinea;
 
-- Desactivado durante la carga masiva; se reactiva al final del script completo
-- SET FOREIGN_KEY_CHECKS = 0;
-- SET UNIQUE_CHECKS = 0;
-- SET AUTOCOMMIT = 0;
 
-- ------------------------------------------------------------
-- 01. aeropuertos  (25 filas)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS aeropuertos;
CREATE TABLE aeropuertos (
    id_aeropuerto INT          NOT NULL,
    codigo_iata   CHAR(3)      NOT NULL,
    ciudad        VARCHAR(80)  NOT NULL,
    pais          VARCHAR(80)  NOT NULL,
    PRIMARY KEY (id_aeropuerto),
    UNIQUE KEY uq_aeropuertos_iata (codigo_iata)
) ENGINE=InnoDB;
 
COMMIT;

LOAD DATA LOCAL INFILE 'C:/P6_aerolinea/01_aeropuertos.csv'
INTO TABLE aeropuertos
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(id_aeropuerto, codigo_iata, ciudad, pais);

COMMIT;
-- ------------------------------------------------------------
-- 02. rutas  (56 filas)  FK: aeropuertos (origen y destino)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS rutas;
CREATE TABLE rutas (
    id_ruta       INT NOT NULL,
    id_origen     INT NOT NULL,
    id_destino    INT NOT NULL,
    distancia_km  INT NOT NULL,
    duracion_min  INT NOT NULL,
    PRIMARY KEY (id_ruta),
    UNIQUE KEY uq_rutas_origen_destino (id_origen, id_destino),
    CONSTRAINT fk_rutas_origen  FOREIGN KEY (id_origen)  REFERENCES aeropuertos (id_aeropuerto),
    CONSTRAINT fk_rutas_destino FOREIGN KEY (id_destino) REFERENCES aeropuertos (id_aeropuerto),
    CONSTRAINT ck_rutas_distinto CHECK (id_origen <> id_destino)
) ENGINE=InnoDB;
 
LOAD DATA LOCAL INFILE 'C:/P6_aerolinea/02_rutas.csv'
INTO TABLE rutas
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(id_ruta, id_origen, id_destino, distancia_km, duracion_min);
 
COMMIT;

-- ------------------------------------------------------------
-- 03. modelos_avion  (5 filas)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS modelos_avion;
CREATE TABLE modelos_avion (
    id_modelo   INT          NOT NULL,
    fabricante  VARCHAR(50)  NOT NULL,
    nombre      VARCHAR(50)  NOT NULL,
    capacidad   SMALLINT UNSIGNED NOT NULL,
    PRIMARY KEY (id_modelo)
) ENGINE=InnoDB;
 
LOAD DATA LOCAL INFILE 'C:/P6_aerolinea/03_modelos_avion.csv'
INTO TABLE modelos_avion
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(id_modelo, fabricante, nombre, capacidad);
 
COMMIT;

-- ------------------------------------------------------------
-- 04. aviones  (31 filas)  FK: modelos_avion
--     Nota: la matricula CC-BAA aparece 2 veces en los datos
--     (id_avion 7 y 31), por eso NO lleva UNIQUE.
-- ------------------------------------------------------------
DROP TABLE IF EXISTS aviones;
CREATE TABLE aviones (
    id_avion          INT         NOT NULL,
    id_modelo         INT         NOT NULL,
    matricula         VARCHAR(15) NOT NULL,
    anio_fabricacion  SMALLINT    NOT NULL,
    PRIMARY KEY (id_avion),
    KEY idx_aviones_matricula (matricula),
    CONSTRAINT fk_aviones_modelo FOREIGN KEY (id_modelo) REFERENCES modelos_avion (id_modelo)
) ENGINE=InnoDB;
 
LOAD DATA LOCAL INFILE 'C:/P6_aerolinea/04_aviones.csv'
INTO TABLE aviones
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(id_avion, id_modelo, matricula, anio_fabricacion);
 
COMMIT;

-- ------------------------------------------------------------
-- 05. vuelos  (3,100 filas)  FK: rutas, aviones
--     salida_real viene vacia en 1105 vuelos (cancelados/programados):
--     se convierte a NULL.
-- ------------------------------------------------------------
DROP TABLE IF EXISTS vuelos;
CREATE TABLE vuelos (
    id_vuelo      INT         NOT NULL,
    id_ruta       INT         NOT NULL,
    id_avion      INT         NOT NULL,
    salida_prog   DATETIME    NOT NULL,
    salida_real   DATETIME    NULL,
    estado        VARCHAR(15) NOT NULL,
    numero_vuelo  VARCHAR(10) NOT NULL,
    PRIMARY KEY (id_vuelo),
    KEY idx_vuelos_salida_prog (salida_prog),
    KEY idx_vuelos_numero (numero_vuelo),
    CONSTRAINT fk_vuelos_ruta  FOREIGN KEY (id_ruta)  REFERENCES rutas (id_ruta),
    CONSTRAINT fk_vuelos_avion FOREIGN KEY (id_avion) REFERENCES aviones (id_avion),
    CONSTRAINT ck_vuelos_estado CHECK (estado IN ('programado', 'aterrizado', 'cancelado'))
) ENGINE=InnoDB;
 
LOAD DATA LOCAL INFILE 'C:/P6_aerolinea/05_vuelos.csv'
INTO TABLE vuelos
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(id_vuelo, id_ruta, id_avion, salida_prog, @salida_real, estado, numero_vuelo)
SET salida_real = NULLIF(@salida_real, '');
 
COMMIT;

-- ------------------------------------------------------------
-- 06. tripulantes  (440 filas)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS tripulantes;
CREATE TABLE tripulantes (
    id_tripulante  INT           NOT NULL,
    nombre         VARCHAR(100)  NOT NULL,
    cargo          VARCHAR(20)   NOT NULL,
    horas_vuelo    DECIMAL(9,1)  NOT NULL,
    PRIMARY KEY (id_tripulante)
) ENGINE=InnoDB;
 
LOAD DATA LOCAL INFILE 'C:/P6_aerolinea/06_tripulantes.csv'
INTO TABLE tripulantes
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(id_tripulante, nombre, cargo, horas_vuelo);
 
COMMIT;

-- ------------------------------------------------------------
-- 07. tripulacion_vuelo  (19,017 filas)  tabla N:M
--     FK: vuelos, tripulantes  |  PK compuesta
-- ------------------------------------------------------------
DROP TABLE IF EXISTS tripulacion_vuelo;
CREATE TABLE tripulacion_vuelo (
    id_vuelo       INT          NOT NULL,
    id_tripulante  INT          NOT NULL,
    rol            VARCHAR(30)  NOT NULL,
    PRIMARY KEY (id_vuelo, id_tripulante),
    CONSTRAINT fk_tripvuelo_vuelo      FOREIGN KEY (id_vuelo)      REFERENCES vuelos (id_vuelo),
    CONSTRAINT fk_tripvuelo_tripulante FOREIGN KEY (id_tripulante) REFERENCES tripulantes (id_tripulante)
) ENGINE=InnoDB;
 
LOAD DATA LOCAL INFILE 'C:/P6_aerolinea/07_tripulacion_vuelo.csv'
INTO TABLE tripulacion_vuelo
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(id_vuelo, id_tripulante, rol);
 
COMMIT;

-- SELECT COUNT(*) AS  vuelos FROM  vuelos;
-- SELECT COUNT(*) AS  tripulantes FROM  tripulantes;
-- SELECT COUNT(*) AS  tripulacion_vuelo FROM tripulacion_vuelo;

-- ------------------------------------------------------------
-- 08. pasajeros  (140,000 filas)
--     Nota: 38 documentos estan repetidos en los datos,
--     por eso documento NO lleva UNIQUE (solo indice).
-- ------------------------------------------------------------
DROP TABLE IF EXISTS pasajeros;
CREATE TABLE pasajeros (
    id_pasajero   INT           NOT NULL,
    documento     VARCHAR(20)   NOT NULL,
    nombre        VARCHAR(100)  NOT NULL,
    nacionalidad  VARCHAR(30)   NOT NULL,
    PRIMARY KEY (id_pasajero),
    KEY idx_pasajeros_documento (documento)
) ENGINE=InnoDB;
 
LOAD DATA LOCAL INFILE 'C:/P6_aerolinea/08_pasajeros.csv'
INTO TABLE pasajeros
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(id_pasajero, documento, nombre, nacionalidad);

 COMMIT;

-- ------------------------------------------------------------
-- 09. cuentas_millas  (87,126 filas)  FK: pasajeros (relacion 1:1)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS cuentas_millas;
CREATE TABLE cuentas_millas (
    id_cuenta    INT           NOT NULL,
    id_pasajero  INT           NOT NULL,
    nivel        VARCHAR(15)   NOT NULL,
    millas       INT UNSIGNED  NOT NULL,
    PRIMARY KEY (id_cuenta),
    UNIQUE KEY uq_cuentas_pasajero (id_pasajero),
    CONSTRAINT fk_cuentas_pasajero FOREIGN KEY (id_pasajero) REFERENCES pasajeros (id_pasajero)
) ENGINE=InnoDB;
 
LOAD DATA LOCAL INFILE 'C:/P6_aerolinea/09_cuentas_millas.csv'
INTO TABLE cuentas_millas
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(id_cuenta, id_pasajero, nivel, millas);
 
COMMIT;

-- ------------------------------------------------------------
-- 10. reservas  (266,334 filas)  FK: pasajeros
-- ------------------------------------------------------------
DROP TABLE IF EXISTS reservas;
CREATE TABLE reservas (
    id_reserva    INT          NOT NULL,
    id_pasajero   INT          NOT NULL,
    codigo_pnr    CHAR(6)      NOT NULL,
    fecha_compra  DATETIME     NOT NULL,
    canal         VARCHAR(20)  NOT NULL,
    PRIMARY KEY (id_reserva),
    UNIQUE KEY uq_reservas_pnr (codigo_pnr),
    KEY idx_reservas_fecha (fecha_compra),
    CONSTRAINT fk_reservas_pasajero FOREIGN KEY (id_pasajero) REFERENCES pasajeros (id_pasajero)
) ENGINE=InnoDB;
 
LOAD DATA LOCAL INFILE 'C:/P6_aerolinea/10_reservas.csv'
INTO TABLE reservas
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(id_reserva, id_pasajero, codigo_pnr, fecha_compra, canal);
 
COMMIT;

-- ------------------------------------------------------------
-- 11. tarifas  (6 filas)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS tarifas;
CREATE TABLE tarifas (
    id_tarifa          INT         NOT NULL,
    clase              VARCHAR(30) NOT NULL,
    nombre             VARCHAR(30) NOT NULL,
    equipaje_incluido  TINYINT(1)  NOT NULL,
    reembolsable       TINYINT(1)  NOT NULL,
    PRIMARY KEY (id_tarifa)
) ENGINE=InnoDB;
 
LOAD DATA LOCAL INFILE 'C:/P6_aerolinea/11_tarifas.csv'
INTO TABLE tarifas
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(id_tarifa, clase, nombre, equipaje_incluido, reembolsable);
 
COMMIT;

-- ------------------------------------------------------------
-- 12. boletos  (487,357 filas)  FK: reservas, vuelos, tarifas, pasajeros
--     UNIQUE (id_vuelo, asiento): impide repetir asiento en un vuelo.
--     id_pasajero es quien viaja (puede ser distinto del titular
--     de la reserva).
-- ------------------------------------------------------------
DROP TABLE IF EXISTS boletos;
CREATE TABLE boletos (
    id_boleto    INT            NOT NULL,
    id_reserva   INT            NOT NULL,
    id_vuelo     INT            NOT NULL,
    id_tarifa    INT            NOT NULL,
    asiento      VARCHAR(5)     NOT NULL,
    precio       DECIMAL(10,2)  NOT NULL,
    id_pasajero  INT            NOT NULL,
    PRIMARY KEY (id_boleto),
    UNIQUE KEY uq_boletos_vuelo_asiento (id_vuelo, asiento),
    KEY idx_boletos_pasajero (id_pasajero),
    CONSTRAINT fk_boletos_reserva  FOREIGN KEY (id_reserva)  REFERENCES reservas (id_reserva),
    CONSTRAINT fk_boletos_vuelo    FOREIGN KEY (id_vuelo)    REFERENCES vuelos (id_vuelo),
    CONSTRAINT fk_boletos_tarifa   FOREIGN KEY (id_tarifa)   REFERENCES tarifas (id_tarifa),
    CONSTRAINT fk_boletos_pasajero FOREIGN KEY (id_pasajero) REFERENCES pasajeros (id_pasajero),
    CONSTRAINT ck_boletos_precio   CHECK (precio >= 0)
) ENGINE=InnoDB;
 
LOAD DATA LOCAL INFILE 'C:/P6_aerolinea/12_boletos.csv'
INTO TABLE boletos
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(id_boleto, id_reserva, id_vuelo, id_tarifa, asiento, precio, id_pasajero);
 
COMMIT;
 
-- ------------------------------------------------------------
-- 13. equipajes  (487,687 filas)  FK: boletos
-- ------------------------------------------------------------
DROP TABLE IF EXISTS equipajes;
CREATE TABLE equipajes (
    id_equipaje  INT           NOT NULL,
    id_boleto    INT           NOT NULL,
    peso_kg      DECIMAL(5,1)  NOT NULL,
    tipo         VARCHAR(30)   NOT NULL,
    PRIMARY KEY (id_equipaje),
    CONSTRAINT fk_equipajes_boleto FOREIGN KEY (id_boleto) REFERENCES boletos (id_boleto),
    CONSTRAINT ck_equipajes_peso   CHECK (peso_kg > 0)
) ENGINE=InnoDB;
 
LOAD DATA LOCAL INFILE 'C:/P6_aerolinea/13_equipajes.csv'
INTO TABLE equipajes
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(id_equipaje, id_boleto, peso_kg, tipo);
 
COMMIT;

-- ------------------------------------------------------------
-- 14. pagos  (276,782 filas)  FK: reservas
--     Una reserva puede tener varios pagos (pago dividido).
-- ------------------------------------------------------------
DROP TABLE IF EXISTS pagos;
CREATE TABLE pagos (
    id_pago     INT            NOT NULL,
    id_reserva  INT            NOT NULL,
    monto       DECIMAL(12,2)  NOT NULL,
    moneda      CHAR(3)        NOT NULL,
    metodo      VARCHAR(30)    NOT NULL,
    PRIMARY KEY (id_pago),
    KEY idx_pagos_reserva (id_reserva),
    CONSTRAINT fk_pagos_reserva FOREIGN KEY (id_reserva) REFERENCES reservas (id_reserva),
    CONSTRAINT ck_pagos_moneda  CHECK (moneda IN ('PEN', 'USD')),
    CONSTRAINT ck_pagos_monto   CHECK (monto > 0)
) ENGINE=InnoDB;
 
LOAD DATA LOCAL INFILE 'C:/P6_aerolinea/14_pagos.csv'
INTO TABLE pagos
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(id_pago, id_reserva, monto, moneda, metodo);
 
COMMIT;

-- ============================================================
-- REACTIVAR VERIFICACIONES
-- ============================================================
SET FOREIGN_KEY_CHECKS = 1;
SET UNIQUE_CHECKS = 1;
SET AUTOCOMMIT = 1;

 -- Verificación: debe devolver 
SELECT COUNT(*) AS  tripulantes FROM  tripulantes;
SELECT * FROM  tripulantes LIMIT 5;

-- ============================================================
-- reactivar las verificaciones al final:
--  	SET FOREIGN_KEY_CHECKS = 1; SET UNIQUE_CHECKS = 1; SET AUTOCOMMIT = 1;
-- ============================================================
-- SHOW VARIABLES LIKE 'local_infile'; si dice OFF ejecuta lo siguiente:
-- SET GLOBAL local_infile = 1
-- luego click en Query > Reconect to server y vuelve a ejecutar
-- SHOW VARIABLES LIKE 'local_infile'; deberia decir ON

-- ============================================================
-- HACER CONSULTAS OPERATIVAS
-- ============================================================

-- 1. ¿Que vuelos estan disponibles para viajar de un aeropuerto
--    de origen a uno de destino en una fecha dada?
--    "Disponible" = vuelo de esa ruta y fecha que NO esta cancelado.

-- Reglas:
-- 1. Si hay vuelos en la fecha solicitada, muestra esos vuelos.
-- 2. Si no se indica fecha, muestra vuelos de todas las fechas.
-- 3. Si no hay vuelos en la fecha solicitada, muestra todos los
--    vuelos de fechas cercanas.
-- 4. muestra vuelos programados.
-- ============================================================

SET @origen = 'LIM';
SET @destino = 'JUL';
SET @fecha = '2026-11-29'; # '2026-11-29' JUL --'2026-12-15' TACNA-TCQ --'2026-11-30' NO HAY JUL--NULL

SELECT v.id_vuelo,
       v.numero_vuelo,
       ao.codigo_iata  AS origen,
       ao.ciudad       AS ciudad_origen,
       ad.codigo_iata  AS destino,
       ad.ciudad       AS ciudad_destino,
       v.salida_prog,
       v.estado,
       CASE
           WHEN @fecha IS NULL                  THEN 'Todas las fechas'
           WHEN DATE(v.salida_prog) = @fecha    THEN 'Fecha solicitada'
           ELSE 'Otra fecha'
       END AS coincidencia
FROM vuelos v
JOIN rutas       r  ON r.id_ruta        = v.id_ruta
JOIN aeropuertos ao ON ao.id_aeropuerto = r.id_origen
JOIN aeropuertos ad ON ad.id_aeropuerto = r.id_destino
WHERE ao.codigo_iata = @origen
  AND ad.codigo_iata = @destino
  AND v.estado = 'programado'
  AND (
        -- regla 2: sin fecha, no se filtra por fecha
        @fecha IS NULL
        -- vuelos de la fecha solicitada
        OR (v.salida_prog >= @fecha AND v.salida_prog < DATE_ADD(@fecha, INTERVAL 1 DAY))
        -- regla 3: si NO existe ningun vuelo ese dia, se permiten las otras fechas
        OR NOT EXISTS (
              SELECT 1
              FROM vuelos v2
              JOIN rutas       r2  ON r2.id_ruta        = v2.id_ruta
              JOIN aeropuertos ao2 ON ao2.id_aeropuerto = r2.id_origen
              JOIN aeropuertos ad2 ON ad2.id_aeropuerto = r2.id_destino
              WHERE ao2.codigo_iata = @origen
                AND ad2.codigo_iata = @destino
                AND v2.estado = 'programado'
                AND v2.salida_prog >= @fecha
                AND v2.salida_prog <  DATE_ADD(@fecha, INTERVAL 1 DAY)
        )
      )
ORDER BY ABS(DATEDIFF(DATE(v.salida_prog), @fecha)),   -- mas cercanos a @fecha primero
         v.salida_prog;

-- ============================================================
-- 2. ¿Cuales son los horarios de salida y llegada de esos vuelos?
--    La tabla vuelos no guarda la llegada: se calcula sumando
--    rutas.duracion_min a la hora de salida.
--    Los vuelos sin salida_real (programados) muestran NULL en
--    salida_real y llegada_real.
-- ============================================================

SET @fecha = '2026-11-29'; # LIM-JUL

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
WHERE ao.codigo_iata = @origen
  AND ad.codigo_iata = @destino
  AND v.salida_prog >= @fecha
  AND v.salida_prog <  DATE_ADD(@fecha, INTERVAL 1 DAY)
  AND v.estado = 'programado'
ORDER BY v.salida_prog;
 
-- ============================================================
-- 3. ¿Cual es el estado actual de cada vuelo que quiere consultar?
--    Se busca por numero de vuelo y fecha (el mismo numero se repite
--    en muchas fechas, por eso hace falta la fecha).
--    retraso_min = minutos entre la salida programada y la real
--    (negativo = salio antes de lo programado).
-- ============================================================

SET @fecha = '2026-11-29'; # '2026-11-29' --			 '2025-04-10'--		 '2026-10-24'
SET @numero_vuelo = 'LP2414' ; # 'LP2414' aun no sale -- 'LP2414' cancelado-- 'LP2797' salio antes

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
WHERE v.numero_vuelo = @numero_vuelo
  AND v.salida_prog >= @fecha
  AND v.salida_prog <  DATE_ADD(@fecha, INTERVAL 1 DAY)
ORDER BY v.salida_prog;

-- ============================================================
-- 4. ¿Que informacion tiene un vuelo especifico, incluyendo su
--    ruta, horarios y avion asignado?
--    Usa @id_vuelo. La llegada se calcula con rutas.duracion_min.
-- ============================================================
SET @id_vuelo = 2143;

SELECT v.id_vuelo,
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
WHERE v.id_vuelo = @id_vuelo;

-- ============================================================
-- 5. ¿Que tarifas y clases de servicio estan disponibles y
--    cuanto cuesta cada una?
--    La tabla tarifas no guarda precios: el precio sale de los
--    boletos (boletos.precio). Para el vuelo @id_vuelo se muestra el
--    precio minimo ("desde"), promedio y maximo de cada tarifa.
--    Si esa tarifa no se ha vendido en ese vuelo, se usa como
--    referencia la ruta completa (columna base_del_precio).
--    Nota: boletos.precio no indica la moneda.
-- ============================================================

SET @id_vuelo = 2143;

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
        WHERE id_vuelo = @id_vuelo
        GROUP BY id_tarifa
     ) pv ON pv.id_tarifa = t.id_tarifa
LEFT JOIN (
        SELECT b.id_tarifa,
               MIN(b.precio) AS precio_min,
               AVG(b.precio) AS precio_prom,
               MAX(b.precio) AS precio_max
        FROM boletos b
        JOIN vuelos vr ON vr.id_vuelo = b.id_vuelo
        WHERE vr.id_ruta = (SELECT id_ruta FROM vuelos WHERE id_vuelo = @id_vuelo)
        GROUP BY b.id_tarifa
     ) pr ON pr.id_tarifa = t.id_tarifa
ORDER BY t.id_tarifa;

-- ============================================================
-- 6. ¿Cuantos asientos hay disponibles en el vuelo seleccionado
--    para elegir opcion de viaje?
--    disponibles = capacidad del modelo de avion - boletos emitidos.
-- ============================================================
SET @id_vuelo = 2143;
-- 6a. Resumen de ocupacion
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
WHERE v.id_vuelo = @id_vuelo
GROUP BY v.id_vuelo, v.numero_vuelo, v.estado, m.nombre, m.capacidad;
 
-- 6b. Lista de asientos libres para elegir.
--     No existe una tabla de asientos: el mapa de cada modelo se
--     deduce de los asientos que aparecen en sus boletos (en los
--     datos aparecen los 144, 174, 186, 220 y 303 de cada modelo).
SELECT s.asiento
FROM (
        SELECT DISTINCT b2.asiento
        FROM boletos b2
        JOIN vuelos   v2  ON v2.id_vuelo  = b2.id_vuelo
        JOIN aviones  av2 ON av2.id_avion = v2.id_avion
        WHERE av2.id_modelo = (
                SELECT av3.id_modelo
                FROM vuelos v3
                JOIN aviones av3 ON av3.id_avion = v3.id_avion
                WHERE v3.id_vuelo = @id_vuelo)
     ) s
LEFT JOIN boletos b ON b.id_vuelo = @id_vuelo AND b.asiento = s.asiento
WHERE b.id_boleto IS NULL
ORDER BY CAST(s.asiento AS UNSIGNED), RIGHT(s.asiento, 1);

-- ============================================================
-- 7. ¿Que datos de los pasajeros se deben consultar o registrar
--    para asociarlos a la reserva?
--    Datos del pasajero: documento, nombre y nacionalidad.
--    Se asocian a la reserva de dos maneras:
--      reservas.id_pasajero = titular que compra
--      boletos.id_pasajero  = persona que viaja (puede ser otra)
-- ============================================================
-- 7a. Consultar un pasajero por documento (con su cuenta de millas
--     y cuantas reservas tiene como titular).
--     Ojo: hay 38 documentos repetidos en los datos, asi que una
--     busqueda puede devolver mas de una fila.

SET @documento=  '26787167' ; # 'P1918895' --48247946
SELECT p.id_pasajero,
       p.documento,
       p.nombre,
       p.nacionalidad,
       cm.nivel  AS nivel_millas,
       cm.millas,
       (SELECT COUNT(*) FROM reservas r WHERE r.id_pasajero = p.id_pasajero) AS reservas_como_titular
FROM pasajeros p
LEFT JOIN cuentas_millas cm ON cm.id_pasajero = p.id_pasajero
WHERE p.documento = @documento;

/*
-- 7b. Registrar un pasajero nuevo si su documento aun no existe.
--     id_pasajero no es AUTO_INCREMENT en este esquema, por eso se
--     calcula el siguiente con MAX + 1.
--     Como ejemplo corre dentro de una transaccion que termina en
--     ROLLBACK: se ve el resultado y NO queda guardado. Para guardar
--     de verdad, cambia ROLLBACK por COMMIT.
--     (En la aplicacion real conviene ejecutar antes:
--      ALTER TABLE pasajeros MODIFY id_pasajero INT NOT NULL AUTO_INCREMENT; )
START TRANSACTION;
 
INSERT INTO pasajeros (id_pasajero, documento, nombre, nacionalidad)
SELECT (SELECT COALESCE(MAX(id_pasajero), 0) + 1 FROM pasajeros),
       @nuevo_documento, @nuevo_nombre, @nuevo_nacionalidad
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM pasajeros WHERE documento = @nuevo_documento);
 
SELECT ROW_COUNT() AS filas_insertadas;   -- 1 = registrado, 0 = el documento ya existia
 
SELECT * FROM pasajeros WHERE documento = @nuevo_documento;
 
ROLLBACK;   -- cambia a COMMIT para guardar el pasajero
COMMIT; 
*/

-- ============================================================
-- 10. ¿Que boletos se han emitido para una reserva y que tarifa
--     y clase de servicio tiene cada uno?
--     Se busca por codigo_pnr. Devuelve una fila por boleto.
-- ============================================================
SET @codigo_pnr = 'AVX8DH' ; # 'LBEFDO' --'AVX8DH' personas en el vuelo compran boletos no asientos

SELECT b.id_boleto,
       pv.nombre        AS pasajero,
       v.numero_vuelo,
       v.salida_prog,
       b.asiento,
       t.clase,
       t.nombre         AS tarifa,
       IF(t.equipaje_incluido = 1, 'Si', 'No') AS equipaje_incluido,
       IF(t.reembolsable      = 1, 'Si', 'No') AS reembolsable,
       b.precio
FROM reservas r
JOIN boletos   b  ON b.id_reserva   = r.id_reserva
JOIN tarifas   t  ON t.id_tarifa    = b.id_tarifa
JOIN pasajeros pv ON pv.id_pasajero = b.id_pasajero
JOIN vuelos    v  ON v.id_vuelo     = b.id_vuelo
WHERE r.codigo_pnr = @codigo_pnr
ORDER BY v.salida_prog, b.id_boleto;

-- ============================================================
-- 11. ¿Que pagos estan asociados a una reserva y cual es el
--     estado de cada transaccion?
--     Se busca por codigo_pnr. Devuelve una fila por pago.
--     OJO: la tabla pagos NO tiene columna de estado (solo monto,
--     moneda y metodo). Por eso "estado_pago_reserva" se DEDUCE:
--     'Pagada completa' si lo pagado cubre el total de los boletos,
--     'Pago parcial' si no. Se compara en dolares: los boletos
--     parecen estar en USD y los pagos en PEN se convierten con
--     @tipo_cambio (en los datos el cambio usado es 3.75).
-- ============================================================
SET @tipo_cambio = 3.75;
SET @codigo_pnr = 'AVX8DH';

SELECT r.codigo_pnr,
       p.id_pago,
       ROW_NUMBER() OVER (PARTITION BY r.id_reserva ORDER BY p.id_pago) AS n_pago,
       COUNT(*)     OVER (PARTITION BY r.id_reserva)                    AS pagos_de_la_reserva,
       p.metodo,
       p.moneda,
       p.monto,
       ROUND(CASE p.moneda WHEN 'USD' THEN p.monto ELSE p.monto / @tipo_cambio END, 2) AS monto_usd,
       CASE
           WHEN SUM(CASE p.moneda WHEN 'USD' THEN p.monto ELSE p.monto / @tipo_cambio END)
                    OVER (PARTITION BY r.id_reserva)
                >= (SELECT SUM(b.precio) FROM boletos b WHERE b.id_reserva = r.id_reserva) - 0.01
           THEN 'Pagada completa'
           ELSE 'Pago parcial'
       END AS estado_pago_reserva
FROM reservas r
JOIN pagos p ON p.id_reserva = r.id_reserva
WHERE r.codigo_pnr = @codigo_pnr
ORDER BY p.id_pago;

-- ============================================================
-- 12. ¿Cual es el importe total registrado para una reserva y
--     cuanto se ha pagado hasta el momento?
--     Se busca por codigo_pnr. Devuelve una fila.
--     importe_total = boletos + cargo de equipaje, donde el cargo es
--     @cargo_bodega (35 USD) por cada maleta tipo 'Bodega' de un boleto
--     cuya tarifa NO incluye equipaje. Esta regla se dedujo de los datos
--     (no existe un precio de equipaje en ninguna tabla) y reproduce
--     exactamente lo pagado en las 266,334 reservas.
--     Los pagos en PEN se convierten a USD con @tipo_cambio.
-- ============================================================

SET @codigo_pnr = 'AVX8DH';
SET @tipo_cambio = 3.75;
SET @cargo_bodega = 35;

WITH res AS (
    SELECT id_reserva, codigo_pnr
    FROM reservas
    WHERE codigo_pnr = @codigo_pnr
),
tb AS (
    SELECT b.id_reserva,
           COUNT(*)      AS n_boletos,
           SUM(b.precio) AS importe_boletos
    FROM boletos b
    JOIN res ON res.id_reserva = b.id_reserva
    GROUP BY b.id_reserva
),
eqp AS (
    SELECT b.id_reserva,
           COUNT(*) AS maletas_con_cargo
    FROM boletos b
    JOIN res       ON res.id_reserva = b.id_reserva
    JOIN tarifas t ON t.id_tarifa    = b.id_tarifa AND t.equipaje_incluido = 0
    JOIN equipajes e ON e.id_boleto  = b.id_boleto AND e.tipo = 'Bodega'
    GROUP BY b.id_reserva
),
pg AS (
    SELECT p.id_reserva,
           COUNT(*)       AS n_pagos,
           MIN(p.moneda)  AS moneda_pago,
           SUM(p.monto)   AS pagado_moneda_pago,
           SUM(CASE p.moneda WHEN 'USD' THEN p.monto ELSE p.monto / COALESCE(@tipo_cambio, 3.75) END) AS pagado_usd
    FROM pagos p
    JOIN res ON res.id_reserva = p.id_reserva
    GROUP BY p.id_reserva
)
SELECT res.codigo_pnr,
       tb.n_boletos,
       tb.importe_boletos,
       COALESCE(eqp.maletas_con_cargo, 0)                    AS maletas_con_cargo,
       COALESCE(eqp.maletas_con_cargo, 0) * COALESCE(@cargo_bodega, 35)    AS cargo_equipaje,
       ROUND(tb.importe_boletos + COALESCE(eqp.maletas_con_cargo, 0) * COALESCE(@cargo_bodega, 35), 2) AS importe_total_usd,
       COALESCE(pg.n_pagos, 0)                               AS n_pagos,
       pg.moneda_pago,
       pg.pagado_moneda_pago,
       ROUND(COALESCE(pg.pagado_usd, 0), 2)                  AS pagado_usd,
       ROUND(GREATEST(tb.importe_boletos + COALESCE(eqp.maletas_con_cargo, 0) * COALESCE(@cargo_bodega, 35)
                      - COALESCE(pg.pagado_usd, 0), 0), 2)   AS saldo_pendiente_usd,
       CASE
           WHEN COALESCE(pg.pagado_usd, 0)
                >= tb.importe_boletos + COALESCE(eqp.maletas_con_cargo, 0) * COALESCE(@cargo_bodega, 35) - 0.01
           THEN 'Pagada completa'
           ELSE 'Pago parcial'
       END AS estado_pago
FROM res
JOIN tb        ON tb.id_reserva  = res.id_reserva
LEFT JOIN eqp  ON eqp.id_reserva = res.id_reserva
LEFT JOIN pg   ON pg.id_reserva  = res.id_reserva;

 
-- ============================================================
-- 13. ¿Que boletos corresponden a un pasajero y a que vuelos le
--     permiten acceder?
--     Se busca por @id_pasajero (usa la 7a para encontrarlo por
--     documento: hay documentos repetidos, el id es exacto).
--     Se listan los boletos donde el pasajero VIAJA (boletos.id_pasajero),
--     aunque la reserva este a nombre de otro titular.
--     situacion_boleto se deduce del estado del vuelo.
-- ============================================================
SET @id_pasajero = 12;

SELECT b.id_boleto,
       r.codigo_pnr,
       pt.nombre      AS titular_reserva,
       v.numero_vuelo,
       ao.codigo_iata AS origen,
       ad.codigo_iata AS destino,
       v.salida_prog,
       DATE_ADD(v.salida_prog, INTERVAL ru.duracion_min MINUTE) AS llegada_prog,
       v.estado       AS estado_vuelo,
       CASE v.estado
           WHEN 'programado' THEN 'Pendiente de volar'
           WHEN 'cancelado'  THEN 'Vuelo cancelado'
           ELSE 'Ya volado'
       END            AS situacion_boleto,
       b.asiento,
       t.clase,
       t.nombre       AS tarifa,
       b.precio
FROM boletos b
JOIN reservas    r  ON r.id_reserva     = b.id_reserva
JOIN pasajeros   pt ON pt.id_pasajero   = r.id_pasajero
JOIN vuelos      v  ON v.id_vuelo       = b.id_vuelo
JOIN rutas       ru ON ru.id_ruta       = v.id_ruta
JOIN aeropuertos ao ON ao.id_aeropuerto = ru.id_origen
JOIN aeropuertos ad ON ad.id_aeropuerto = ru.id_destino
JOIN tarifas     t  ON t.id_tarifa      = b.id_tarifa
WHERE b.id_pasajero = @id_pasajero
ORDER BY v.salida_prog, b.id_boleto;

-- ============================================================
-- 14. ¿Que reservas tiene registradas un pasajero y cuales son
--     sus estados actuales?
--     Usa @id_pasajero. Incluye las reservas donde es TITULAR y
--     aquellas donde solo VIAJA (columna "rol").
--     La tabla reservas NO tiene columna de estado: se DEDUCE asi
--       Cancelada              = todos sus vuelos estan cancelados
--       Pendiente de pago      = lo pagado no cubre el importe total
--       Parcialmente cancelada = algun vuelo cancelado y otros no
--       Confirmada             = el resto (pagada y sin cancelaciones)
--     El importe total y el pago se calculan como en la consulta 12.
-- ============================================================

SET @id_pasajero = 12;

WITH ids AS (
    SELECT id_reserva FROM reservas WHERE id_pasajero = @id_pasajero
    UNION
    SELECT id_reserva FROM boletos  WHERE id_pasajero = @id_pasajero
),
bol AS (
    SELECT b.id_reserva,
           COUNT(*)                          AS n_boletos,
           SUM(b.id_pasajero = @id_pasajero) AS boletos_del_pasajero,
           SUM(b.precio)                     AS importe_boletos,
           SUM(v.estado = 'cancelado')       AS n_cancelados,
           MIN(v.salida_prog)                AS primer_vuelo
    FROM boletos b
    JOIN ids         ON ids.id_reserva = b.id_reserva
    JOIN vuelos v    ON v.id_vuelo     = b.id_vuelo
    GROUP BY b.id_reserva
),
car AS (
    SELECT b.id_reserva, COUNT(*) AS maletas
    FROM boletos b
    JOIN ids         ON ids.id_reserva = b.id_reserva
    JOIN tarifas t   ON t.id_tarifa    = b.id_tarifa AND t.equipaje_incluido = 0
    JOIN equipajes e ON e.id_boleto    = b.id_boleto AND e.tipo = 'Bodega'
    GROUP BY b.id_reserva
),
pag AS (
    SELECT p.id_reserva,
           SUM(CASE p.moneda WHEN 'USD' THEN p.monto
                             ELSE p.monto / COALESCE(@tipo_cambio, 3.75) END) AS pagado_usd
    FROM pagos p
    JOIN ids ON ids.id_reserva = p.id_reserva
    GROUP BY p.id_reserva
),
calc AS (
    SELECT r.id_reserva, r.codigo_pnr, r.fecha_compra, r.canal, r.id_pasajero AS id_titular,
           bol.n_boletos, bol.boletos_del_pasajero, bol.n_cancelados, bol.primer_vuelo,
           bol.importe_boletos + COALESCE(@cargo_bodega, 35) * COALESCE(car.maletas, 0) AS importe_total,
           COALESCE(pag.pagado_usd, 0) AS pagado
    FROM ids
    JOIN reservas r   ON r.id_reserva   = ids.id_reserva
    JOIN bol          ON bol.id_reserva = ids.id_reserva
    LEFT JOIN car     ON car.id_reserva = ids.id_reserva
    LEFT JOIN pag     ON pag.id_reserva = ids.id_reserva
)
SELECT c.codigo_pnr,
       c.fecha_compra,
       c.canal,
       IF(c.id_titular = @id_pasajero, 'Titular', 'Pasajero') AS rol,
       pt.nombre                       AS titular,
       c.n_boletos,
       c.boletos_del_pasajero,
       c.primer_vuelo,
       ROUND(c.importe_total, 2)       AS importe_total_usd,
       ROUND(c.pagado, 2)              AS pagado_usd,
       ROUND(GREATEST(c.importe_total - c.pagado, 0), 2) AS saldo_pendiente_usd,
       CASE
           WHEN c.n_cancelados = c.n_boletos            THEN 'Cancelada'
           WHEN c.pagado < c.importe_total - 0.01       THEN 'Pendiente de pago'
           WHEN c.n_cancelados > 0                      THEN 'Parcialmente cancelada'
           ELSE 'Confirmada'
       END AS estado_reserva
FROM calc c
JOIN pasajeros pt ON pt.id_pasajero = c.id_titular
ORDER BY c.fecha_compra, c.id_reserva;

-- ============================================================
-- 16. ¿Que informacion de equipaje esta registrada para una
--     reserva o un pasajero, incluyendo peso y tipo?
--     cargo_usd sigue la regla de la consulta 12: 35 USD por cada
--     maleta 'Bodega' en un boleto cuya tarifa no incluye equipaje.
-- ============================================================

SET @codigo_pnr = 'AVX8DH';
SET @cargo_bodega = 35;

-- 16a. Equipaje de una reserva (usa @codigo_pnr)
SELECT r.codigo_pnr,
       e.id_equipaje,
       b.id_boleto,
       pv.nombre        AS pasajero,
       v.numero_vuelo,
       v.salida_prog,
       e.tipo,
       e.peso_kg,
       t.nombre         AS tarifa,
       IF(t.equipaje_incluido = 1, 'Si', 'No') AS equipaje_incluido_en_tarifa,
       CASE WHEN e.tipo = 'Bodega' AND t.equipaje_incluido = 0
            THEN COALESCE(@cargo_bodega, 35) ELSE 0 END AS cargo_usd
FROM reservas r
JOIN boletos   b  ON b.id_reserva   = r.id_reserva
JOIN equipajes e  ON e.id_boleto    = b.id_boleto
JOIN pasajeros pv ON pv.id_pasajero = b.id_pasajero
JOIN vuelos    v  ON v.id_vuelo     = b.id_vuelo
JOIN tarifas   t  ON t.id_tarifa    = b.id_tarifa
WHERE r.codigo_pnr = @codigo_pnr
ORDER BY v.salida_prog, b.id_boleto, e.id_equipaje;
 
-- 16b. Equipaje de un pasajero (usa @id_pasajero): todas las piezas de
--      los boletos donde el pasajero viaja.
SELECT r.codigo_pnr,
       e.id_equipaje,
       b.id_boleto,
       v.numero_vuelo,
       v.salida_prog,
       e.tipo,
       e.peso_kg,
       t.nombre         AS tarifa,
       IF(t.equipaje_incluido = 1, 'Si', 'No') AS equipaje_incluido_en_tarifa,
       CASE WHEN e.tipo = 'Bodega' AND t.equipaje_incluido = 0
            THEN COALESCE(@cargo_bodega, 35) ELSE 0 END AS cargo_usd
FROM boletos   b
JOIN reservas  r  ON r.id_reserva = b.id_reserva
JOIN equipajes e  ON e.id_boleto  = b.id_boleto
JOIN vuelos    v  ON v.id_vuelo   = b.id_vuelo
JOIN tarifas   t  ON t.id_tarifa  = b.id_tarifa
WHERE b.id_pasajero = @id_pasajero
ORDER BY v.salida_prog, b.id_boleto, e.id_equipaje;

-- ============================================================
-- 17. ¿Que vuelos presentan retrasos y cuales son sus horarios
--     programados y reales, si estan registrados?
--     Retraso = minutos entre salida_prog y salida_real. Solo hay
--     salida_real en vuelos que ya salieron. Filtros: @min_retraso
--     (en la practica un vuelo "retrasado" suele ser >= 15 min; usa 1
--     para ver cualquier retraso) y el rango @fecha_desde / @fecha_hasta
--     (NULL = sin limite). Muestra los 100 mas retrasados: quita el
--     LIMIT para verlos todos.
-- ============================================================
SET @min_retraso = 15;
SET @fecha_desde = '2025-12-01';
SET @fecha_hasta = '2025-12-31';

SELECT v.id_vuelo,
       v.numero_vuelo,
       ao.codigo_iata AS origen,
       ad.codigo_iata AS destino,
       v.salida_prog,
       v.salida_real,
       TIMESTAMPDIFF(MINUTE, v.salida_prog, v.salida_real) AS retraso_min,
       DATE_ADD(v.salida_prog, INTERVAL ru.duracion_min MINUTE) AS llegada_prog,
       DATE_ADD(v.salida_real, INTERVAL ru.duracion_min MINUTE) AS llegada_real,
       v.estado
FROM vuelos v
JOIN rutas       ru ON ru.id_ruta       = v.id_ruta
JOIN aeropuertos ao ON ao.id_aeropuerto = ru.id_origen
JOIN aeropuertos ad ON ad.id_aeropuerto = ru.id_destino
WHERE v.salida_real IS NOT NULL
  AND TIMESTAMPDIFF(MINUTE, v.salida_prog, v.salida_real) >= COALESCE(@min_retraso, 15)
  AND (@fecha_desde IS NULL OR v.salida_prog >= @fecha_desde)
  AND (@fecha_hasta IS NULL OR v.salida_prog <  DATE_ADD(@fecha_hasta, INTERVAL 1 DAY))
ORDER BY retraso_min DESC, v.salida_prog;
-- LIMIT 100;

-- ============================================================
-- 19. ¿Que tripulantes estan asignados a un vuelo determinado y
--     cuales son sus funciones?
--     Usa @id_vuelo. "rol" es la funcion en ese vuelo
--     (tripulacion_vuelo.rol); "cargo" es el puesto del tripulante.
--     Cada vuelo tiene entre 5 y 10 tripulantes.
-- ============================================================
SET @id_vuelo = 2143; # 2148
SELECT v.id_vuelo,
       v.numero_vuelo,
       v.salida_prog,
       tv.rol,
       t.id_tripulante,
       t.nombre,
       t.cargo,
       t.horas_vuelo
FROM vuelos v
JOIN tripulacion_vuelo tv ON tv.id_vuelo      = v.id_vuelo
JOIN tripulantes       t  ON t.id_tripulante  = tv.id_tripulante
WHERE v.id_vuelo = @id_vuelo
ORDER BY FIELD(tv.rol, 'Capitán', 'Primer Oficial', 'Jefe de cabina', 'TCP'), t.nombre;
 