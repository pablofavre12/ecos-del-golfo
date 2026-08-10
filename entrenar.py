"""Entrena el clasificador lineal (softmax, numpy puro) y lo versiona.

Datos: embeddings de la DB — confirmados con su tipo efectivo (corregido si
lo hubo) + descartados como clase 'descarte'. Las clases con menos de
MIN_POR_CLASE ejemplos se excluyen del entrenamiento (y se informa).

Accuracy honesta: validación cruzada estratificada de k folds (k = mín(5,
tamaño de la clase más chica)) ANTES de entrenar el modelo final con todos
los datos. El modelo queda en la tabla `modelo` como versión nueva (nunca
pisa una anterior): pesos .npz como BLOB + clases + n por clase + accuracy.

Uso: python entrenar.py [--db ruta/ecos.db] [--nota texto]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

import base
import clasificar
import embeddings

MIN_POR_CLASE = 3
SEMILLA = 2026


def datos_de_entrenamiento(con) -> tuple[np.ndarray, list[str], str | None, dict[str, int]]:
    """(X, etiquetas, embedder, excluidas): confirmados por tipo efectivo +
    descartados como 'descarte'. Filtra clases con menos de MIN_POR_CLASE."""
    filas = con.execute(
        """
        SELECT e.vector, e.dimension, e.embedder, s.estado,
               COALESCE(s.tipo_corregido, s.tipo) AS tipo_efectivo
        FROM segmento s JOIN embedding e ON e.filename = s.filename
        WHERE s.estado IN ('confirmado', 'descartado')
        ORDER BY s.filename
        """
    ).fetchall()
    if not filas:
        return np.zeros((0, 0)), [], None, {}

    embedders = {f["embedder"] for f in filas}
    if len(embedders) > 1:
        raise SystemExit(
            f"El índice mezcla embedders ({sorted(embedders)}): re-indexar con uno solo."
        )

    vectores, etiquetas = [], []
    for f in filas:
        etiqueta = clasificar.CLASE_DESCARTE if f["estado"] == "descartado" else f["tipo_efectivo"]
        vectores.append(embeddings.blob_a_vector(f["vector"], f["dimension"]))
        etiquetas.append(etiqueta)

    conteo: dict[str, int] = {}
    for etiqueta in etiquetas:
        conteo[etiqueta] = conteo.get(etiqueta, 0) + 1
    excluidas = {c: n for c, n in conteo.items() if n < MIN_POR_CLASE}
    indices = [i for i, et in enumerate(etiquetas) if et not in excluidas]
    X = np.stack([vectores[i] for i in indices]).astype(np.float64)
    etiquetas = [etiquetas[i] for i in indices]
    return X, etiquetas, filas[0]["embedder"], excluidas


def _folds_estratificados(y: np.ndarray, k: int, semilla: int) -> list[np.ndarray]:
    """k folds con cada clase repartida pareja (round-robin tras mezclar)."""
    rng = np.random.default_rng(semilla)
    folds: list[list[int]] = [[] for _ in range(k)]
    for clase in np.unique(y):
        indices = np.flatnonzero(y == clase)
        rng.shuffle(indices)
        for posicion, indice in enumerate(indices):
            folds[posicion % k].append(int(indice))
    return [np.array(sorted(f)) for f in folds]


def accuracy_cv(X: np.ndarray, y: np.ndarray, n_clases: int, k: int) -> float:
    """Accuracy promedio de validación cruzada estratificada de k folds."""
    folds = _folds_estratificados(y, k, SEMILLA)
    aciertos, total = 0, 0
    for i, prueba in enumerate(folds):
        entrenamiento = np.concatenate([f for j, f in enumerate(folds) if j != i])
        W, b = clasificar.entrenar_softmax(X[entrenamiento], y[entrenamiento], n_clases)
        predicho = np.argmax(clasificar.softmax(X[prueba] @ W + b), axis=1)
        aciertos += int((predicho == y[prueba]).sum())
        total += len(prueba)
    return aciertos / total if total else 0.0


def entrenar(ruta_db: Path | str = base.RUTA_DB, nota: str | None = None) -> dict:
    """Loop completo. Devuelve un resumen dict (version, accuracy_cv, n_por_clase…)."""
    con = base.conectar(ruta_db)
    try:
        X, etiquetas, embedder, excluidas = datos_de_entrenamiento(con)
        if len(etiquetas) == 0:
            raise SystemExit("Sin embeddings con veredicto en la DB: nada que entrenar.")
        for clase, n in sorted(excluidas.items()):
            print(f"  ⚠ clase {clase!r} excluida: solo {n} ejemplos (mínimo {MIN_POR_CLASE})")

        clases = sorted(set(etiquetas))
        indice_clase = {c: i for i, c in enumerate(clases)}
        y = np.array([indice_clase[e] for e in etiquetas])
        n_por_clase = {c: int((y == indice_clase[c]).sum()) for c in clases}
        k = min(5, min(n_por_clase.values()))

        acc = accuracy_cv(X, y, len(clases), k) if k >= 2 else None
        W, b = clasificar.entrenar_softmax(X, y, len(clases))

        version = con.execute("SELECT COALESCE(MAX(version), 0) FROM modelo").fetchone()[0] + 1
        con.execute(
            """
            INSERT INTO modelo (version, embedder, clases, n_por_clase, accuracy_cv,
                                pesos, nota)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version,
                embedder,
                json.dumps(clases),
                json.dumps(n_por_clase),
                acc,
                clasificar.serializar_pesos(W, b, clases),
                nota or f"entrenado con {len(y)} ejemplos, CV de {k} folds",
            ),
        )
        con.commit()
    finally:
        con.close()
    return {
        "version": version,
        "embedder": embedder,
        "clases": clases,
        "n_por_clase": n_por_clase,
        "accuracy_cv": acc,
        "folds": k,
        "excluidas": excluidas,
    }


def main(argv: list[str]) -> int:
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    ruta_db = Path(argv[argv.index("--db") + 1]) if "--db" in argv else base.RUTA_DB
    nota = argv[argv.index("--nota") + 1] if "--nota" in argv else None

    print(f"Entrenando el clasificador con los veredictos de {ruta_db}…")
    resumen = entrenar(ruta_db, nota)
    print(f"\nModelo v{resumen['version']} guardado (embedder {resumen['embedder']!r}):")
    for clase, n in sorted(resumen["n_por_clase"].items()):
        print(f"  {clase:20s} {n:4d} ejemplos")
    if resumen["accuracy_cv"] is not None:
        print(
            f"  accuracy CV ({resumen['folds']} folds): {resumen['accuracy_cv']:.1%} — "
            "medida ANTES del entrenamiento final, sobre datos no vistos por cada fold"
        )
    else:
        print("  accuracy CV: no calculable (alguna clase con un solo ejemplo)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
