"""Detector propio de eventos acústicos — la metodología del informe (§4) como código.

Formaliza el pipeline calibrado en la sesión exploratoria:

  VAD por energía (percentil adaptativo por archivo) → segmentos candidatos →
  features (índice armónico vía HPSS por filtrado de mediana, factor de cresta,
  concentración de energía de la envolvente de Hilbert, prominencia espectral
  contra el archivo completo, frecuencia pico, duración) → clasificación gruesa
  (tonal_candidato / impulsivo_candidato / ruido).

Los umbrales NO están hardcodeados: se leen de la tabla `calibracion` (R12),
versionada con historial. HPSS se implementa por filtrado de mediana sobre el
espectrograma (scipy) — el mismo algoritmo que `librosa.effects.hpss`, sin la
dependencia.

Uso: python detectar.py <archivo.wav> [--sitio nombre] [--db ruta/ecos.db]
"""

from __future__ import annotations

import sys
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import hilbert, stft

import base

# Parámetros de señal (estructurales, no de calibración: definen CÓMO se mide,
# no CUÁNDO algo es vocalización — por eso no viven en la tabla calibracion).
VAD_HOP_S = 0.016  # ~16 ms, como el hop del informe (§4.2)
MARGEN_NUCLEO_DB = 6.0  # frames "de núcleo": umbral VAD + este margen
HPSS_NPERSEG = 2048
HPSS_HOP = 512
HPSS_KERNEL = 31  # frames/bins del filtro de mediana (default de librosa)
PROMINENCIA_NPERSEG = 1024  # espectrograma del archivo completo (§4.7)

CLASES_GRUESAS = ("tonal_candidato", "impulsivo_candidato", "ruido")


@dataclass
class Deteccion:
    """Un evento candidato con sus features y su clase gruesa."""

    inicio_s: float
    fin_s: float
    duracion_s: float  # duración del evento VAD (frames activos + fusión)
    duracion_nucleo_s: float  # lapso de los frames ≥ umbral + 6 dB
    clase: str
    indice_armonico: float
    factor_cresta: float
    concentracion_energia: float
    prominencia_db: float
    frecuencia_pico_hz: float

    def como_dict(self) -> dict:
        return asdict(self)


# ---------- lectura de audio ----------


def leer_wav_mono(ruta: Path | str) -> tuple[np.ndarray, int]:
    """WAV PCM 16-bit → mono float32 en [-1, 1]. Lee por bloques de ~1 minuto
    para no duplicar picos de memoria con archivos largos (35 min a 44.1 kHz)."""
    with wave.open(str(ruta), "rb") as w:
        sr = w.getframerate()
        n_canales = w.getnchannels()
        if w.getsampwidth() != 2:
            raise ValueError(f"Solo WAV PCM 16-bit (este tiene {w.getsampwidth() * 8} bits)")
        bloques = []
        paso = sr * 60
        while True:
            crudo = w.readframes(paso)
            if not crudo:
                break
            x = np.frombuffer(crudo, dtype=np.int16).astype(np.float32) / 32768.0
            if n_canales > 1:
                x = x.reshape(-1, n_canales).mean(axis=1, dtype=np.float32)
            bloques.append(x)
    if not bloques:
        return np.zeros(0, dtype=np.float32), sr
    return np.concatenate(bloques), sr


# ---------- VAD por energía (§4.2) ----------


def vad_energia(
    y: np.ndarray,
    sr: int,
    percentil: float,
    fusion_s: float,
    dur_min_s: float,
    dur_max_s: float,
    piso_sobre_mediana_db: float = 3.0,
) -> list[tuple[float, float, float]]:
    """Eventos [(inicio_s, fin_s, duracion_nucleo_s)] por energía RMS con
    umbral adaptativo: percentil de la distribución de RMS en dB de ESTE
    archivo (no un valor fijo). Fusiona eventos separados por menos de
    `fusion_s` y filtra por duración.

    Dos medidas por evento:
    - duración VAD (fin - inicio): frames activos + fusión;
    - duración de NÚCLEO: lapso de los frames ≥ umbral + 6 dB dentro del
      evento. Es la duración del sonido fuerte en sí, robusta a la fusión con
      frames de ruido vecinos — la que usa la ventana de duración del gunshot.

    El umbral nunca baja de mediana + `piso_sobre_mediana_db`: en un archivo
    homogéneo el percentil cae dentro de la fluctuación del fondo y el VAD
    encadenaría frames de ruido puro en mega-eventos.
    """
    hop = max(1, int(round(sr * VAD_HOP_S)))
    n_hops = len(y) // hop
    if n_hops == 0:
        return []
    energia = (y[: n_hops * hop].astype(np.float32) ** 2).reshape(n_hops, hop).mean(axis=1)
    rms_db = 10.0 * np.log10(energia + 1e-12)
    umbral = max(
        float(np.percentile(rms_db, percentil)),
        float(np.median(rms_db)) + piso_sobre_mediana_db,
    )
    activo = rms_db > umbral
    if not activo.any():
        return []

    # corridas contiguas de frames activos
    bordes = np.flatnonzero(np.diff(activo.astype(np.int8)))
    inicios = list(bordes[activo[bordes + 1]] + 1)
    fines = list(bordes[~activo[bordes + 1]] + 1)
    if activo[0]:
        inicios.insert(0, 0)
    if activo[-1]:
        fines.append(n_hops)

    # fusionar gaps cortos
    max_gap = int(round(fusion_s / VAD_HOP_S))
    eventos: list[list[int]] = []
    for s, e in zip(inicios, fines):
        if eventos and s - eventos[-1][1] <= max_gap:
            eventos[-1][1] = e
        else:
            eventos.append([s, e])

    hop_s = hop / sr
    resultado = []
    for s, e in eventos:
        dur = (e - s) * hop_s
        if not (dur_min_s <= dur <= dur_max_s):
            continue
        fuerte = np.flatnonzero(rms_db[s:e] >= umbral + MARGEN_NUCLEO_DB)
        nucleo = (fuerte[-1] - fuerte[0] + 1) * hop_s if len(fuerte) else dur
        resultado.append((s * hop_s, e * hop_s, nucleo))
    return resultado


# ---------- features ----------


def indice_armonico(segmento: np.ndarray, sr: int) -> float:
    """HPSS por filtrado de mediana sobre el espectrograma (Fitzgerald 2010,
    el mismo algoritmo que librosa.effects.hpss, acá con scipy):

    - mediana a lo largo del TIEMPO → realza componentes armónicas (líneas
      horizontales del espectrograma);
    - mediana a lo largo de la FRECUENCIA → realza percusivas (verticales);
    - máscaras de Wiener → energía armónica vs percusiva.

    índice = energía_armónica / (energía_armónica + energía_percusiva).
    No es confiable en segmentos < ~0.3 s (pocos frames), igual que en el
    informe (§4.3) — esa guarda la aplica la clasificación gruesa, no esta
    función.
    """
    if len(segmento) < 256:
        return 0.0
    # El hop se adapta a la duración: el filtro de mediana temporal necesita
    # más frames que su kernel (31). Con hop fijo, un segmento corto queda con
    # menos frames que el kernel y el índice colapsa a ~0.5 sin importar el
    # contenido. Se apunta a ≥ 48 frames (hop entre 64 y 512 muestras).
    hop = max(64, min(HPSS_HOP, len(segmento) // 48))
    nperseg = min(HPSS_NPERSEG, 4 * hop, len(segmento))
    _, _, Z = stft(segmento, fs=sr, nperseg=nperseg, noverlap=nperseg - hop, padded=True)
    S = np.abs(Z)
    if S.shape[1] < 3:
        return 0.0
    k_t = min(HPSS_KERNEL, S.shape[1])
    k_f = min(HPSS_KERNEL, S.shape[0])
    armonica = median_filter(S, size=(1, k_t))
    percusiva = median_filter(S, size=(k_f, 1))
    a2, p2 = armonica**2, percusiva**2
    mascara_a = a2 / (a2 + p2 + 1e-12)
    potencia = S**2
    e_armonica = float(np.sum(potencia * mascara_a))
    e_percusiva = float(np.sum(potencia * (1.0 - mascara_a)))
    return e_armonica / (e_armonica + e_percusiva + 1e-12)


def impulsividad(segmento: np.ndarray, sr: int) -> tuple[float, float]:
    """(factor de cresta, concentración de energía) sobre la envolvente de
    Hilbert (§4.6): pico/RMS y fracción de la energía en ±5 ms del pico."""
    if len(segmento) == 0:
        return 0.0, 0.0
    envolvente = np.abs(hilbert(segmento))
    pico = int(np.argmax(envolvente))
    rms = float(np.sqrt(np.mean(segmento.astype(np.float64) ** 2)))
    cresta = float(envolvente[pico]) / (rms + 1e-12)
    ventana = int(0.005 * sr)  # ±5 ms
    lo, hi = max(0, pico - ventana), min(len(envolvente), pico + ventana)
    concentracion = float(np.sum(envolvente[lo:hi] ** 2) / (np.sum(envolvente**2) + 1e-12))
    return cresta, concentracion


def frecuencia_pico(segmento: np.ndarray, sr: int) -> float:
    """Frecuencia del pico del espectro (FFT con ventana Hann)."""
    if len(segmento) < 8:
        return 0.0
    espectro = np.abs(np.fft.rfft(segmento * np.hanning(len(segmento))))
    freqs = np.fft.rfftfreq(len(segmento), 1.0 / sr)
    return float(freqs[int(np.argmax(espectro))])


def espectrograma_archivo(y: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Un espectrograma del archivo COMPLETO (hop sin solapamiento, float32)
    para el chequeo de prominencia espectral (§4.7). Se calcula una vez por
    archivo, no por evento."""
    freqs, tiempos, Z = stft(
        y, fs=sr, nperseg=PROMINENCIA_NPERSEG, noverlap=0, padded=False
    )
    Sxx_db = (20.0 * np.log10(np.abs(Z) + 1e-12)).astype(np.float32)
    return freqs, tiempos, Sxx_db


def prominencia_espectral(
    contexto: tuple[np.ndarray, np.ndarray, np.ndarray],
    inicio_s: float,
    fin_s: float,
    freq_pico: float,
) -> float:
    """Cuánto se destaca (dB) la frecuencia pico del evento contra esa MISMA
    frecuencia en el resto del archivo. Un tono de fondo constante no se
    destaca de sí mismo → prominencia baja = ruido continuo (§4.7).

    Dentro del evento se usa el percentil 95 (máximo robusto) en vez de la
    mediana del informe: un llamado con barrido (up_call, 80→250 Hz) ocupa su
    bin pico solo una fracción de los frames del evento, y la mediana lo
    castigaba como si fuera fondo. Afuera del evento la mediana queda igual.
    """
    freqs, tiempos, Sxx_db = contexto
    bin_idx = int(np.argmin(np.abs(freqs - freq_pico)))
    serie = Sxx_db[bin_idx, :]
    mascara = (tiempos >= inicio_s) & (tiempos <= fin_s)
    if not mascara.any() or mascara.all():
        return 0.0
    return float(np.percentile(serie[mascara], 95) - np.median(serie[~mascara]))


# ---------- clasificación gruesa ----------


def clasificar_grueso(d: Deteccion, params: dict) -> str:
    """Aplica los umbrales de la calibración vigente. Devuelve la clase gruesa."""
    for lo, hi in params.get("bandas_excluidas_hz", []):
        if lo <= d.frecuencia_pico_hz <= hi:
            return "ruido"

    es_impulsivo = (
        d.indice_armonico < params["gunshot_armonico_max"]
        and params["gunshot_dur_min_s"] <= d.duracion_nucleo_s <= params["gunshot_dur_max_s"]
        and d.factor_cresta >= params["cresta_min"]
        and d.concentracion_energia >= params["concentracion_min"]
    )
    if es_impulsivo:
        return "impulsivo_candidato"

    es_tonal = (
        d.indice_armonico >= params["armonico_min"]
        and d.duracion_s >= params["armonico_confiable_dur_min_s"]
        and d.duracion_s <= params["tonal_dur_max_s"]
        and d.prominencia_db >= params["prominencia_min_db"]
    )
    if es_tonal:
        return "tonal_candidato"
    return "ruido"


# ---------- pipeline ----------


def detectar_en_senal(y: np.ndarray, sr: int, params: dict) -> list[Deteccion]:
    """Pipeline completo sobre una señal ya en memoria (mono float)."""
    # El piso de duración del VAD no puede filtrar gunshots que la propia
    # calibración permite (0.08 s < 0.15 s): se usa el mínimo de ambos.
    dur_min = min(params["dur_min_s"], params["gunshot_dur_min_s"])
    eventos = vad_energia(
        y,
        sr,
        percentil=params["vad_percentil"],
        fusion_s=params["vad_fusion_s"],
        dur_min_s=dur_min,
        dur_max_s=params["dur_max_s"],
        piso_sobre_mediana_db=params.get("vad_piso_sobre_mediana_db", 3.0),
    )
    if not eventos:
        return []
    contexto = espectrograma_archivo(y, sr)

    detecciones = []
    for inicio_s, fin_s, nucleo_s in eventos:
        seg = y[int(inicio_s * sr) : int(fin_s * sr)]
        cresta, concentracion = impulsividad(seg, sr)
        f_pico = frecuencia_pico(seg, sr)
        d = Deteccion(
            inicio_s=round(inicio_s, 3),
            fin_s=round(fin_s, 3),
            duracion_s=round(fin_s - inicio_s, 3),
            duracion_nucleo_s=round(nucleo_s, 3),
            clase="ruido",
            indice_armonico=round(indice_armonico(seg, sr), 4),
            factor_cresta=round(cresta, 2),
            concentracion_energia=round(concentracion, 4),
            prominencia_db=round(prominencia_espectral(contexto, inicio_s, fin_s, f_pico), 2),
            frecuencia_pico_hz=round(f_pico, 1),
        )
        d.clase = clasificar_grueso(d, params)
        detecciones.append(d)
    return detecciones


def detectar_archivo(
    ruta_wav: Path | str, params: dict
) -> tuple[list[Deteccion], int]:
    """Lee el WAV y corre el pipeline. Devuelve (detecciones, sample_rate)."""
    y, sr = leer_wav_mono(ruta_wav)
    return detectar_en_senal(y, sr, params), sr


# ---------- CLI ----------


def main(argv: list[str]) -> int:
    if len(argv) < 2 or "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    ruta = Path(argv[1])
    sitio = argv[argv.index("--sitio") + 1] if "--sitio" in argv else "global"
    ruta_db = Path(argv[argv.index("--db") + 1]) if "--db" in argv else base.RUTA_DB

    con = base.conectar(ruta_db)
    try:
        version, params = base.calibracion_vigente(con, sitio)
    finally:
        con.close()

    print(f"Detectando en {ruta.name} con calibración v{version} (sitio {sitio!r})…")
    detecciones, sr = detectar_archivo(ruta, params)
    conteos = {clase: 0 for clase in CLASES_GRUESAS}
    for d in detecciones:
        conteos[d.clase] += 1
        if d.clase != "ruido":
            print(
                f"  {d.inicio_s:8.2f}s  {d.clase:20s} dur {d.duracion_s:5.2f}s  "
                f"armónico {d.indice_armonico:.2f}  cresta {d.factor_cresta:5.1f}  "
                f"pico {d.frecuencia_pico_hz:7.1f} Hz  prom {d.prominencia_db:+.1f} dB"
            )
    print(
        f"Listo ({sr} Hz): {len(detecciones)} eventos — "
        f"{conteos['tonal_candidato']} tonales candidatos, "
        f"{conteos['impulsivo_candidato']} impulsivos candidatos, "
        f"{conteos['ruido']} ruido."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
