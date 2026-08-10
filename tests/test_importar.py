"""Tests del importador y del registro de veredictos (WCH-467)."""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import base
import generar_fixtures
import importar


@pytest.fixture(scope="module")
def carpeta_fixtures(tmp_path_factory):
    """Fixtures sintéticos completos en tmp (sin espectrogramas: los tests
    no los necesitan y matplotlib los hace lentos)."""
    destino = tmp_path_factory.mktemp("datos") / "fixtures"
    generar_fixtures.generar(destino, con_espectrogramas=False)
    return destino


@pytest.fixture
def ruta_db(tmp_path):
    return tmp_path / "ecos.db"


def contar(ruta_db, consulta="SELECT COUNT(*) FROM segmento", params=()):
    con = base.conectar(ruta_db)
    try:
        return con.execute(consulta, params).fetchone()[0]
    finally:
        con.close()


def test_importador_feliz(carpeta_fixtures, ruta_db):
    reporte = importar.importar(carpeta_fixtures, ruta_db)

    assert not reporte.errores
    # 40 del catálogo + 18 candidatos
    assert reporte.total_cargadas == 58
    assert contar(ruta_db) == 58
    # El catálogo llega resuelto: los únicos propuestos son los 18 candidatos
    assert contar(ruta_db, "SELECT COUNT(*) FROM segmento WHERE estado = 'propuesto'") == 18
    assert contar(ruta_db, "SELECT COUNT(*) FROM segmento WHERE estado = 'confirmado'") == 31
    assert (
        contar(ruta_db, "SELECT COUNT(*) FROM segmento WHERE fuente = 'muelle-madryn-2025-10'")
        == 23
    )
    # No hubo espectrogramas en este fixture → los reporta como faltantes, sin fallar
    assert len(reporte.espectrogramas_faltantes) == 58


def test_columnas_cambiadas_reporta_sin_explotar(tmp_path, ruta_db):
    """Un CSV con columnas renombradas/extras se importa en lo posible y las
    diferencias quedan en el reporte — nunca stack trace."""
    carpeta = tmp_path / "raros"
    (carpeta / "clips").mkdir(parents=True)
    with open(carpeta / "catalogo.csv", "w", newline="") as f:
        w = csv.writer(f)
        # "tipo" y "fuente" son sinónimos mapeables; "color_favorito" es extra;
        # faltan recording_start, offset, absolute_datetime y status.
        w.writerow(["filename", "tipo", "fuente", "color_favorito"])
        w.writerow(["a.wav", "up_call", "embarcacion-2026-08", "azul"])
        w.writerow(["", "up_call", "embarcacion-2026-08", "rojo"])  # sin filename
        w.writerow(["b.wav", "", "embarcacion-2026-08", "verde"])  # sin type

    reporte = importar.importar(carpeta, ruta_db)

    rep = next(a for a in reporte.archivos if a.nombre == "catalogo.csv")
    assert rep.columnas_mapeadas == {"tipo": "type", "fuente": "recording_source"}
    assert rep.columnas_extra == ["color_favorito"]
    assert set(rep.columnas_faltantes) == {
        "recording_start",
        "offset_in_recording_s",
        "absolute_datetime",
        "status",
    }
    assert len(rep.filas_invalidas) == 2
    assert rep.insertadas == 1
    # El clip a.wav no existe en clips/ → reportado
    assert reporte.clips_faltantes == ["a.wav"]
    # candidatos.csv no estaba → error informativo, no excepción
    assert any("candidatos.csv" in err for err in reporte.errores)
    assert contar(ruta_db) == 1


def test_csv_totalmente_ajeno_no_explota(tmp_path, ruta_db):
    carpeta = tmp_path / "ajeno"
    carpeta.mkdir()
    with open(carpeta / "catalogo.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["una", "cosa", "cualquiera"])
        w.writerow(["1", "2", "3"])

    reporte = importar.importar(carpeta, ruta_db)

    assert any("filename/type" in err for err in reporte.errores)
    assert reporte.total_cargadas == 0
    assert contar(ruta_db) == 0


def test_reimport_idempotente(carpeta_fixtures, ruta_db):
    primero = importar.importar(carpeta_fixtures, ruta_db)
    segundo = importar.importar(carpeta_fixtures, ruta_db)

    assert contar(ruta_db) == 58  # re-correr no duplica
    assert sum(a.insertadas for a in primero.archivos) == 58
    assert sum(a.insertadas for a in segundo.archivos) == 0
    assert sum(a.actualizadas for a in segundo.archivos) == 58


def test_reimport_no_pisa_veredicto(carpeta_fixtures, ruta_db):
    importar.importar(carpeta_fixtures, ruta_db)
    con = base.conectar(ruta_db)
    filename = con.execute(
        "SELECT filename FROM segmento WHERE estado = 'propuesto' LIMIT 1"
    ).fetchone()[0]
    base.registrar_veredicto(con, filename, "descartar")
    con.close()

    importar.importar(carpeta_fixtures, ruta_db)

    con = base.conectar(ruta_db)
    fila = con.execute("SELECT estado FROM segmento WHERE filename = ?", (filename,)).fetchone()
    con.close()
    assert fila["estado"] == "descartado"  # el CSV no pisa lo revisado a mano


def test_veredicto_escribe_estado(carpeta_fixtures, ruta_db):
    importar.importar(carpeta_fixtures, ruta_db)
    con = base.conectar(ruta_db)
    filas = con.execute(
        "SELECT filename FROM segmento WHERE estado = 'propuesto' LIMIT 3"
    ).fetchall()
    a, b, c = (f["filename"] for f in filas)

    assert base.registrar_veredicto(con, a, "confirmar")
    assert base.registrar_veredicto(con, b, "corregir", tipo_corregido="up_call")
    assert base.registrar_veredicto(con, c, "descartar")

    for filename, estado_esperado, tipo_corregido in (
        (a, "confirmado", None),
        (b, "confirmado", "up_call"),
        (c, "descartado", None),
    ):
        fila = con.execute(
            "SELECT estado, tipo_corregido, revisado_en, revisor FROM segmento WHERE filename = ?",
            (filename,),
        ).fetchone()
        assert fila["estado"] == estado_esperado
        assert fila["tipo_corregido"] == tipo_corregido
        assert fila["revisado_en"] is not None
        assert fila["revisor"] == "local"

    # Acción inválida y corrección sin tipo → error claro, no estado corrupto
    with pytest.raises(ValueError):
        base.registrar_veredicto(con, a, "romper")
    with pytest.raises(ValueError):
        base.registrar_veredicto(con, a, "corregir")
    # Segmento inexistente → False, sin excepción
    assert not base.registrar_veredicto(con, "no-existe.wav", "confirmar")
    con.close()
