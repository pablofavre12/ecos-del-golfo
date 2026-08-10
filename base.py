"""Base de datos del catálogo — única fuente de verdad (D10).

Esquema SQLite compartido por el importador, el tablero y los tests.
"""

from __future__ import annotations

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
"""


def conectar(ruta: Path | str = RUTA_DB) -> sqlite3.Connection:
    con = sqlite3.connect(str(ruta))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(_ESQUEMA)
    return con


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
