# Aerolínea: Reservas, Vuelos y Puntualidad (Proyecto 6)

Sistema en Python orientado a objetos sobre la base MySQL `aerolinea`
(14 tablas), con patrones de diseño y análisis con pandas.

## 1. Instalación

1. Carga la base de datos ejecutando `sql/data_base.sql` completo en MySQL
   Workbench (los CSV deben estar en `C:\P6_aerolinea\`).
2. Instala las librerías (una sola vez):
   ```
   pip install -r requirements.txt
   ```
3. Copia `.env.ejemplo` como `.env` y escribe tu usuario y clave de MySQL.

## 2. Uso

| Comando | Qué hace |
|---|---|
| `python main.py` | Menú de consola: buscar vuelos, detalle, cotizar, reservar, operar un vuelo, consultar PNR, buscar pasajero, análisis |
| `streamlit run dashboard.py` | **Dashboard de negocio** (tema oscuro): mapa de rutas 3D coloreable por ingresos/puntualidad/ocupación/pasajeros, calendario de días con más vuelos, KPIs con tendencia, hallazgos automáticos y pestañas de rutas, ventas, operaciones y clientes. Filtros de fecha, mercado, rutas y moneda (USD/PEN) |
| `python exportar_html.py` | Genera **salidas/dashboard.html**: el mismo dashboard en un solo archivo que se abre con doble clic (sin Python ni MySQL; solo el fondo del mapa usa internet) |
| `python generar_analisis.py` | Genera los 8 gráficos PNG y `analisis_aerolinea.xlsx` en `salidas/` |
| `python -m pytest -v` | Ejecuta las pruebas unitarias (y las de MySQL si hay conexión) |

En el menú, las opciones **4** (reservar) y **5** (operar vuelo) preguntan si
guardar en la base; si respondes `n` son una simulación y no cambian nada.
Las ventas usan como fecha de compra por defecto el corte del dataset
(30/09/2026), porque los vuelos programados son del 1 al 14 de octubre de 2026.

### Dashboard de negocio (`dashboard.py`)

Vista de la empresa sobre el histórico (ene 2024 – sep 2026):
- **Indicadores:** ingresos, pasajeros transportados, ocupación, puntualidad,
  cancelación y ticket promedio, con variación frente al mismo periodo del año
  anterior (solo cuando ese periodo está completo en los datos).
- **Pestañas:** Resumen (series mensuales, comparativo anual ene–sep, ventas
  anticipadas), Rutas, Ventas (clase, canal, tarifa, anticipación),
  Operaciones (retraso por día y hora, rutas con más retraso, cancelaciones) y
  Clientes (niveles de millas, nacionalidad).
- Las definiciones de cada indicador están en `aerolinea/indicadores.py`.
- **Moneda:** selector USD / PEN. Los precios del dataset están en USD; PEN
  convierte con el tipo de cambio del dataset (3,75).
- **Fuente de datos:** si hay `.env` lee MySQL; si no, lee los 14 CSV del
  dataset (`aerolinea/fuente_csv.py`, mismas cifras). Así funciona publicado.

### Publicar el dashboard (Streamlit Community Cloud)

1. Sube esta carpeta al repositorio de GitHub (sin `.env`; el `.gitignore` lo
   excluye). Los CSV del profesor deben estar en el repositorio, en `datos/` o
   en cualquier carpeta.
2. Entra a https://share.streamlit.io con tu cuenta de GitHub → **Create app**.
3. Repositorio, rama `main` y archivo principal: la ruta a `dashboard.py`.
4. En **Advanced settings** elige **Python 3.12**.
5. Elige el nombre del enlace y presiona **Deploy**.

La versión publicada muestra el histórico del dataset original. Lo que se
registre en MySQL desde `main.py` (reservas, cambios de estado) solo se ve en
la versión local, que lee la base.

## 3. Estructura

```
main.py                    menú de consola
dashboard.py               dashboard de negocio (Streamlit)
generar_analisis.py        análisis completo -> salidas/
aerolinea/
  config.py                conexión leída de .env
  conexion.py              ConexionMySQL ............ Singleton
  repositorios.py          Vuelo/Tarifa/Pasajero/Reserva/AnalisisRepository ... Repository
  modelos.py               Vuelo, Pasajero, Tarifa, Reserva, BoletoNuevo, Pago
  servicios.py             casos de uso (unen repositorios y patrones)
  patrones/
    estado_vuelo.py        VueloOperacion + estados .. State
    observador.py          avisos de retraso ......... Observer
    precio.py              estrategias de precio ..... Strategy
    reserva_builder.py     ReservaBuilder ............ Builder
  analisis.py              pandas: groupby, pivot_table, merge, series de tiempo
  indicadores.py           KPIs de negocio del dashboard (funciones puras)
  graficos.py              Matplotlib / Seaborn
tests/                     pytest (55 pruebas + 7 de integración con MySQL)
sql/data_base.sql          script de la base de datos
```

## 4. Patrones de diseño y justificación

| Patrón | Dónde | Por qué |
|---|---|---|
| **State** | `patrones/estado_vuelo.py` | El vuelo pasa por programado → embarcando → en vuelo → aterrizado (o cancelado). Cada estado es una clase que sabe qué acciones permite, en lugar de `if` sobre un texto. Una acción inválida (aterrizar un vuelo programado) la rechaza el propio estado. La misma regla está en MySQL (trigger `trg_vuelos_transicion_estado`). |
| **Observer** | `patrones/observador.py` | El vuelo publica eventos (cambio de estado, retraso, cancelación) sin saber quién los recibe. `NotificadorPasajeros` avisa a cada pasajero si el retraso es de 15 min o más, `PanelOperaciones` muestra todo y `RegistroCSV` deja constancia. Un canal nuevo es una clase nueva. |
| **Strategy** | `patrones/precio.py` | El precio se calcula con estrategias intercambiables: fijo, por anticipación, por ocupación o dinámico (las tres juntas). Los factores salen de calibrar un modelo con los 487 mil boletos históricos (R² = 0,925; error promedio 7% al probarlo con 20 000 boletos reales). |
| **Builder** | `patrones/reserva_builder.py` | Una reserva tiene titular, varios pasajeros, varios tramos, tarifa, asientos, precios y pago. El builder los agrega paso a paso y valida todo junto: vuelos programados y con cupo, tramos encadenados (conexión mínima 45 min), máximo 9 pasajeros. |
| **Singleton** | `conexion.py` | Un solo engine de SQLAlchemy (con su pool de conexiones) para toda la aplicación. |
| **Repository** | `repositorios.py` | Todo el SQL está encapsulado; el resto del sistema recibe DataFrames u objetos. Las reservas se guardan en una sola transacción. |

## 5. Análisis con pandas (resultados con los datos del profesor)

- **Retrasos:** viernes (16,7 min) y domingo (14,6) son los peores días; el
  retraso crece a lo largo del día y es mayor en la temporada de lluvias
  (dic-mar). Ruta con más retraso: LIM-TPP (24,1 min).
- **Pregunta del enunciado:** en Lima-Cusco, comprar con 0-3 días cuesta en
  promedio 371,83 USD frente a 119,49 USD con 28-32 días: **3,1 veces más**
  (Mann-Whitney, p < 1e-300). La relación se mantiene dentro de cada tarifa
  (2,9 a 3,0 veces), así que no se debe a la mezcla de tarifas.
- **Precio dinámico:** anticipación 0-3 días ×2,46; vuelo más del 95% lleno
  ×1,61; julio y diciembre ×1,17.
- **Millas:** los pasajeros Platino son el 2% y generan el 19% del gasto.
- **Negocio (histórico):** US$ 176,7 M de ingresos, 474 975 pasajeros, ocupación
  85,1%, puntualidad 71,0%, cancelación 1,5%. Las rutas internacionales son el
  18% de los vuelos y el 55% de los ingresos. Enero–septiembre 2026 creció 6,3%
  en ingresos frente al mismo periodo de 2025.
