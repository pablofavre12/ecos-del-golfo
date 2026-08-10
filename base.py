"""Base de datos del catálogo — única fuente de verdad (D10).

Esquema SQLite compartido por el importador, el tablero y los tests.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

RUTA_DB = Path(__file__).parent / "ecos.db"

ESTADOS = ("propuesto", "confirmado", "descartado", "desconocido")

# Tipos conocidos del informe exploratorio (§2). "revisar_muy_cortos" y
# "posible_ruido_agua" son categorías de descarte que también viajan en el CSV.
TIPOS = (
    "up_call",
    "high_call",
    "pulsive_call",
    "gunshot_call",
    "no_clasificado",
    "revisar_muy_cortos",
    "posible_ruido_agua",
)

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS segmento (
    filename            TEXT PRIMARY KEY,
    tipo                TEXT NOT NULL,
    fuente              TEXT NOT NULL,
    inicio_grabacion    TEXT,
    offset_s            REAL,
    fecha_hora_absoluta TEXT,
    estado              TEXT NOT NULL DEFAULT 'propuesto'
                        CHECK (estado IN ('propuesto','confirmado','descartado','desconocido')),
    tipo_corregido      TEXT,
    clip_path           TEXT,
    espectrograma_path  TEXT,
    revisado_en         TEXT,
    revisor             TEXT,
    creado_en           TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS embedding (
    filename   TEXT PRIMARY KEY REFERENCES segmento(filename),
    embedder   TEXT NOT NULL,
    dimension  INTEGER NOT NULL,
    vector     BLOB NOT NULL,
    creado_en  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Umbrales del detector, versionados con historial (R12). Nunca se pisa una
-- versión: recalibrar.py siempre inserta una nueva. `parametros` es JSON.
CREATE TABLE IF NOT EXISTS calibracion (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sitio         TEXT NOT NULL DEFAULT 'global',
    version       INTEGER NOT NULL,
    parametros    TEXT NOT NULL,
    n_confirmados INTEGER NOT NULL DEFAULT 0,
    n_descartados INTEGER NOT NULL DEFAULT 0,
    creado_en     TEXT NOT NULL DEFAULT (datetime('now')),
    nota          TEXT,
    UNIQUE (sitio, version)
);

-- Clasificador lineal re-entrenable (softmax sobre embeddings), versionado.
-- `pesos` es un .npz serializado (W, b, clases). Nunca se pisa una versión.
CREATE TABLE IF NOT EXISTS modelo (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    version     INTEGER NOT NULL UNIQUE,
    embedder    TEXT NOT NULL,
    clases      TEXT NOT NULL,
    n_por_clase TEXT NOT NULL,
    accuracy_cv REAL,
    pesos       BLOB NOT NULL,
    creado_en   TEXT NOT NULL DEFAULT (datetime('now')),
    nota        TEXT
);
"""

# Calibración semilla (versión 1): los umbrales de la sesión exploratoria,
# tal como quedaron en el informe (§4). Todo consumidor los lee de la tabla
# `calibracion` — nunca de esta constante directamente.
CALIBRACION_INICIAL = {
    # VAD por energía (§4.2)
    "vad_percentil": 89.0,  # umbral adaptativo: percentil 88-90 del RMS en dB
    "vad_piso_sobre_mediana_db": 3.0,  # el umbral nunca baja de mediana + piso
    "vad_fusion_s": 0.45,  # fusionar eventos separados por menos de 0.4-0.5 s
    "dur_min_s": 0.15,
    "dur_max_s": 20.0,
    # Índice armónico (§4.3)
    "armonico_min": 0.65,  # vocalización tonal candidata
    "armonico_confiable_dur_min_s": 0.3,  # por debajo, HPSS no es confiable
    "tonal_dur_max_s": 4.0,  # tonal > 4 s se reclasifica como ruido (§4.7)
    # Gunshot / impulsivos (§4.6)
    "gunshot_armonico_max": 0.35,
    "gunshot_dur_min_s": 0.08,
    "gunshot_dur_max_s": 0.35,
    "cresta_min": 10.0,  # factor de cresta (pico / RMS)
    "concentracion_min": 0.3,  # energía de la envolvente en ±5 ms del pico
    # Ruido de sitio (§4.7)
    "prominencia_min_db": 6.0,  # contra el archivo completo
    "bandas_excluidas_hz": [],  # pares [lo, hi]; vacío para 'global'
}


def _migrar(con: sqlite3.Connection) -> None:
    """Migración idempotente: columnas nuevas de `segmento` + semilla de
    calibración. Corre en cada conexión; solo actúa si falta algo."""
    columnas = {fila[1] for fila in con.execute("PRAGMA table_info(segmento)")}
    if "tipo_propuesto_por" not in columnas:
        con.execute("ALTER TABLE segmento ADD COLUMN tipo_propuesto_por TEXT")
        # Los segmentos que ya existían vienen todos del catálogo del informe.
        con.execute("UPDATE segmento SET tipo_propuesto_por = 'sesion-exploratoria'")
    if "confianza" not in columnas:
        con.execute("ALTER TABLE segmento ADD COLUMN confianza REAL")  # NULL = histórico
    if con.execute("SELECT COUNT(*) FROM calibracion").fetchone()[0] == 0:
        con.execute(
            """
            INSERT INTO calibracion (sitio, version, parametros, n_confirmados,
                                     n_descartados, nota)
            VALUES ('global', 1, ?, 18, 4,
                    'calibración de la sesión exploratoria, 18 escuchas')
            """,
            (json.dumps(CALIBRACION_INICIAL),),
        )
    con.commit()


def conectar(ruta: Path | str = RUTA_DB) -> sqlite3.Connection:
    con = sqlite3.connect(str(ruta))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(_ESQUEMA)
    _migrar(con)
    return con


def calibracion_vigente(con: sqlite3.Connection, sitio: str = "global") -> tuple[int, dict]:
    """Última versión de calibración para el sitio (cae a 'global' si no hay).

    Devuelve (version, parametros). La semilla garantiza que 'global' existe.
    """
    for candidato in (sitio, "global"):
        fila = con.execute(
            "SELECT version, parametros FROM calibracion WHERE sitio = ? "
            "ORDER BY version DESC LIMIT 1",
            (candidato,),
        ).fetchone()
        if fila:
            return int(fila["version"]), json.loads(fila["parametros"])
    raise RuntimeError("Sin calibración en la DB (la semilla debería existir)")


def registrar_veredicto(
    con: sqlite3.Connection,
    filename: str,
    accion: str,
    tipo_corregido: str | None = None,
    revisor: str = "local",
) -> bool:
    """Asienta el veredicto de la cola de revisión sobre un segmento.

    Acciones: confirmar / corregir (requiere tipo_corregido) / descartar /
    desconocido. Devuelve False si el segmento no existe.
    """
    acciones = {
        "confirmar": "confirmado",
        "corregir": "confirmado",
        "descartar": "descartado",
        "desconocido": "desconocido",
    }
    if accion not in acciones:
        raise ValueError(f"Acción inválida: {accion!r}")
    if accion == "corregir" and not tipo_corregido:
        raise ValueError("Corregir requiere tipo_corregido")

    ahora = datetime.now().isoformat(timespec="seconds")
    cur = con.execute(
        """
        UPDATE segmento
        SET estado = ?, tipo_corregido = ?, revisado_en = ?, revisor = ?,
            actualizado_en = datetime('now')
        WHERE filename = ?
        """,
        (
            acciones[accion],
            tipo_corregido if accion == "corregir" else None,
            ahora,
            revisor,
            filename,
        ),
    )
    con.commit()
    return cur.rowcount > 0
