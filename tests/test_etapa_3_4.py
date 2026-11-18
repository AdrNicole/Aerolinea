"""Pruebas locales sin Streamlit ni acceso a MySQL (no modifican los CSV)."""
from datetime import datetime
from pathlib import Path
import json
import sys

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from precio_strategy import Cotizador, DatosCotizacion, PrecioDinamicoStrategy, PrecioHistoricoFijo
from servicio_precios import ServicioPrecios, ultimo_ipc_disponible, total_en_moneda
from db_sqlalchemy import MapaAsientosRepository


@pytest.fixture(scope='module')
def muestras():
    vuelos = pd.read_csv(ROOT/'05_vuelos.csv')
    rutas = pd.read_csv(ROOT.parent/'02_rutas.csv') if (ROOT.parent/'02_rutas.csv').exists() else None
    assert len(vuelos)==3511
    assert vuelos.id_vuelo.is_unique
    assert set(range(3101,3512)) == set(vuelos.id_vuelo) - set(range(1,3101))
    nuevos = vuelos[vuelos.id_vuelo>=3101]
    assert len(nuevos)==411
    assert (nuevos.estado=='programado').all()
    assert nuevos.salida_real.isna().all()
    f=pd.to_datetime(nuevos.salida_prog,dayfirst=True)
    assert f.min().date().isoformat()=='2026-11-15'
    assert f.max().date().isoformat()=='2027-03-31'
    if rutas is not None:
        assert set(nuevos.id_ruta).issubset(set(rutas.id_ruta))
    return nuevos


def test_cobertura_de_todas_las_tarifas_y_rutas(muestras):
    params=json.loads((ROOT/'parametros_strategy_por_tarifa.json').read_text())
    claves={(t['id_ruta'],t['id_tarifa']) for t in params['base_usd_constantes_diciembre_2025']}
    assert len(claves)==336
    for ruta in muestras.id_ruta.unique():
        assert {(ruta,t) for t in range(1,7)} <= claves


def test_monedas_e_inflacion():
    assert ultimo_ipc_disponible(datetime(2026,11,15))==('2026-10',337.511)
    assert ultimo_ipc_disponible(datetime(2026,7,15))[0]=='2026-07'
    assert total_en_moneda('226.42',2,3.75)==('452.84','1698.16')
    with pytest.raises(ValueError):
        ultimo_ipc_disponible(datetime(2021,1,1))


def test_strategy_comparativa_y_cobertura(muestras):
    ahora=datetime(2026,11,15,12)
    cot_fijo=Cotizador(ROOT/'parametros_strategy_por_tarifa.json', PrecioHistoricoFijo())
    cot_dyn=Cotizador(ROOT/'parametros_strategy_por_tarifa.json', PrecioDinamicoStrategy())
    viajes=muestras.copy()
    viajes['salida_prog']=pd.to_datetime(viajes.salida_prog,dayfirst=True)
    for v in viajes[viajes.salida_prog>ahora].itertuples():
        for tarifa in range(1,7):
            args=DatosCotizacion(id_ruta=v.id_ruta,id_tarifa=tarifa,
                fecha_salida=v.salida_prog.to_pydatetime(),fecha_cotizacion=ahora,
                capacidad=174,asientos_ocupados=0,
                ipc_us_cotizacion=337.511,tipo_cambio_pen_usd=3.75)
            fijo=cot_fijo.cotizar(args)
            dinamico=cot_dyn.cotizar(args)
            assert float(fijo['precio_usd'])>0
            assert float(dinamico['precio_usd'])>0
            assert dinamico['importe_estimado']
    base=DatosCotizacion(id_ruta=1,id_tarifa=1,
        fecha_salida=datetime(2027,1,15,12),fecha_cotizacion=ahora,
        capacidad=174,asientos_ocupados=0,
        ipc_us_cotizacion=337.511,tipo_cambio_pen_usd=3.75)
    return_base=cot_dyn.cotizar(base)
    return_alta=cot_dyn.cotizar(DatosCotizacion(**{**base.__dict__,'asientos_ocupados':155}))
    assert float(return_alta['precio_usd'])>float(return_base['precio_usd'])


def test_seis_tarifas_y_totales_por_dos_pasajeros(muestras):
    v=muestras.iloc[-1]
    salida=pd.to_datetime(v.salida_prog,dayfirst=True)
    info={'id_ruta':int(v.id_ruta),'capacidad':174,'salida_prog':salida}
    tarifas=pd.read_csv(ROOT.parent/'11_tarifas.csv') if (ROOT.parent/'11_tarifas.csv').exists() else pd.DataFrame([
        {'id_tarifa':x,'clase': 'Económica' if x<5 else ('Premium Economy' if x==5 else 'Business'),
         'nombre':str(x),'equipaje_incluido':x>2,'reembolsable':x>3} for x in range(1,7)
    ])
    res=ServicioPrecios().cotizar_tarifas(info,tarifas.to_dict('records'),0,datetime(2026,11,15,12),3.75)
    assert len(res)==6
    for row in res:
        usd,pen=total_en_moneda(row['precio_usd'],2,3.75)
        assert float(usd)>0 and float(pen)>0
        assert abs(float(pen)-2*float(row['precio_pen']))<0.005


def test_etiquetas_historicas_asientos_sqlite():
    """Comprueba SELECT DISTINCT y ORDER BY sin necesitar MariaDB."""
    eng=create_engine('sqlite+pysqlite:///:memory:')
    with eng.begin() as c:
        c.exec_driver_sql('CREATE TABLE aviones (id_avion INT, id_modelo INT)')
        c.exec_driver_sql('CREATE TABLE vuelos (id_vuelo INT, id_avion INT)')
        c.exec_driver_sql('CREATE TABLE boletos (id_vuelo INT, asiento TEXT)')
        c.exec_driver_sql('INSERT INTO aviones VALUES (1,1),(2,1),(3,2)')
        c.exec_driver_sql('INSERT INTO vuelos VALUES (10,1),(11,2),(12,3)')
        c.exec_driver_sql("INSERT INTO boletos VALUES (10,'2A'),(10,'1B'),(11,'1A'),(12,'1A')")
    repo=MapaAsientosRepository.__new__(MapaAsientosRepository)
    repo.engine=eng
    assert repo.etiquetas_modelo(10).asiento.tolist()==['1A','1B','2A']
    assert repo.ocupados(10).asiento.tolist()==['1B','2A']


def test_inputs_invalidos():
    with pytest.raises(ValueError):
        total_en_moneda('100',0,3.75)
    with pytest.raises(ValueError):
        ServicioPrecios().cotizar_tarifas({}, [],0,datetime(2026,11,15),0)
