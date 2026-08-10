"""Tests del loop de mejora continua (WCH-471): detector propio, calibración
versionada, clasificador re-entrenable e ingesta con dedupe."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import base
import clasificar
import detectar
import entrenar
import generar_fixtures
import importar
import indexar
import ingerir
import recalibrar

SR = 32000


# ---------- señales sintéticas ----------


def _tono(freq=370.0, dur=1.0, sr=SR):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    return np.sin(2 * np.pi * freq * t)


def _barrido(f0=80.0, f1=250.0, dur=1.0, sr=SR):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    return np.sin(2 * np.pi * (f0 * t + (f1 - f0) * t**2 / (2 * dur)))


def _gunshot(rng, dur=0.3, tau=0.02, sr=SR):
    """Impulso de banda ancha: caída exponencial + ataque extra al inicio."""
    n = int(sr * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    envolvente = np.exp(-t / tau) * (1 + 1.5 * np.exp(-t / 0.003))
    return rng.normal(0, 1, n) * envolvente


def _senal_con_eventos(rng):
    """30 s de fondo con 3 eventos conocidos: barrido (5 s), tono (15 s),
    impulso (25 s)."""
    y = rng.normal(0, 0.01, SR * 30).astype(np.float32)
    y[5 * SR : 6 * SR] += (_barrido() * 0.5).astype(np.float32)
    y[15 * SR : 16 * SR] += (_tono() * 0.5).astype(np.float32)
    imp = (_gunshot(rng) * 0.9).astype(np.float32)
    y[25 * SR : 25 * SR + len(imp)] += imp
    return y


@pytest.fixture()
def params():
    return dict(base.CALIBRACION_INICIAL)


# ---------- HPSS por filtrado de mediana ----------


def test_hpss_tono_alto_ruido_bajo():
    """Un tono puro da índice armónico alto; ruido blanco, bajo (§4.3)."""
    rng = np.random.default_rng(1)
    armonico_tono = detectar.indice_armonico(_tono(), SR)
    armonico_ruido = detectar.indice_armonico(rng.normal(0, 1, SR), SR)
    assert armonico_tono > 0.9
    assert armonico_ruido < 0.6
    assert armonico_tono > armonico_ruido + 0.3


def test_hpss_impulso_da_bajo():
    """Un impulso decayente (gunshot) es percusivo: índice bien bajo, incluso
    siendo un segmento corto (la resolución del STFT se adapta)."""
    rng = np.random.default_rng(2)
    assert detectar.indice_armonico(_gunshot(rng, dur=0.15), SR) < 0.35


# ---------- detector completo ----------


def test_detector_encuentra_los_tres_eventos(params):
    rng = np.random.default_rng(7)
    detecciones = detectar.detectar_en_senal(_senal_con_eventos(rng), SR, params)
    candidatas = [d for d in detecciones if d.clase != "ruido"]
    assert len(candidatas) == 3

    por_inicio = {round(d.inicio_s): d for d in candidatas}
    assert por_inicio[5].clase == "tonal_candidato"
    assert por_inicio[15].clase == "tonal_candidato"
    assert por_inicio[25].clase == "impulsivo_candidato"
    # features coherentes con la calibración
    assert por_inicio[15].indice_armonico >= params["armonico_min"]
    assert por_inicio[25].factor_cresta >= params["cresta_min"]
    assert por_inicio[25].concentracion_energia >= params["concentracion_min"]


def test_detector_banda_excluida_reclasifica_a_ruido(params):
    """La exclusión de bandas de sitio (§4.7) manda el pico a ruido."""
    rng = np.random.default_rng(7)
    y = _senal_con_eventos(rng)
    params["bandas_excluidas_hz"] = [[360, 380]]  # la banda del tono de 370 Hz
    candidatas = [d for d in detectar.detectar_en_senal(y, SR, params) if d.clase != "ruido"]
    assert all(round(d.inicio_s) != 15 for d in candidatas)


# ---------- DB con fixtures + índice (para clasificador e ingesta) ----------


@pytest.fixture(scope="module")
def carpeta_fixtures(tmp_path_factory):
    destino = tmp_path_factory.mktemp("datos") / "fixtures"
    generar_fixtures.generar(destino, con_espectrogramas=False)
    return destino


@pytest.fixture()
def db_indexada(carpeta_fixtures, tmp_path):
    ruta_db = tmp_path / "ecos.db"
    importar.importar(carpeta_fixtures, ruta_db)
    conteos = indexar.indexar(ruta_db)
    assert conteos["con_error"] == 0
    return ruta_db


# ---------- softmax numpy + versionado del modelo ----------


def test_entrenar_softmax_acierta_y_versiona(db_indexada):
    resumen = entrenar.entrenar(db_indexada, nota="test")
    assert resumen["version"] == 1
    assert clasificar.CLASE_DESCARTE in resumen["clases"]
    assert resumen["accuracy_cv"] is not None

    con = base.conectar(db_indexada)
    try:
        modelo = clasificar.cargar_modelo(con)
        # sanity: sobre los propios datos de entrenamiento acierta casi todo
        X, etiquetas, _, _ = entrenar.datos_de_entrenamiento(con)
        aciertos = sum(
            modelo.clases[int(np.argmax(modelo.predecir(x)))] == etiqueta
            for x, etiqueta in zip(X, etiquetas)
        )
        assert aciertos / len(etiquetas) >= 0.9

        # re-entrenar crea versión nueva sin pisar la anterior
        resumen2 = entrenar.entrenar(db_indexada, nota="test 2")
        assert resumen2["version"] == 2
        versiones = [f["version"] for f in con.execute("SELECT version FROM modelo ORDER BY version")]
        assert versiones == [1, 2]
        assert clasificar.cargar_modelo(con).version == 2
    finally:
        con.close()


def test_clasificar_devuelve_confianza_y_top2(db_indexada):
    entrenar.entrenar(db_indexada, nota="test")
    con = base.conectar(db_indexada)
    try:
        fila = con.execute(
            """
            SELECT e.vector, e.dimension, COALESCE(s.tipo_corregido, s.tipo) AS tipo
            FROM segmento s JOIN embedding e ON e.filename = s.filename
            WHERE s.estado = 'confirmado' AND s.tipo = 'up_call' LIMIT 1
            """
        ).fetchone()
        import embeddings

        vector = embeddings.blob_a_vector(fila["vector"], fila["dimension"])
        resultado = clasificar.clasificar(con, vector)
        assert resultado["motor"].startswith("clasificador-v")
        assert 0.0 <= resultado["confianza"] <= 1.0
        assert len(resultado["top2"]) == 2

        # fallback: sin modelo, votan los vecinos
        con.execute("DELETE FROM modelo")
        con.commit()
        vecinos = clasificar.clasificar(con, vector)
        assert vecinos["motor"] == "vecinos"
        assert vecinos["tipo"] == "up_call"  # su clon confirmado está en el índice
    finally:
        con.close()


# ---------- recalibración versionada ----------


def test_recalibrar_crea_version_nueva_con_historial(db_indexada):
    version, params, reporte = recalibrar.recalibrar(db_indexada, nota="test")
    assert version == 2  # la v1 es la semilla del informe
    con = base.conectar(db_indexada)
    try:
        filas = con.execute(
            "SELECT version, parametros FROM calibracion WHERE sitio='global' ORDER BY version"
        ).fetchall()
        assert [f["version"] for f in filas] == [1, 2]
        # la semilla sigue intacta
        import json

        assert json.loads(filas[0]["parametros"]) == base.CALIBRACION_INICIAL
    finally:
        con.close()
    # los fixtures tienen ≥5 tonales confirmados: armonico_min se recalculó
    assert any("armonico_min" in linea and "→" in linea or "sin cambio" in linea for linea in reporte)


def test_recalibrar_con_pocas_muestras_mantiene(db_indexada):
    """Fixtures: solo 3 gunshot confirmados (< 5) → los umbrales de gunshot
    se mantienen y el reporte lo dice."""
    _, params, reporte = recalibrar.recalibrar(db_indexada, nota="test")
    assert params["cresta_min"] == base.CALIBRACION_INICIAL["cresta_min"]
    assert params["concentracion_min"] == base.CALIBRACION_INICIAL["concentracion_min"]
    assert any("cresta_min" in linea and "se mantiene" in linea for linea in reporte)


def test_recalibrar_db_vacia_no_rompe(tmp_path):
    ruta_db = tmp_path / "vacia.db"
    base.conectar(ruta_db).close()
    version, params, reporte = recalibrar.recalibrar(ruta_db, nota="test")
    assert version == 2
    assert params["armonico_min"] == base.CALIBRACION_INICIAL["armonico_min"]


# ---------- ingesta con dedupe ----------


@pytest.fixture()
def wav_campania(tmp_path):
    """Una 'campaña' de 30 s con los 3 eventos conocidos, con nombre AudioMoth."""
    rng = np.random.default_rng(7)
    ruta = tmp_path / "20251104_090000.WAV"
    y = _senal_con_eventos(rng)
    # normalizar ANTES de escribir: el pico del impulso supera ±1.0 y el
    # int16 desbordaría (wrap-around que destruye el factor de cresta)
    generar_fixtures.escribir_wav(ruta, y / np.abs(y).max() * 0.9)
    return ruta


def test_ingesta_dedupe_e_idempotencia(db_indexada, wav_campania, tmp_path):
    entrenar.entrenar(db_indexada, nota="test")
    resumen = ingerir.ingerir(
        wav_campania, fuente="campania-test", ruta_db=db_indexada, raiz_datos=tmp_path / "datos"
    )
    assert resumen["ok"]
    assert resumen["ingresados"] == 3  # los 3 eventos entran a la cola

    con = base.conectar(db_indexada)
    try:
        filas = con.execute(
            "SELECT * FROM segmento WHERE fuente = 'campania-test' ORDER BY offset_s"
        ).fetchall()
        assert len(filas) == 3
        for fila in filas:
            # nomenclatura de §5.3: fecha_hora + tipo, sin restos del placeholder
            assert fila["filename"] == f"2025-11-04_{fila['filename'][11:20]}_{fila['tipo']}.wav"
            assert fila["estado"] == "propuesto"
            assert fila["tipo_propuesto_por"] is not None
            assert fila["confianza"] is not None and 0.0 <= fila["confianza"] <= 1.0
            assert Path(fila["clip_path"]).exists()
            assert Path(fila["espectrograma_path"]).exists()
    finally:
        con.close()

    # re-ingerir la MISMA grabación: el dedupe no deja pasar nada (idempotente)
    resumen2 = ingerir.ingerir(
        wav_campania, fuente="campania-test", ruta_db=db_indexada, raiz_datos=tmp_path / "datos"
    )
    assert resumen2["ok"]
    assert resumen2["ingresados"] == 0
    assert resumen2["dedupeados"] == resumen2["candidatos"]


def test_ingesta_rechaza_archivo_roto(db_indexada, tmp_path):
    roto = tmp_path / "20251104_100000.WAV"
    roto.write_bytes(b"RIFF" + b"\x00" * 20)  # cabecera trunca
    resumen = ingerir.ingerir(roto, ruta_db=db_indexada, raiz_datos=tmp_path / "datos")
    assert not resumen["ok"]
    assert resumen["errores"]


def test_solapa_tolerancia():
    intervalos = [(10.0, 12.0)]
    assert ingerir.solapa(12.5, 13.5, intervalos)  # a 0.5 s del borde: solapa
    assert not ingerir.solapa(13.5, 14.5, intervalos)  # a 1.5 s: no


# ---------- veredictos existentes intactos tras migración ----------


def test_migracion_no_toca_veredictos(db_indexada):
    con = base.conectar(db_indexada)
    try:
        registrado = base.registrar_veredicto(con, con.execute(
            "SELECT filename FROM segmento WHERE estado='propuesto' LIMIT 1"
        ).fetchone()["filename"], "confirmar", revisor="test")
        assert registrado
        antes = con.execute(
            "SELECT filename, estado, revisor FROM segmento WHERE revisor='test'"
        ).fetchall()
    finally:
        con.close()
    # reconectar re-corre la migración: nada cambia
    con = base.conectar(db_indexada)
    try:
        despues = con.execute(
            "SELECT filename, estado, revisor FROM segmento WHERE revisor='test'"
        ).fetchall()
        assert [tuple(f) for f in antes] == [tuple(f) for f in despues]
    finally:
        con.close()
