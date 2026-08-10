"""Propuesta de tipo con confianza — dos motores sobre los embeddings Perch.

a) VECINOS: k-NN (k=5, similitud coseno) contra los ejemplares CONFIRMADOS del
   catálogo. Tipo por voto ponderado por similitud; confianza = fracción del
   peso total que se lleva el tipo ganador.

b) CLASIFICADOR LINEAL re-entrenable: softmax regression en numpy puro (sin
   sklearn), entrenado por entrenar.py sobre confirmados (tipos) + descartados
   (clase 'descarte'), versionado en la tabla `modelo`. Confianza = probabilidad
   softmax del tipo ganador; también devuelve el top-2.

`clasificar()` usa el modelo vigente (última versión compatible con el
embedder del vector) y cae a los vecinos si no hay modelo. El resultado
incluye `motor` ('clasificador-vN' o 'vecinos') para asentar la trazabilidad
en `segmento.tipo_propuesto_por`.

Uso como CLI: python clasificar.py <filename-del-catalogo> [--db ruta]
(clasifica un clip ya indexado, útil para inspección).
"""

from __future__ import annotations

import io
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import base
import embeddings

K_VECINOS = 5
CLASE_DESCARTE = "descarte"


# ---------- softmax en numpy puro ----------


def softmax(logits: np.ndarray) -> np.ndarray:
    """Softmax estable por filas."""
    z = logits - logits.max(axis=-1, keepdims=True)
    ez = np.exp(z)
    return ez / ez.sum(axis=-1, keepdims=True)


def entrenar_softmax(
    X: np.ndarray,
    y: np.ndarray,
    n_clases: int,
    iteraciones: int = 400,
    tasa: float = 1.0,
    reg_l2: float = 1e-3,
    semilla: int = 2026,
) -> tuple[np.ndarray, np.ndarray]:
    """Softmax regression full-batch con descenso por gradiente. Devuelve
    (W (dims, clases), b (clases,)). Determinista (semilla fija)."""
    rng = np.random.default_rng(semilla)
    n, d = X.shape
    W = rng.normal(0, 0.01, (d, n_clases))
    b = np.zeros(n_clases)
    Y = np.zeros((n, n_clases))
    Y[np.arange(n), y] = 1.0
    # pesos por clase inversos a la frecuencia: las clases chicas no se ahogan
    frec = Y.sum(axis=0)
    peso_clase = n / (n_clases * np.maximum(frec, 1.0))
    peso = (Y @ peso_clase)[:, None]

    for _ in range(iteraciones):
        P = softmax(X @ W + b)
        G = (P - Y) * peso / n
        W -= tasa * (X.T @ G + reg_l2 * W)
        b -= tasa * G.sum(axis=0)
    return W, b


@dataclass
class Modelo:
    version: int
    embedder: str
    clases: list[str]
    W: np.ndarray
    b: np.ndarray
    accuracy_cv: float | None

    def predecir(self, vector: np.ndarray) -> np.ndarray:
        """Probabilidades softmax (una por clase) para un vector."""
        return softmax(vector @ self.W + self.b)


def serializar_pesos(W: np.ndarray, b: np.ndarray, clases: list[str]) -> bytes:
    buffer = io.BytesIO()
    np.savez_compressed(
        buffer,
        W=W.astype(np.float32),
        b=b.astype(np.float32),
        clases=np.array(clases, dtype=object),
    )
    return buffer.getvalue()


def cargar_modelo(con: sqlite3.Connection, embedder: str | None = None) -> Modelo | None:
    """Última versión de la tabla `modelo` (opcionalmente, del embedder dado)."""
    consulta = "SELECT version, embedder, accuracy_cv, pesos FROM modelo"
    args: tuple = ()
    if embedder:
        consulta += " WHERE embedder = ?"
        args = (embedder,)
    fila = con.execute(consulta + " ORDER BY version DESC LIMIT 1", args).fetchone()
    if not fila:
        return None
    datos = np.load(io.BytesIO(fila["pesos"]), allow_pickle=True)
    return Modelo(
        version=int(fila["version"]),
        embedder=fila["embedder"],
        clases=[str(c) for c in datos["clases"]],
        W=datos["W"].astype(np.float64),
        b=datos["b"].astype(np.float64),
        accuracy_cv=fila["accuracy_cv"],
    )


# ---------- datos de entrenamiento / vecinos desde la DB ----------


def ejemplares_confirmados(
    con: sqlite3.Connection,
) -> tuple[np.ndarray, list[str], str | None]:
    """(matriz de vectores, tipo efectivo por fila, nombre del embedder) de los
    segmentos confirmados con embedding."""
    filas = con.execute(
        """
        SELECT e.vector, e.dimension, e.embedder,
               COALESCE(s.tipo_corregido, s.tipo) AS tipo_efectivo
        FROM segmento s JOIN embedding e ON e.filename = s.filename
        WHERE s.estado = 'confirmado'
        ORDER BY s.filename
        """
    ).fetchall()
    if not filas:
        return np.zeros((0, 0)), [], None
    X = np.stack([embeddings.blob_a_vector(f["vector"], f["dimension"]) for f in filas])
    return X, [f["tipo_efectivo"] for f in filas], filas[0]["embedder"]


def vecinos(
    con: sqlite3.Connection, vector: np.ndarray, k: int = K_VECINOS
) -> dict | None:
    """Motor a): voto ponderado por similitud coseno de los k confirmados más
    cercanos. Los vectores del índice están L2-normalizados (producto punto =
    coseno). Devuelve dict tipo/confianza/top2/motor, o None sin confirmados."""
    X, tipos, _ = ejemplares_confirmados(con)
    if len(tipos) == 0:
        return None
    v = np.asarray(vector, dtype=np.float32)
    norma = float(np.linalg.norm(v))
    if norma > 0:
        v = v / norma
    similitudes = X @ v
    orden = np.argsort(similitudes)[::-1][: min(k, len(tipos))]
    pesos: dict[str, float] = {}
    for i in orden:
        pesos[tipos[i]] = pesos.get(tipos[i], 0.0) + max(float(similitudes[i]), 0.0)
    total = sum(pesos.values())
    ranking = sorted(pesos.items(), key=lambda par: par[1], reverse=True)
    if total <= 0:
        return None
    top2 = [(tipo, round(peso / total, 4)) for tipo, peso in ranking[:2]]
    return {
        "tipo": ranking[0][0],
        "confianza": round(ranking[0][1] / total, 4),
        "top2": top2,
        "motor": "vecinos",
    }


def clasificar(
    con: sqlite3.Connection, vector: np.ndarray, embedder: str | None = None
) -> dict | None:
    """Motor b) con fallback a): usa el modelo vigente si existe (y es del
    embedder correcto); si no, vota por vecinos. None si no hay con qué."""
    modelo = cargar_modelo(con, embedder)
    if modelo is not None:
        v = np.asarray(vector, dtype=np.float64)
        norma = float(np.linalg.norm(v))
        if norma > 0:
            v = v / norma
        probabilidades = modelo.predecir(v)
        orden = np.argsort(probabilidades)[::-1]
        top2 = [(modelo.clases[i], round(float(probabilidades[i]), 4)) for i in orden[:2]]
        return {
            "tipo": modelo.clases[orden[0]],
            "confianza": round(float(probabilidades[orden[0]]), 4),
            "top2": top2,
            "motor": f"clasificador-v{modelo.version}",
        }
    return vecinos(con, vector)


# ---------- CLI de inspección ----------


def main(argv: list[str]) -> int:
    if len(argv) < 2 or "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    filename = argv[1]
    ruta_db = Path(argv[argv.index("--db") + 1]) if "--db" in argv else base.RUTA_DB
    con = base.conectar(ruta_db)
    try:
        fila = con.execute(
            "SELECT vector, dimension, embedder FROM embedding WHERE filename = ?",
            (filename,),
        ).fetchone()
        if not fila:
            print(f"{filename} no está indexado (correr indexar.py)")
            return 1
        vector = embeddings.blob_a_vector(fila["vector"], fila["dimension"])
        resultado = clasificar(con, vector, fila["embedder"])
    finally:
        con.close()
    if not resultado:
        print("Sin modelo ni confirmados para clasificar.")
        return 1
    print(f"{filename} → {resultado['tipo']} ({resultado['confianza']:.0%}, {resultado['motor']})")
    print(f"  top-2: {resultado['top2']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
