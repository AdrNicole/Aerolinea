-- CONSULTAS DE LECTURA - ETAPA 3 Y 4 (MySQL / MariaDB modernos)
-- No INSERT, UPDATE, DELETE, TRUNCATE, CREATE ni LOAD DATA.
-- Precio dinámico/IPC/TC se calculan en Python: servicio_precios.py + precio_strategy.py.
USE aerolinea;
SET @id_vuelo := 3101;

-- 1. Información del vuelo para cotizar (ruta, horario, capacidad, plazas libres)
SELECT v.id_vuelo, v.id_ruta, v.numero_vuelo, v.estado,
       ao.codigo_iata AS origen, ad.codigo_iata AS destino,
       v.salida_prog,
       DATE_ADD(v.salida_prog, INTERVAL r.duracion_min MINUTE) AS llegada_prog,
       r.duracion_min,
       m.fabricante, m.nombre AS modelo, m.capacidad,
       COUNT(b.id_boleto) AS ocupados,
       m.capacidad - COUNT(b.id_boleto) AS libres
FROM vuelos v
JOIN rutas r ON r.id_ruta = v.id_ruta
JOIN aeropuertos ao ON ao.id_aeropuerto = r.id_origen
JOIN aeropuertos ad ON ad.id_aeropuerto = r.id_destino
JOIN aviones av ON av.id_avion = v.id_avion
JOIN modelos_avion m ON m.id_modelo = av.id_modelo
LEFT JOIN boletos b ON b.id_vuelo = v.id_vuelo
WHERE v.id_vuelo = @id_vuelo
GROUP BY v.id_vuelo, v.id_ruta, v.numero_vuelo, v.estado,
         ao.codigo_iata, ad.codigo_iata, v.salida_prog,
         r.duracion_min, m.fabricante, m.nombre, m.capacidad;

-- 2. Catálogo de tarifas. El importe se obtiene de Strategy en Python.
SELECT id_tarifa, clase, nombre, equipaje_incluido, reembolsable
FROM tarifas ORDER BY id_tarifa;

-- 3. Etiquetas históricas por modelo para presentar un mapa genérico de plazas.
SELECT s.asiento FROM (
    SELECT DISTINCT b.asiento
    FROM boletos b
    JOIN vuelos vh ON vh.id_vuelo = b.id_vuelo
    JOIN aviones ah ON ah.id_avion = vh.id_avion
    WHERE ah.id_modelo = (
        SELECT av.id_modelo
        FROM vuelos v JOIN aviones av ON av.id_avion = v.id_avion
        WHERE v.id_vuelo = @id_vuelo
    )
) s
ORDER BY CAST(s.asiento AS UNSIGNED), SUBSTR(s.asiento, -1);

-- 4. Ocupación realmente registrada por vuelo.
SELECT asiento FROM boletos WHERE id_vuelo = @id_vuelo
ORDER BY CAST(asiento AS UNSIGNED), SUBSTR(asiento, -1);
