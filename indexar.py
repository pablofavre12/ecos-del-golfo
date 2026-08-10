"""Indexa los clips del catálogo para la búsqueda inversa (R10).

Calcula el embedding de cada clip de `segmento` y lo guarda en la tabla
`embedding` de ecos.db (vector float32 como BLOB, con el nombre del embedder
usado). Idempotente: re-correr solo indexa lo que falta, o re-indexa todo lo
que haya quedado calculado con OTRO embedder que el pedido.

Uso: python indexar.py [--embedder espectral|perch] [--db ruta/ecos.db]
"""

from __future__ import annotations

import sys
from pathlib import Path

import base
import embeddings


def indexar(
    ruta_db: Path | str = base.RUTA_DB, nombre_embedder: str = "espectral"
) -> dict[str, int]:
    """Devuelve conteos: indexados / al_dia / sin_clip / con_error."""
    if nombre_embedder not in embeddings.EMBEDDERS:
        opciones = ", ".join(sorted(embeddings.EMBEDDERS))
        raise SystemExit(f"Embedder desconocido: {nombre_embedder!r} (opciones: {opciones})")
    embedder = embeddings.EMBEDDERS[nombre_embedder]()

    con = base.conectar(ruta_db)
    conteos = {"indexados": 0, "al_dia": 0, "sin_clip": 0, "con_error": 0}
    try:
        segmentos = con.execute(
            """
            SELECT s.filename, s.clip_path, e.embedder AS embedder_previo
            FROM segmento s LEFT JOIN embedding e ON e.filename = s.filename
            ORDER BY s.filename
            """
        ).fetchall()

        for s in segmentos:
            if s["embedder_previo"] == embedder.nombre:
                conteos["al_dia"] += 1
                continue
            if not s["clip_path"] or not Path(s["clip_path"]).exists():
                conteos["sin_clip"] += 1
                print(f"  ⚠ sin clip en disco: {s['filename']}")
                continue
            try:
                vector = embedder.embed(Path(s["clip_path"]))
            except Exception as err:  # un clip roto no frena el índice
                conteos["con_error"] += 1
                print(f"  ⚠ error al embeber {s['filename']}: {err}")
                continue
            con.execute(
                """
                INSERT INTO embedding (filename, embedder, dimension, vector)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(filename) DO UPDATE SET
                    embedder = excluded.embedder,
                    dimension = excluded.dimension,
                    vector = excluded.vector,
                    creado_en = datetime('now')
                """,
                (s["filename"], embedder.nombre, len(vector), embeddings.vector_a_blob(vector)),
            )
            conteos["indexados"] += 1
        con.commit()
    finally:
        con.close()
    return conteos


def main(argv: list[str]) -> int:
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    nombre = argv[argv.index("--embedder") + 1] if "--embedder" in argv else "espectral"
    ruta_db = Path(argv[argv.index("--db") + 1]) if "--db" in argv else base.RUTA_DB

    print(f"Indexando clips de {ruta_db} con el embedder {nombre!r}…")
    c = indexar(ruta_db, nombre)
    print(
        f"Listo: {c['indexados']} indexados, {c['al_dia']} ya al día, "
        f"{c['sin_clip']} sin clip, {c['con_error']} con error."
    )
    return 0 if c["con_error"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
