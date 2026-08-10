"""Genera fixtures SINTÉTICOS de desarrollo en fixtures/.

No son grabaciones reales: son barridos, tonos e impulsos armados con numpy
que imitan la *forma* de los tipos de sonido del informe exploratorio (§2),
con la distribución y nomenclatura reales del catálogo (§5.3).
"""

from __future__ import annotations

import csv
import wave
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).parent
SR = 32000  # Hz — alcanza de sobra para tipos < 4 kHz

COLUMNAS_CATALOGO = [
    "filename",
    "type",
    "recording_source",
    "recording_start",
    "offset_in_recording_s",
    "absolute_datetime",
    "status",
]

# Distribución que espeja el informe (§2): embarcación con los 5 tipos más las
# dos categorías de descarte; muelle con mayoría pulsive_call. El catálogo
# llega ya resuelto (confirmado/descartado/desconocido): los pendientes de la
# cola son exactamente los 18 de candidatos.csv.
# (tipo, cantidad, status)
PLAN_EMBARCACION = [
    ("pulsive_call", 10, "confirmado"),
    ("up_call", 8, "confirmado"),
    ("high_call", 5, "confirmado"),
    ("gunshot_call", 3, "confirmado"),
    ("no_clasificado", 2, "desconocido"),
    ("revisar_muy_cortos", 4, "descartado"),
    ("posible_ruido_agua", 3, "descartado"),
]
PLAN_MUELLE = [
    ("pulsive_call", 4, "confirmado"),
    ("high_call", 1, "confirmado"),
]

INICIO_EMBARCACION = datetime(2026, 8, 3, 17, 38, 56)
INICIO_MUELLE = datetime(2025, 10, 4, 9, 0, 0)

# Cola de candidatos estilo muelle (18 filas, veredicto pendiente).
PLAN_CANDIDATOS = [("pulsive_call", 16), ("high_call", 1), ("no_clasificado", 1)]
INICIO_CANDIDATOS = datetime(2025, 10, 6, 15, 0, 0)


def _envolvente(n: int, ataque: float = 0.08, caida: float = 0.2) -> np.ndarray:
    """Fade-in/fade-out para que el clip no arranque ni corte en seco."""
    env = np.ones(n)
    a, c = max(1, int(n * ataque)), max(1, int(n * caida))
    env[:a] = np.linspace(0, 1, a)
    env[-c:] = np.linspace(1, 0, c)
    return env


def sintetizar(tipo: str, rng: np.random.Generator) -> np.ndarray:
    """Devuelve un clip mono float en [-1, 1] según la forma del tipo."""
    if tipo == "up_call":
        # Barrido ascendente grave ~80→250 Hz, ~1 s
        dur = rng.uniform(0.7, 1.2)
        t = np.linspace(0, dur, int(SR * dur), endpoint=False)
        f0, f1 = rng.uniform(75, 90), rng.uniform(220, 260)
        fase = 2 * np.pi * (f0 * t + (f1 - f0) * t**2 / (2 * dur))
        y = np.sin(fase) + 0.25 * np.sin(2 * fase)
    elif tipo == "high_call":
        # Tono ~370 Hz con vibrato leve, ~1.2 s
        dur = rng.uniform(1.0, 1.4)
        t = np.linspace(0, dur, int(SR * dur), endpoint=False)
        f = 370 + 12 * np.sin(2 * np.pi * 3 * t)
        y = np.sin(2 * np.pi * np.cumsum(f) / SR)
    elif tipo == "pulsive_call":
        # Stack de armónicos apilados sobre una fundamental grave, ~0.6 s
        dur = rng.uniform(0.5, 0.8)
        t = np.linspace(0, dur, int(SR * dur), endpoint=False)
        f0 = rng.uniform(120, 180)
        y = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 7))
        y = np.asarray(y) * (1 + 0.4 * np.sin(2 * np.pi * 18 * t))  # pulsación
    elif tipo == "gunshot_call":
        # Impulso de banda ancha con caída rápida, ~0.5 s total
        dur = 0.5
        n = int(SR * dur)
        y = rng.normal(0, 1, n) * np.exp(-np.linspace(0, 18, n))
    elif tipo == "posible_ruido_agua":
        # Ruido filtrado sin estructura tonal clara, ~0.6 s
        dur = 0.6
        n = int(SR * dur)
        ruido = rng.normal(0, 1, n)
        y = np.convolve(ruido, np.ones(24) / 24, mode="same")
    elif tipo == "revisar_muy_cortos":
        # Fragmento tonal muy corto (la categoría existe por durar < 0.3 s,
        # pero el piso del ticket para clips es 0.5 s)
        dur = 0.5
        t = np.linspace(0, dur, int(SR * dur), endpoint=False)
        y = np.sin(2 * np.pi * rng.uniform(100, 240) * t) * 0.6
    else:  # no_clasificado y cualquier tipo futuro
        dur = 0.8
        t = np.linspace(0, dur, int(SR * dur), endpoint=False)
        y = np.sin(2 * np.pi * 197 * t) + 0.3 * np.sin(2 * np.pi * 305 * t)

    y = np.asarray(y, dtype=np.float64)
    y *= _envolvente(len(y))
    y += rng.normal(0, 0.02, len(y))  # piso de ruido de mar
    return y / (np.max(np.abs(y)) + 1e-9) * 0.85


def escribir_wav(ruta: Path, y: np.ndarray) -> None:
    datos = (y * 32767).astype(np.int16)
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(datos.tobytes())


def escribir_espectrograma(ruta_wav: Path, ruta_png: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with wave.open(str(ruta_wav), "rb") as w:
        sr = w.getframerate()
        y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16) / 32768.0

    fig, ax = plt.subplots(figsize=(4.2, 2.6), dpi=90)
    fig.patch.set_facecolor("#0a1524")
    ax.set_facecolor("#0a1524")
    ax.specgram(y, NFFT=512, Fs=sr, noverlap=384, cmap="magma")
    ax.set_ylim(0, 4000)
    ax.tick_params(colors="#6b84a3", labelsize=6)
    for spine in ax.spines.values():
        spine.set_color("#22344d")
    ax.set_xlabel("s", color="#6b84a3", fontsize=6)
    ax.set_ylabel("Hz", color="#6b84a3", fontsize=6)
    fig.tight_layout(pad=0.4)
    fig.savefig(ruta_png, facecolor=fig.get_facecolor())
    plt.close(fig)


def nombre_clip(momento: datetime, tipo: str) -> str:
    """Nomenclatura de §5.3: {YYYY-MM-DD}_{HHhMMmSSs}_{tipo}.wav"""
    return f"{momento:%Y-%m-%d}_{momento:%Hh%Mm%Ss}_{tipo}.wav"


def _filas(plan, inicio: datetime, fuente: str, rng: np.random.Generator, con_status=True):
    filas, offset = [], 0.0
    for tipo, cantidad, *resto in plan:
        for _ in range(cantidad):
            offset += float(rng.uniform(8, 90))
            momento = inicio + timedelta(seconds=offset)
            fila = {
                "filename": nombre_clip(momento, tipo),
                "type": tipo,
                "recording_source": fuente,
                "recording_start": inicio.strftime("%Y-%m-%d %H:%M:%S"),
                "offset_in_recording_s": f"{offset:.1f}",
                "absolute_datetime": momento.strftime("%Y-%m-%d %H:%M:%S"),
            }
            if con_status:
                fila["status"] = resto[0]
            filas.append(fila)
    return filas


def generar(destino: Path | None = None, con_espectrogramas: bool = True) -> Path:
    destino = destino or (RAIZ / "fixtures")
    clips = destino / "clips"
    espectros = destino / "espectrogramas"
    clips.mkdir(parents=True, exist_ok=True)
    espectros.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(2026)

    filas_catalogo = _filas(PLAN_EMBARCACION, INICIO_EMBARCACION, "embarcacion-2026-08", rng)
    filas_catalogo += _filas(PLAN_MUELLE, INICIO_MUELLE, "muelle-madryn-2025-10", rng)

    filas_candidatos = _filas(
        PLAN_CANDIDATOS, INICIO_CANDIDATOS, "muelle-madryn-2025-10", rng, con_status=False
    )
    for fila in filas_candidatos:
        fila["confirmed_by_ear"] = ""  # vacía: pendiente de escucha

    with open(destino / "catalogo.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS_CATALOGO)
        w.writeheader()
        w.writerows(filas_catalogo)

    with open(destino / "candidatos.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS_CATALOGO[:-1] + ["confirmed_by_ear"])
        w.writeheader()
        w.writerows(filas_candidatos)

    for fila in filas_catalogo + filas_candidatos:
        ruta_wav = clips / fila["filename"]
        escribir_wav(ruta_wav, sintetizar(fila["type"], rng))
        if con_espectrogramas:
            escribir_espectrograma(ruta_wav, espectros / (ruta_wav.stem + ".png"))

    return destino


if __name__ == "__main__":
    destino = generar()
    n_clips = len(list((destino / "clips").glob("*.wav")))
    print(f"Fixtures sintéticos generados en {destino}/")
    print(f"  catalogo.csv + candidatos.csv + {n_clips} clips + espectrogramas")
