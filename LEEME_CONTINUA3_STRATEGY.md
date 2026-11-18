# CONTINUA3 — Comparación de tarifas y selección de plazas con Strategy

## Alcance implementado

- Se conservó la búsqueda de vuelos futura, fecha, pasajeros, ida/vuelta y multidestino (máximo 2 tramos) de la versión CONTINUA3 anterior.
- Tras elegir **un vuelo por tramo** en «Buscar vuelos», pulsar **Comparar categorías y tarifas**.
- Nueva pantalla **Comparar tarifas**: muestra las 3 categorías (Económica, Premium Economy, Business); dentro de Económica permite escoger Básica, Light, Plus y Full. Se presenta descripción **solo de prestaciones presentes en la BD** (equipaje incluido y reembolsabilidad), salida/llegada programadas, plazas totales y precios simulados por persona y por todo el grupo en USD y PEN.
- Nueva pantalla **Plaza**: mapa interactivo basado en etiquetas reales de asientos que aparecen en los boletos de cada modelo de avión; diferencia libre, ocupado y seleccionado. Contador N / pasajeros; exige seleccionar un asiento por persona. En ida y vuelta se selecciona una tarifa y plazas para cada tramo, y el último botón **Resumen del viaje** abre «Detalle de vuelo».
- «Detalle de vuelo» muestra un resumen provisional con todos los tramos, tarifas, asientos y totales USD/PEN; conserva la pantalla histórica cuando no existe un itinerario terminado.
- No se implementan pagos, registro de pasajeros, emisión de boletos, inventario por cabina ni servicios extra. **No hay escritura en MySQL ni bloqueo real de plazas**.

## Precio (solo patrón Strategy, sin EMSR-b)

`precio_strategy.py` contiene `EstrategiaPrecio` (ABC), `PrecioHistoricoFijo`, `PrecioDinamicoStrategy` y el contexto `Cotizador`. La interfaz utiliza **solo `PrecioDinamicoStrategy`**:

`USD = mediana histórica por ruta y tarifa (USD dic. 2025) × IPC_US_cotización / IPC_US_dic2025 × factor Strategy por anticipación y ocupación`

`PEN = USD_redondeado × tipo de cambio de simulación`, redondeado a dos decimales por persona. Los factores se ajustaron previamente con datos 2024–2025, y el backtest 2026 anterior obtuvo WAPE 10,20 % frente al 37,85 % de una política fija. **Estas métricas proceden del estudio anterior; en esta entrega no se vuelve a entrenar ni a validar la precisión estadística del modelo.** No equivalen a demostrar ingresos adicionales.

La ocupación es número de boletos emitidos / capacidad total. No se usa la ocupación futura del avión. El precio que se muestra se congela en la selección de la tarifa hasta el resumen de ese itinerario de demostración.

- IPC: archivo `ipc_usa_bls_nsa.csv` entregado con el backtest; el último dato disponible de la serie para noviembre de 2026 es octubre de 2026, 337,511. El código toma el último valor **igual o anterior a la fecha de cotización**. No proyecta el IPC de la fecha del vuelo. Si el archivo se queda antiguo, actualizarlo mediante fuente oficial.
- Cambio PEN/USD: aparece como **campo editable y expresamente simulado**, cuyo valor inicial (3,75) procede de la generación de la BD sintética. Nunca debe considerarse cambio de mercado vigente.
- Precios y moneda no representan una oferta comercial ni incluyen un cálculo fiscal real. Las tarifas son estimaciones académicas.

## Limitación explícita del mapa de plazas

La base registra `boletos.asiento`, el modelo del avión y su `capacidad`. **No guarda inventario físico por cabina**. El mapa reproduce el conjunto de etiquetas observadas de un modelo, con ocupados actuales por vuelo, pero no permite afirmar que un asiento concreto es Económico, Premium Economy o Business. Se permite seleccionar plazas globales y la pantalla muestra esa limitación claramente. No se han añadido asientos ficticios a los CSV, ni se ha diseñado un reparto de cabinas arbitrario. La disponibilidad puede variar hasta completar una reserva futura.

## Instalación Windows

1. Haz una copia de seguridad de tu proyecto anterior. Copia `app.py`, `db_sqlalchemy.py`, `reportes.py`, `precio_strategy.py`, `servicio_precios.py`, `parametros_strategy_por_tarifa.json` e `ipc_usa_bls_nsa.csv` a una misma carpeta. El ZIP contiene estos archivos y `05_vuelos.csv` de 3.511 filas para comprobación; **no lo reimportes íntegramente a MySQL si ya tienes los 3.511 registros cargados**.
2. En tu MySQL/MariaDB, comprueba `SELECT COUNT(*) FROM vuelos;` → debe devolver **3511**. También deben existir las otras 13 tablas. El script `data_base.sql` es el original de creación/carga: **NO lo ejecutes de nuevo sobre la base poblada**.
3. Asegúrate de que existe la carpeta `.streamlit` y crea `.streamlit/secrets.toml` copiando `secrets.toml.example`. Completa las credenciales reales, no las compartas y no subas este archivo a un repositorio.
4. En la terminal, desde la carpeta de la aplicación:
   ```bash
   python -m pip install -r requirements.txt
   python -m streamlit run app.py
   ```
5. En «Buscar vuelos», elige origen, destino, fecha y pasajeros; pulsa Buscar, marca una fila y elige el vuelo. En ida y vuelta debes seleccionar un vuelo de **cada tramo**. Después pulsa «Comparar categorías y tarifas», elige la categoría y la tarifa; en «Plaza» selecciona el mismo número de asientos que pasajeros. Continúa hasta «Resumen del viaje».

## Verificación

`python -m pytest -q tests/test_etapa_3_4.py`

Pruebas locales: integridad básica de CSV con 3.511 vuelos, cobertura de las 56 rutas y seis tarifas, clase Strategy, inflación / doble moneda, validaciones de precios y consulta de etiquetas de asientos en una SQLite **temporal en memoria**. No se ha conectado desde este entorno a tu servidor MariaDB/MySQL ni se ha ejecutado la aplicación visual en Streamlit. Verifica estas dos pruebas en tu ordenador; esta entrega no certifica funcionamiento de producción.

## Cambios y archivos no modificados

`db_sqlalchemy.py` incorpora `TarifaCatalogoRepository`, `MapaAsientosRepository` y `id_ruta` en la ficha del vuelo. `app.py` incorpora pantallas y navegación. `servicio_precios.py` adapta IPC y cambio al modelo Strategy calibrado. `consultas_etapa_3_4.sql` contiene solo consultas para inspección manual. `05_vuelos.csv` se incluye **sin modificación** respecto al último archivo aprobado. No hay modificaciones en las otras 13 tablas ni en los boletos y pagos.
