"""Embeddings de clips para la búsqueda inversa (R10) — diseño enchufable.

Dos implementaciones detrás de la misma interfaz `Embedder`:

- `EmbedderEspectral` (default): funciona HOY con numpy puro. Banco de
  filtros log-espaciados sobre el espectro (tipo mel simplificado, 32 bandas)
  con estadísticas temporales por banda. Determinista: el mismo clip produce
  siempre el mismo vector.
- `EmbedderPerch`: adaptador para producción con datos reales. Requiere
  `perch-hoplite` (Google) instalado en la máquina del admin; acá solo
  levanta un error claro con las instrucciones si falta.

Los vectores se guardan L2-normalizados, así la similitud coseno entre dos
clips es el producto punto de sus vectores.
"""

from __future__ import annotations

import sqlite3
import wave
from pathlib import Path

import numpy as np

# Parámetros del embedder espectral. Cambiarlos cambia el espacio de
# embeddings: si se tocan, hay que re-indexar (subir la VERSION lo fuerza).
N_BANDAS = 32
NFFT = 1024
HOP = 256
FREQ_MIN = 40.0
FREQ_MAX = 4000.0  # los tipos del informe viven por debajo de 4 kHz


class Embedder:
    """Interfaz mínima: un nombre estable (queda asentado en la tabla
    `embedding` para saber con qué se indexó) y embed(clip) → vector."""

    nombre: str = "base"
    dimension: int = 0

    def embed(self, ruta_wav: Path) -> np.ndarray:
        raise NotImplementedError


class EmbedderEspectral(Embedder):
    """Vector de características por clip usando numpy puro.

    Espectrograma de potencia (ventana Hann) → banco de 32 filtros
    triangulares log-espaciados entre 40 y 4000 Hz → log-energía por banda →
    estadísticas temporales por banda (media, desvío, máximo) → 96 dims,
    L2-normalizado. Determinista.
    """

    nombre = "espectral-v1"
    dimension = N_BANDAS * 3

    def embed(self, ruta_wav: Path) -> np.ndarray:
        y, sr = _leer_wav(ruta_wav)
        bandas = _log_energia_por_banda(y, sr)  # (frames, N_BANDAS)
        vector = np.concatenate(
            [bandas.mean(axis=0), bandas.std(axis=0), bandas.max(axis=0)]
        ).astype(np.float32)
        norma = float(np.linalg.norm(vector))
        return vector / norma if norma > 0 else vector


class EmbedderPerch(Embedder):
    """Adaptador para producción: embeddings de Perch (perch-hoplite).

    NO se instala en este repo de desarrollo (arrastra TensorFlow). Es para
    la máquina del admin con los datos reales — ver README.
    """

    nombre = "perch-hoplite"
    dimension = 1280

    def embed(self, ruta_wav: Path) -> np.ndarray:
        try:
            from perch_hoplite.zoo import model_configs  # noqa: F401
        except ImportError as err:
            raise RuntimeError(
                "EmbedderPerch requiere perch-hoplite, que no está instalado en "
                "esta máquina (y no debe instalarse en el entorno de desarrollo: "
                "arrastra TensorFlow). En la máquina del admin con datos reales:\n"
                "  pip install perch-hoplite\n"
                "y después: python indexar.py --embedder perch"
            ) from err
        raise NotImplementedError(
            "Adaptador Perch pendiente de cablear contra datos reales (WCH-468 "
            "deja la interfaz; el cableado se hace con los audios del Golfo)."
        )


EMBEDDERS = {"espectral": EmbedderEspectral, "perch": EmbedderPerch}


def _leer_wav(ruta: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(ruta), "rb") as w:
        sr = w.getframerate()
        n_canales = w.getnchannels()
        crudo = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    y = crudo.astype(np.float64) / 32768.0
    if n_canales > 1:
        y = y.reshape(-1, n_canales).mean(axis=1)
    return y, sr


def _banco_filtros(sr: int) -> np.ndarray:
    """Filtros triangulares log-espaciados: (N_BANDAS, NFFT//2 + 1)."""
    freqs = np.fft.rfftfreq(NFFT, d=1.0 / sr)
    tope = min(FREQ_MAX, sr / 2)
    bordes = np.geomspace(FREQ_MIN, tope, N_BANDAS + 2)
    banco = np.zeros((N_BANDAS, len(freqs)))
    for b in range(N_BANDAS):
        izq, centro, der = bordes[b], bordes[b + 1], bordes[b + 2]
        subida = (freqs - izq) / (centro - izq)
        bajada = (der - freqs) / (der - centro)
        banco[b] = np.clip(np.minimum(subida, bajada), 0, None)
    return banco


def _log_energia_por_banda(y: np.ndarray, sr: int) -> np.ndarray:
    """Espectrograma de potencia por frames → log-energía por banda."""
    if len(y) < NFFT:  # clip más corto que una ventana: pad con ceros
        y = np.pad(y, (0, NFFT - len(y)))
    ventana = np.hanning(NFFT)
    n_frames = 1 + (len(y) - NFFT) // HOP
    indices = np.arange(NFFT)[None, :] + HOP * np.arange(n_frames)[:, None]
    espectro = np.abs(np.fft.rfft(y[indices] * ventana, axis=1)) ** 2
    energia = espectro @ _banco_filtros(sr).T  # (frames, N_BANDAS)
    return np.log10(energia + 1e-10)


# ---------- índice en SQLite ----------


def vector_a_blob(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def blob_a_vector(blob: bytes, dimension: int) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32, count=dimension)


def similares(
    con: sqlite3.Connection, filename: str, n: int = 10
) -> list[tuple[str, float]] | None:
    """Top-n de clips por similitud coseno contra `filename` (excluyéndolo).

    Devuelve [(filename, score)] ordenado de mayor a menor, o None si el
    clip consulta no está indexado (o el índice está vacío).
    """
    filas = con.execute("SELECT filename, dimension, vector FROM embedding").fetchall()
    por_nombre = {f["filename"]: blob_a_vector(f["vector"], f["dimension"]) for f in filas}
    consulta = por_nombre.pop(filename, None)
    if consulta is None or not por_nombre:
        return None
    puntajes = [(otro, float(np.dot(consulta, v))) for otro, v in por_nombre.items()]
    puntajes.sort(key=lambda par: par[1], reverse=True)
    return puntajes[:n]


def hay_indice(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT COUNT(*) FROM embedding").fetchone()[0] > 0
