"""Tests de la búsqueda inversa y la vitrina pública (WCH-468)."""

import csv
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import base
import embeddings
import generar_fixtures
import importar
import indexar
import publicar


@pytest.fixture(scope="module")
def carpeta_fixtures(tmp_path_factory):
    """Fixtures sintéticos completos en tmp (sin espectrogramas: los tests
    no los necesitan y matplotlib los hace lentos)."""
    destino = tmp_path_factory.mktemp("datos") / "fixtures"
    generar_fixtures.generar(destino, con_espectrogramas=False)
    return destino


@pytest.fixture(scope="module")
def db_indexada(carpeta_fixtures, tmp_path_factory):
    """DB con los fixtures importados y el índice de embeddings poblado."""
    ruta_db = tmp_path_factory.mktemp("db") / "ecos.db"
    importar.importar(carpeta_fixtures, ruta_db)
    conteos = indexar.indexar(ruta_db)
    assert conteos["indexados"] == 58 and conteos["con_error"] == 0
    return ruta_db


def test_embedder_determinista(carpeta_fixtures):
    """El mismo clip produce siempre exactamente el mismo vector."""
    clip = sorted((carpeta_fixtures / "clips").glob("*_up_call.wav"))[0]
    embedder = embeddings.EmbedderEspectral()

    v1, v2 = embedder.embed(clip), embedder.embed(clip)

    assert v1.dtype == np.float32
    assert len(v1) == embedder.dimension
    assert np.array_equal(v1, v2)
    assert np.linalg.norm(v1) == pytest.approx(1.0, abs=1e-5)


def test_top1_de_un_up_call_es_otro_up_call(db_indexada):
    """Los fixtures del mismo tipo son similares por construcción: el vecino
    más cercano de un up_call tiene que ser otro up_call."""
    con = base.conectar(db_indexada)
    try:
        consulta = con.execute(
            "SELECT filename FROM segmento WHERE tipo = 'up_call' LIMIT 1"
        ).fetchone()[0]
        resultados = embeddings.similares(con, consulta, n=10)
    finally:
        con.close()

    assert resultados, "similares() no devolvió resultados con el índice poblado"
    top1, score = resultados[0]
    assert top1 != consulta  # el propio clip queda excluido
    assert "up_call" in top1
    assert score > 0.9


def test_indexar_es_idempotente(db_indexada):
    segundo = indexar.indexar(db_indexada)
    assert segundo["indexados"] == 0
    assert segundo["al_dia"] == 58


def test_publicar_solo_confirmados(db_indexada, tmp_path):
    docs = tmp_path / "docs"
    r = publicar.publicar(db_indexada, destino=docs, carpeta_respaldo=tmp_path / "respaldo")

    assert (docs / "index.html").exists()
    assert (docs / "bitacora.html").exists()
    assert (docs / "media" / "clips").is_dir()

    con = base.conectar(db_indexada)
    try:
        confirmados = {
            f[0]
            for f in con.execute("SELECT filename FROM segmento WHERE estado = 'confirmado'")
        }
        no_confirmados = {
            f[0]
            for f in con.execute("SELECT filename FROM segmento WHERE estado != 'confirmado'")
        }
    finally:
        con.close()

    assert r["publicados"] == len(confirmados) > 0
    indice = (docs / "index.html").read_text()
    bitacora = (docs / "bitacora.html").read_text()
    clips_publicados = {p.name for p in (docs / "media" / "clips").glob("*.wav")}

    # Ningún segmento no-confirmado se filtra a la vitrina: ni en las páginas
    # ni en la media copiada.
    for filename in no_confirmados:
        assert filename not in indice
        assert filename not in bitacora
        assert filename not in clips_publicados
    assert clips_publicados <= confirmados

    # La cara pública mantiene sus garantías: banner de procedencia en TODAS
    # las páginas y badge HIPÓTESIS (EA2).
    # (Actualizado en WCH-470: el commit 4332e63 cambió el banner a
    # "Grabaciones reales del Golfo Nuevo" al publicar los datos reales y el
    # test quedó atrás — el contrato vigente es el banner fijo .banner-demo.)
    for pagina in (indice, bitacora):
        assert "Grabaciones reales del Golfo Nuevo" in pagina
        assert "HIPÓTESIS" in pagina


def test_bitacora_tipos_distintos(db_indexada, tmp_path):
    con = base.conectar(db_indexada)
    try:
        confirmados = con.execute(
            "SELECT * FROM segmento WHERE estado = 'confirmado'"
        ).fetchall()
    finally:
        con.close()

    curados = publicar._curar_bitacora(confirmados)

    tipos = [s["tipo_corregido"] or s["tipo"] for s in curados]
    assert len(tipos) == len(set(tipos))  # tipos distintos
    assert 1 <= len(curados) <= 5


def test_respaldo_exporta_todas_las_filas(db_indexada, tmp_path):
    respaldo = tmp_path / "respaldo"
    r = publicar.publicar(db_indexada, destino=tmp_path / "docs", carpeta_respaldo=respaldo)

    with open(respaldo / "catalogo-export.csv", newline="") as f:
        filas = list(csv.DictReader(f))

    con = base.conectar(db_indexada)
    try:
        total = con.execute("SELECT COUNT(*) FROM segmento").fetchone()[0]
        estados = dict(
            con.execute("SELECT estado, COUNT(*) FROM segmento GROUP BY estado").fetchall()
        )
    finally:
        con.close()

    # El export es el dump COMPLETO (con veredictos), no solo lo publicado.
    assert r["filas_respaldadas"] == total == len(filas) == 58
    assert "estado" in filas[0] and "revisor" in filas[0]
    por_estado = {}
    for fila in filas:
        por_estado[fila["estado"]] = por_estado.get(fila["estado"], 0) + 1
    assert por_estado == estados

    # Y quedó la copia timestampeada de la DB al lado.
    assert list(respaldo.glob("ecos-*.db"))
