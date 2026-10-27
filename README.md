# Dataset — P6_aerolinea

Archivos CSV (UTF-8, separador coma, encabezado en la primera fila, NULL = celda vacía, booleanos 0/1).
El prefijo numérico indica el **orden de carga** que respeta las llaves foráneas.

| # | Archivo | Filas | Columnas |
|---|---|---|---|
| 01 | `01_aeropuertos.csv` | 25 | id_aeropuerto, codigo_iata, ciudad, pais |
| 02 | `02_rutas.csv` | 56 | id_ruta, id_origen, id_destino, distancia_km, duracion_min |
| 03 | `03_modelos_avion.csv` | 5 | id_modelo, fabricante, nombre, capacidad |
| 04 | `04_aviones.csv` | 31 | id_avion, id_modelo, matricula, anio_fabricacion |
| 05 | `05_vuelos.csv` | 3,100 | id_vuelo, id_ruta, id_avion, salida_prog, salida_real, estado, numero_vuelo |
| 06 | `06_tripulantes.csv` | 440 | id_tripulante, nombre, cargo, horas_vuelo |
| 07 | `07_tripulacion_vuelo.csv` | 19,017 | id_vuelo, id_tripulante, rol |
| 08 | `08_pasajeros.csv` | 140,000 | id_pasajero, documento, nombre, nacionalidad |
| 09 | `09_cuentas_millas.csv` | 87,126 | id_cuenta, id_pasajero, nivel, millas |
| 10 | `10_reservas.csv` | 266,334 | id_reserva, id_pasajero, codigo_pnr, fecha_compra, canal |
| 11 | `11_tarifas.csv` | 6 | id_tarifa, clase, nombre, equipaje_incluido, reembolsable |
| 12 | `12_boletos.csv` | 487,357 | id_boleto, id_reserva, id_vuelo, id_tarifa, asiento, precio, id_pasajero |
| 13 | `13_equipajes.csv` | 487,687 | id_equipaje, id_boleto, peso_kg, tipo |
| 14 | `14_pagos.csv` | 276,782 | id_pago, id_reserva, monto, moneda, metodo |

**Total de registros:** 1,767,966

## Columnas añadidas al modelo de referencia
- `boletos.id_pasajero` (FK → pasajeros): una reserva agrupa 1–4 pasajeros; cada boleto identifica a quién vuela. `reservas.id_pasajero` es el titular que compra.
- `rutas.duracion_min`, `vuelos.numero_vuelo`, `tarifas.nombre` (familia tarifaria).

## Notas y patrones sembrados
- Precios en USD en `boletos.precio`; `pagos.monto` en la `moneda` indicada (PEN a 3,75). El pago puede superar la suma de boletos porque incluye cargos por equipaje extra. Un 4% de reservas paga en 2 partes (millas + dinero).
- Precio dinámico: sube fuerte cuando se compra con pocos días de anticipación (`fecha_compra` vs `salida_prog`) y conforme se llena el vuelo; temporada alta en julio y diciembre.
  Ej. Lima–Cusco: comprar 3 días antes cuesta en promedio ~2,5× lo de comprar con 30 días.
- Retraso (`salida_real − salida_prog`) depende de la ruta (Jauja, Iquitos, Cajamarca, Pto. Maldonado más), de la hora (vuelos de madrugada/mañana más puntuales), viernes y domingos, y temporada de lluvias (dic–mar).
- `estado`: aterrizado, cancelado (salida_real NULL) y programado (vuelos posteriores al 2026-09-30, con ventas parciales).
- ~18% de reservas tienen tramo de vuelta (dos vuelos en la misma reserva).
- Tripulación por vuelo: 1 Capitán, 1 Primer Oficial, 3–5 TCP (6–8 en el 787). `tripulantes.horas_vuelo` = experiencia previa + horas de vuelos aterrizados.
- `cuentas_millas` solo para pasajeros afiliados; nivel según millas (Clásica < 12 000 ≤ Plata < 30 000 ≤ Oro < 60 000 ≤ Platino).


## Carga en MySQL (ejemplo)
```sql
SET GLOBAL local_infile = 1;
LOAD DATA LOCAL INFILE '01_tabla.csv' INTO TABLE tabla
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;
```
Con pandas + SQLAlchemy: `pd.read_csv(f).to_sql(tabla, engine, if_exists='append', index=False, chunksize=5000)`
