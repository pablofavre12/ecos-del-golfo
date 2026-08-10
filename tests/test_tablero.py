"""Tests del tablero v2 (WCH-470): vistas server-rendered, solo lectura."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import base
import generar_fixtures
import importar
import tablero


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    """DB con los fixtures sintéticos importados (sin espectrogramas: lento)."""
    carpeta = tmp_path_factory.mktemp("datos") / "fixtures"
    generar_fixtures.generar(carpeta, con_espectrogramas=False)
    ruta_db = tmp_path_factory.mktemp("db") / "ecos.db"
    importar.importar(carpeta, ruta_db)
    con = base.conectar(ruta_db)
    yield con
    con.close()


def test_panel_cuenta_el_pipeline_con_numeros_reales(con):
    html = tablero.vista_panel(con)

    # El funnel narra las 6 etapas con los números de la DB (58 fixtures).
    for etapa in (
        "Sonidos detectados",
        "Propuestos a revisión",
        "Revisión del experto",
        "Confirmados",
        "Publicados en la vitrina",
    ):
        assert etapa in html
    assert ">58<" in html  # detectados
    assert "Salud por campaña" in html  # R19
    assert "Actividad reciente" in html  # trazabilidad
    assert "HIPÓTESIS" in html  # EA2


def test_cola_trae_progreso_referencias_y_atajos(con):
    html = tablero.vista_cola(con, pos=0)

    assert "Revisando" in html and "pendientes" in html
    assert "Por qué está en la cola" in html
    # Los 4 veredictos con su form y su explicación en criollo.
    for accion in ("confirmar", "corregir", "descartar", "desconocido"):
        assert f'data-veredicto="{accion}"' in html
    assert "Es lo que dice la máquina" in html
    # Atajos de teclado con leyenda visible.
    for tecla in ("<kbd>C</kbd>", "<kbd>X</kbd>", "<kbd>D</kbd>", "<kbd>espacio</kbd>"):
        assert tecla in html
    # Comparación de oído: ejemplares confirmados del tipo, o su estado vacío.
    assert "Así suenan los" in html or "Sin ejemplares confirmados" in html


def test_cola_clampa_posiciones_fuera_de_rango(con):
    assert "Revisando" in tablero.vista_cola(con, pos=9999)
    assert "Revisando" in tablero.vista_cola(con, pos=-5)


def test_explorador_cuenta_filtros_activos(con):
    html = tablero.vista_explorador(con, {"tipo": "up_call", "estado": "confirmado"})
    assert "2 filtros activos" in html
    assert "Quitar filtros" in html
