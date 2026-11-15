"""Patron Observer: avisos de retraso y cancelacion."""
import csv
from datetime import datetime, timedelta

from aerolinea.patrones.estado_vuelo import VueloOperacion
from aerolinea.patrones.observador import NotificadorPasajeros, PanelOperaciones, RegistroCSV

SALIDA = datetime(2027, 1, 10, 8, 0)


def armar(pasajeros_df):
    v = VueloOperacion(7, "LP2049", SALIDA)
    panel = PanelOperaciones(imprimir=False)
    notif = NotificadorPasajeros(lambda id_vuelo: pasajeros_df)
    v.suscribir(panel)
    v.suscribir(notif)
    return v, panel, notif


def test_retraso_significativo_avisa_a_cada_pasajero(pasajeros_df):
    v, panel, notif = armar(pasajeros_df)
    v.iniciar_embarque()
    v.despegar(SALIDA + timedelta(minutes=40))
    assert len(notif.mensajes) == 2
    assert "40 min de retraso" in notif.mensajes[0]
    assert [e.tipo for e in panel.eventos] == ["CAMBIO_ESTADO", "CAMBIO_ESTADO", "RETRASO"]


def test_retraso_menor_al_umbral_no_avisa_a_pasajeros(pasajeros_df):
    v, panel, notif = armar(pasajeros_df)
    v.anunciar_retraso(10)
    assert notif.mensajes == []
    assert panel.eventos[-1].tipo == "RETRASO"   # el panel si lo ve


def test_cancelacion_avisa_con_motivo(pasajeros_df):
    v, _, notif = armar(pasajeros_df)
    v.cancelar("Cierre del aeropuerto")
    assert len(notif.mensajes) == 2
    assert "CANCELADO" in notif.mensajes[0] and "Cierre del aeropuerto" in notif.mensajes[0]


def test_desuscribir(pasajeros_df):
    v, panel, notif = armar(pasajeros_df)
    v.desuscribir(notif)
    v.cancelar("x")
    assert notif.mensajes == [] and len(panel.eventos) == 2


def test_registro_csv(tmp_path, pasajeros_df):
    v, _, _ = armar(pasajeros_df)
    ruta = tmp_path / "eventos.csv"
    v.suscribir(RegistroCSV(ruta))
    v.iniciar_embarque()
    v.cancelar("Falla tecnica")
    filas = list(csv.DictReader(ruta.open(encoding="utf-8")))
    assert [f["tipo"] for f in filas] == ["CAMBIO_ESTADO", "CAMBIO_ESTADO", "CANCELACION"]
