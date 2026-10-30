-- ============================================================
-- SEMANA 2: CONSULTAS ANALITICAS, VISTAS, PROCEDIMIENTO Y TRIGGER
-- Proyecto: Aerolinea - Reservas, Vuelos y Puntualidad
-- Base: aerolinea (MySQL 8)
-- Supuesto: boletos.precio esta en USD (igual que en sus consultas 11 y 12)
-- Ejecuta cada bloque por separado y toma captura del resultado.
-- ============================================================
USE aerolinea;

-- ============================================================
-- A. CONSULTAS ANALITICAS
-- ============================================================

-- A1. OCUPACION DE VUELOS (JOIN de 5 tablas, vuelos con mas ocupacion)
SELECT v.id_vuelo,
       v.numero_vuelo,
       CONCAT(ao.codigo_iata, '-', ad.codigo_iata) AS ruta,
       v.salida_prog,
       v.estado,
       m.capacidad,
       COUNT(b.id_boleto)                                  AS boletos,
       ROUND(COUNT(b.id_boleto) / m.capacidad * 100, 1)    AS ocupacion_pct
FROM vuelos v
JOIN rutas         r  ON r.id_ruta        = v.id_ruta
JOIN aeropuertos   ao ON ao.id_aeropuerto = r.id_origen
JOIN aeropuertos   ad ON ad.id_aeropuerto = r.id_destino
JOIN aviones       av ON av.id_avion      = v.id_avion
JOIN modelos_avion m  ON m.id_modelo      = av.id_modelo
LEFT JOIN boletos  b  ON b.id_vuelo       = v.id_vuelo
WHERE v.estado <> 'cancelado'
GROUP BY v.id_vuelo, v.numero_vuelo, ao.codigo_iata, ad.codigo_iata,
         v.salida_prog, v.estado, m.capacidad
ORDER BY ocupacion_pct DESC
LIMIT 50;

-- A2. FACTOR DE OCUPACION PROMEDIO POR RUTA (CTE)
WITH ocup AS (
    SELECT v.id_vuelo, v.id_ruta, m.capacidad, COUNT(b.id_boleto) AS boletos
    FROM vuelos v
    JOIN aviones       av ON av.id_avion = v.id_avion
    JOIN modelos_avion m  ON m.id_modelo = av.id_modelo
    LEFT JOIN boletos  b  ON b.id_vuelo  = v.id_vuelo
    WHERE v.estado <> 'cancelado'
    GROUP BY v.id_vuelo, v.id_ruta, m.capacidad
)
SELECT CONCAT(ao.codigo_iata, '-', ad.codigo_iata) AS ruta,
       COUNT(*)                                     AS vuelos,
       ROUND(AVG(o.boletos / o.capacidad) * 100, 1) AS ocupacion_prom_pct
FROM ocup o
JOIN rutas       r  ON r.id_ruta        = o.id_ruta
JOIN aeropuertos ao ON ao.id_aeropuerto = r.id_origen
JOIN aeropuertos ad ON ad.id_aeropuerto = r.id_destino
GROUP BY ao.codigo_iata, ad.codigo_iata
ORDER BY ocupacion_prom_pct DESC;

-- A3. INGRESOS POR RUTA Y CLASE CON ROLLUP
--     GROUPING() distingue las filas de subtotal y total general.
SELECT CASE WHEN GROUPING(ao.codigo_iata) = 1 THEN 'TOTAL GENERAL'
            ELSE ao.codigo_iata END AS origen,
       CASE WHEN GROUPING(ad.codigo_iata) = 1 THEN '(todos)'
            ELSE ad.codigo_iata END AS destino,
       CASE WHEN GROUPING(t.clase) = 1 THEN '(todas)'
            ELSE t.clase END        AS clase,
       COUNT(*)                     AS boletos,
       ROUND(SUM(b.precio), 2)      AS ingresos_usd
FROM boletos b
JOIN vuelos      v  ON v.id_vuelo       = b.id_vuelo
JOIN rutas       r  ON r.id_ruta        = v.id_ruta
JOIN aeropuertos ao ON ao.id_aeropuerto = r.id_origen
JOIN aeropuertos ad ON ad.id_aeropuerto = r.id_destino
JOIN tarifas     t  ON t.id_tarifa      = b.id_tarifa
WHERE v.estado <> 'cancelado'
GROUP BY ao.codigo_iata, ad.codigo_iata, t.clase WITH ROLLUP;

-- A4. HORAS DE VUELO POR TRIPULANTE
--     Se calcula desde los vuelos aterrizados (duracion de la ruta) y se
--     compara con el campo derivado tripulantes.horas_vuelo.
SELECT t.id_tripulante,
       t.nombre,
       t.cargo,
       COUNT(*)                                   AS vuelos,
       ROUND(SUM(r.duracion_min) / 60, 1)         AS horas_calculadas,
       t.horas_vuelo                              AS horas_registradas,
       ROUND(t.horas_vuelo - SUM(r.duracion_min) / 60, 1) AS diferencia
FROM tripulantes t
JOIN tripulacion_vuelo tv ON tv.id_tripulante = t.id_tripulante
JOIN vuelos v             ON v.id_vuelo       = tv.id_vuelo
JOIN rutas  r             ON r.id_ruta        = v.id_ruta
WHERE v.estado = 'aterrizado'
GROUP BY t.id_tripulante, t.nombre, t.cargo, t.horas_vuelo
ORDER BY horas_calculadas DESC
LIMIT 50;

-- A5. VENTANA 1: ranking de rutas por ingresos dentro de cada origen
WITH ing AS (
    SELECT ao.codigo_iata AS origen,
           ad.codigo_iata AS destino,
           SUM(b.precio)  AS ingresos
    FROM boletos b
    JOIN vuelos      v  ON v.id_vuelo       = b.id_vuelo
    JOIN rutas       r  ON r.id_ruta        = v.id_ruta
    JOIN aeropuertos ao ON ao.id_aeropuerto = r.id_origen
    JOIN aeropuertos ad ON ad.id_aeropuerto = r.id_destino
    WHERE v.estado <> 'cancelado'
    GROUP BY ao.codigo_iata, ad.codigo_iata
)
SELECT origen, destino, ROUND(ingresos, 2) AS ingresos_usd,
       RANK() OVER (PARTITION BY origen ORDER BY ingresos DESC) AS puesto_en_origen,
       ROUND(100 * ingresos / SUM(ingresos) OVER (PARTITION BY origen), 1) AS pct_del_origen
FROM ing
ORDER BY origen, puesto_en_origen;

-- A6. VENTANA 2: ingresos mensuales con acumulado y variacion vs mes anterior
WITH mensual AS (
    SELECT DATE_FORMAT(rs.fecha_compra, '%Y-%m') AS mes,
           SUM(b.precio) AS ingresos
    FROM boletos b
    JOIN reservas rs ON rs.id_reserva = b.id_reserva
    GROUP BY DATE_FORMAT(rs.fecha_compra, '%Y-%m')
)
SELECT mes,
       ROUND(ingresos, 2) AS ingresos_usd,
       ROUND(SUM(ingresos) OVER (ORDER BY mes), 2) AS acumulado_usd,
       ROUND(100 * (ingresos - LAG(ingresos) OVER (ORDER BY mes))
                 / LAG(ingresos) OVER (ORDER BY mes), 1) AS variacion_pct
FROM mensual
ORDER BY mes;

-- A7. PUNTUALIDAD: retraso promedio por ruta (solo vuelos que ya salieron)
SELECT CONCAT(ao.codigo_iata, '-', ad.codigo_iata) AS ruta,
       COUNT(*) AS vuelos_salidos,
       ROUND(AVG(TIMESTAMPDIFF(MINUTE, v.salida_prog, v.salida_real)), 1) AS retraso_prom_min,
       ROUND(100 * SUM(TIMESTAMPDIFF(MINUTE, v.salida_prog, v.salida_real) >= 15)
                 / COUNT(*), 1) AS pct_retrasados_15min
FROM vuelos v
JOIN rutas       r  ON r.id_ruta        = v.id_ruta
JOIN aeropuertos ao ON ao.id_aeropuerto = r.id_origen
JOIN aeropuertos ad ON ad.id_aeropuerto = r.id_destino
WHERE v.salida_real IS NOT NULL
GROUP BY ao.codigo_iata, ad.codigo_iata
ORDER BY retraso_prom_min DESC;

-- A8. SUBCONSULTA: pasajeros que gastaron mas que el promedio de gasto
SELECT p.id_pasajero, p.nombre, cm.nivel, ROUND(g.gasto, 2) AS gasto_usd
FROM (SELECT id_pasajero, SUM(precio) AS gasto
      FROM boletos GROUP BY id_pasajero) g
JOIN pasajeros p            ON p.id_pasajero = g.id_pasajero
LEFT JOIN cuentas_millas cm ON cm.id_pasajero = p.id_pasajero
WHERE g.gasto > (SELECT AVG(gasto)
                 FROM (SELECT SUM(precio) AS gasto
                       FROM boletos GROUP BY id_pasajero) x)
ORDER BY g.gasto DESC
LIMIT 30;

-- ============================================================
-- B. VISTAS
-- ============================================================

-- B1. Ocupacion de cada vuelo
CREATE OR REPLACE VIEW v_ocupacion_vuelo AS
SELECT v.id_vuelo,
       v.numero_vuelo,
       CONCAT(ao.codigo_iata, '-', ad.codigo_iata) AS ruta,
       v.salida_prog,
       v.estado,
       m.capacidad,
       COUNT(b.id_boleto)                               AS boletos,
       m.capacidad - COUNT(b.id_boleto)                 AS asientos_disponibles,
       ROUND(COUNT(b.id_boleto) / m.capacidad * 100, 1) AS ocupacion_pct
FROM vuelos v
JOIN rutas         r  ON r.id_ruta        = v.id_ruta
JOIN aeropuertos   ao ON ao.id_aeropuerto = r.id_origen
JOIN aeropuertos   ad ON ad.id_aeropuerto = r.id_destino
JOIN aviones       av ON av.id_avion      = v.id_avion
JOIN modelos_avion m  ON m.id_modelo      = av.id_modelo
LEFT JOIN boletos  b  ON b.id_vuelo       = v.id_vuelo
GROUP BY v.id_vuelo, v.numero_vuelo, ao.codigo_iata, ad.codigo_iata,
         v.salida_prog, v.estado, m.capacidad;

-- B2. Puntualidad por ruta
CREATE OR REPLACE VIEW v_puntualidad_ruta AS
SELECT CONCAT(ao.codigo_iata, '-', ad.codigo_iata) AS ruta,
       COUNT(*) AS vuelos_salidos,
       ROUND(AVG(TIMESTAMPDIFF(MINUTE, v.salida_prog, v.salida_real)), 1) AS retraso_prom_min,
       ROUND(100 * SUM(TIMESTAMPDIFF(MINUTE, v.salida_prog, v.salida_real) >= 15)
                 / COUNT(*), 1) AS pct_retrasados_15min
FROM vuelos v
JOIN rutas       r  ON r.id_ruta        = v.id_ruta
JOIN aeropuertos ao ON ao.id_aeropuerto = r.id_origen
JOIN aeropuertos ad ON ad.id_aeropuerto = r.id_destino
WHERE v.salida_real IS NOT NULL
GROUP BY ao.codigo_iata, ad.codigo_iata;

-- Prueba de las vistas
SELECT * FROM v_ocupacion_vuelo ORDER BY ocupacion_pct DESC LIMIT 10;
SELECT * FROM v_puntualidad_ruta ORDER BY retraso_prom_min DESC LIMIT 10;

-- ============================================================
-- C. PROCEDIMIENTO ALMACENADO
--    sp_registrar_salida_real: registra la salida real de un vuelo,
--    valida el estado y devuelve el retraso. Usa transaccion.
--    Nota: como el modelo solo tiene los estados programado /
--    aterrizado / cancelado, registrar la salida lo marca aterrizado.
-- ============================================================
DROP PROCEDURE IF EXISTS sp_registrar_salida_real;
DELIMITER $$
CREATE PROCEDURE sp_registrar_salida_real(
    IN p_id_vuelo     INT,
    IN p_salida_real  DATETIME
)
BEGIN
    DECLARE v_estado VARCHAR(15) DEFAULT NULL;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    SELECT estado INTO v_estado
    FROM vuelos
    WHERE id_vuelo = p_id_vuelo
    FOR UPDATE;

    IF v_estado IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El vuelo no existe';
    ELSEIF v_estado = 'cancelado' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No se puede registrar la salida de un vuelo cancelado';
    ELSEIF p_salida_real IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Debe indicar la hora real de salida';
    END IF;

    UPDATE vuelos
    SET salida_real = p_salida_real,
        estado      = 'aterrizado'
    WHERE id_vuelo = p_id_vuelo;

    COMMIT;

    SELECT id_vuelo, numero_vuelo, salida_prog, salida_real, estado,
           TIMESTAMPDIFF(MINUTE, salida_prog, salida_real) AS retraso_min
    FROM vuelos
    WHERE id_vuelo = p_id_vuelo;
END$$
DELIMITER ;

-- Prueba (no deja cambios: se revierte). Ejecutar estas lineas juntas:
-- START TRANSACTION;
-- CALL sp_registrar_salida_real(
--      (SELECT id_vuelo FROM vuelos WHERE estado = 'programado' LIMIT 1),
--      NOW());
-- ROLLBACK;
-- Prueba de error (vuelo cancelado):
-- CALL sp_registrar_salida_real(
--      (SELECT id_vuelo FROM vuelos WHERE estado = 'cancelado' LIMIT 1), NOW());

-- ============================================================
-- D. TRIGGER
--    trg_boletos_validar: antes de emitir un boleto verifica que el
--    vuelo no este cancelado y que todavia haya asientos segun la
--    capacidad del modelo de avion.
--    (Mas adelante este mismo trigger puede permitir sobreventa
--    controlada con un limite de overbooking.)
-- ============================================================
DROP TRIGGER IF EXISTS trg_boletos_validar;
DELIMITER $$
CREATE TRIGGER trg_boletos_validar
BEFORE INSERT ON boletos
FOR EACH ROW
BEGIN
    DECLARE v_estado    VARCHAR(15);
    DECLARE v_capacidad INT;
    DECLARE v_ocupados  INT;

    SELECT v.estado, m.capacidad
      INTO v_estado, v_capacidad
    FROM vuelos v
    JOIN aviones       av ON av.id_avion = v.id_avion
    JOIN modelos_avion m  ON m.id_modelo = av.id_modelo
    WHERE v.id_vuelo = NEW.id_vuelo;

    IF v_estado = 'cancelado' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'No se pueden emitir boletos para un vuelo cancelado';
    END IF;

    SELECT COUNT(*) INTO v_ocupados
    FROM boletos
    WHERE id_vuelo = NEW.id_vuelo;

    IF v_ocupados >= v_capacidad THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'El vuelo esta lleno: no hay asientos disponibles';
    END IF;
END$$
DELIMITER ;

-- Prueba 1: vuelo cancelado -> debe dar error 'No se pueden emitir boletos...'
-- (ejecutar las lineas juntas)
-- START TRANSACTION;
-- INSERT INTO boletos (id_boleto, id_reserva, id_vuelo, id_tarifa, asiento, precio, id_pasajero)
-- VALUES ((SELECT MAX(id_boleto) + 1 FROM (SELECT id_boleto FROM boletos) t),
--         1, (SELECT id_vuelo FROM vuelos WHERE estado = 'cancelado' LIMIT 1),
--         1, '99Z', 100, 1);
-- ROLLBACK;

-- Prueba 2: vuelo programado con asientos libres -> debe insertar (se revierte)
-- START TRANSACTION;
-- INSERT INTO boletos (id_boleto, id_reserva, id_vuelo, id_tarifa, asiento, precio, id_pasajero)
-- VALUES ((SELECT MAX(id_boleto) + 1 FROM (SELECT id_boleto FROM boletos) t),
--         1, (SELECT id_vuelo FROM vuelos WHERE estado = 'programado' LIMIT 1),
--         1, '99Z', 100, 1);
-- ROLLBACK;
