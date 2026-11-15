"""Pruebas contra MySQL. Se saltan solas si no hay SQLAlchemy/PyMySQL
o si la base 'aerolinea' no esta disponible (ver .env)."""
import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
pytest.importorskip("pymysql")

from aerolinea.conexion import ConexionMySQL  # noqa: E402
from aerolinea.repositorios import ReservaRepository, VueloRepository  # noqa: E402


@pytest.fixture(scope="module")
def cn():
    try:
        c = ConexionMySQL()
        c.consultar("SELECT 1")
        return c
    except Exception as e:  # sin servidor o sin credenciales
        pytest.skip(f"MySQL no disponible: {e}")


def test_singleton_devuelve_la_misma_instancia(cn):
    assert ConexionMySQL() is cn
    assert VueloRepository().cn is cn


def test_cantidades_cargadas(cn):
    n = cn.consultar("SELECT (SELECT COUNT(*) FROM boletos) b, (SELECT COUNT(*) FROM reservas) r")
    assert n.loc[0, "b"] >= 487357 and n.loc[0, "r"] >= 266334


def test_buscar_vuelos_lim_cuz(cn):
    df = VueloRepository().buscar("LIM", "CUZ", "2026-10-08")
    assert set(df["numero_vuelo"]) == {"LP2045", "LP2049"}


def test_obtener_vuelo_y_asientos(cn):
    repo = VueloRepository()
    v = repo.obtener(3079)
    libres = repo.asientos_libres(3079)
    assert v.capacidad - v.asientos_ocupados == len(libres)


def test_itinerario_pnr(cn):
    assert not ReservaRepository().itinerario("AVX8DH").empty


def test_trigger_no_vende_en_vuelo_cancelado(cn):
    from sqlalchemy import text
    with cn.engine.connect() as cx:
        tx = cx.begin()
        try:
            with pytest.raises(sqlalchemy.exc.DBAPIError, match="cancelado"):
                cx.execute(text("""INSERT INTO boletos VALUES
                    (999999999, 1, (SELECT MIN(id_vuelo) FROM vuelos WHERE estado='cancelado'),
                     1, '1A', 100, 1)"""))
        finally:
            tx.rollback()


def test_trigger_rechaza_transicion_invalida(cn):
    from sqlalchemy import text
    with cn.engine.connect() as cx:
        tx = cx.begin()
        try:
            with pytest.raises(sqlalchemy.exc.DBAPIError, match="Transicion no permitida"):
                cx.execute(text("UPDATE vuelos SET estado='aterrizado' WHERE id_vuelo = 3079"))
        finally:
            tx.rollback()
