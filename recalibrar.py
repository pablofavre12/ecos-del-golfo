"""Recalibra los umbrales del detector desde los veredictos reales (R12).

El loop de mejora continua: cada veredicto del experto (confirmar / descartar)
es un dato de calibración. Este script mide las features de detectar.py sobre
los clips CONFIRMADOS y DESCARTADOS de la DB y deriva umbrales nuevos:

- armonico_min           ← percentil 5 del índice armónico de los tonales
                           confirmados (con duración ≥ 0.3 s, donde HPSS es
                           confiable)
- tonal_dur_max_s        ← duración máxima observada en tonales confirmados
                           + 15 % de margen
- gunshot_armonico_max   ← percentil 95 del índice armónico de los gunshot
                           confirmados
- cresta_min             ← percentil 5 del factor de cresta de los gunshot
- concentracion_min      ← percentil 5 de la concentración de energía
- gunshot_dur_min/max_s  ← rango de duración observado en gunshot ∓ 15 %

Cada parámetro se recalcula SOLO si hay al menos MIN_MUESTRAS ejemplos de la
clase que lo calibra; si no, mantiene el valor vigente y lo dice. El resultado
es SIEMPRE una versión nueva en la tabla `calibracion` (nunca pisa la
anterior), con el reporte de qué cambió y por qué.

Los umbrales del VAD y la prominencia espectral no se recalculan acá: no son
derivables de clips sueltos (necesitan el archivo completo).

Uso: python recalibrar.py [--sitio global] [--db ruta/ecos.db] [--nota texto]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

import base
import detectar

MIN_MUESTRAS = 5
TIPOS_TONALES = ("up_call", "high_call", "pulsive_call", "no_clasificado")


def duracion_nucleo_clip(y: np.ndarray, sr: int) -> float:
    """Duración del SONIDO dentro del clip, no del archivo: los clips del
    catálogo traen aire alrededor del evento (un gunshot de 0.2 s vive en un
    clip de 1.4 s). Análoga a la duración de núcleo del detector: lapso de los
    frames con RMS ≥ fondo del clip (percentil 10) + margen de 6 dB."""
    hop = max(1, int(round(sr * detectar.VAD_HOP_S)))
    n_hops = len(y) // hop
    if n_hops == 0:
        return len(y) / sr
    energia = (y[: n_hops * hop].astype(np.float32) ** 2).reshape(n_hops, hop).mean(axis=1)
    rms_db = 10.0 * np.log10(energia + 1e-12)
    piso = float(np.percentile(rms_db, 10))
    fuerte = np.flatnonzero(rms_db >= piso + detectar.MARGEN_NUCLEO_DB)
    if len(fuerte) == 0:
        return n_hops * hop / sr
    return float(fuerte[-1] - fuerte[0] + 1) * hop / sr


def medir_clips(con) -> dict[str, list[dict]]:
    """Features de detectar.py sobre cada clip con veredicto (confirmado o
    descartado). Agrupa: 'tonal', 'gunshot', 'descartado'."""
    filas = con.execute(
        """
        SELECT filename, COALESCE(tipo_corregido, tipo) AS tipo_efectivo,
               estado, clip_path
        FROM segmento
        WHERE estado IN ('confirmado', 'descartado') AND clip_path IS NOT NULL
        ORDER BY filename
        """
    ).fetchall()

    grupos: dict[str, list[dict]] = {"tonal": [], "gunshot": [], "descartado": []}
    sin_clip = 0
    for fila in filas:
        ruta = Path(fila["clip_path"])
        if not ruta.exists():
            sin_clip += 1
            continue
        y, sr = detectar.leer_wav_mono(ruta)
        if len(y) == 0:
            sin_clip += 1
            continue
        cresta, concentracion = detectar.impulsividad(y, sr)
        medida = {
            "filename": fila["filename"],
            "duracion_s": len(y) / sr,  # del archivo (para el filtro de HPSS confiable)
            "duracion_nucleo_s": duracion_nucleo_clip(y, sr),  # del sonido en sí
            "indice_armonico": detectar.indice_armonico(y, sr),
            "factor_cresta": cresta,
            "concentracion_energia": concentracion,
        }
        if fila["estado"] == "descartado":
            grupos["descartado"].append(medida)
        elif fila["tipo_efectivo"] == "gunshot_call":
            grupos["gunshot"].append(medida)
        elif fila["tipo_efectivo"] in TIPOS_TONALES:
            grupos["tonal"].append(medida)
    if sin_clip:
        print(f"  ⚠ {sin_clip} segmentos con veredicto sin clip en disco (no se usan)")
    return grupos


def _columna(grupo: list[dict], clave: str) -> np.ndarray:
    return np.array([m[clave] for m in grupo])


def derivar_parametros(
    vigentes: dict, grupos: dict[str, list[dict]]
) -> tuple[dict, list[str]]:
    """(parametros nuevos, reporte línea por línea). Mantiene el valor vigente
    para todo parámetro cuya clase de calibración tenga pocos ejemplos."""
    nuevos = dict(vigentes)
    reporte: list[str] = []

    def fijar(clave: str, valor: float, motivo: str) -> None:
        viejo = vigentes[clave]
        valor = round(float(valor), 4)
        if abs(valor - viejo) < 1e-9:
            reporte.append(f"  = {clave}: {viejo} (sin cambio — {motivo})")
        else:
            reporte.append(f"  → {clave}: {viejo} → {valor} ({motivo})")
        nuevos[clave] = valor

    def mantener(clave: str, clase: str, n: int) -> None:
        reporte.append(
            f"  · {clave}: se mantiene {vigentes[clave]} — solo {n} ejemplos "
            f"de {clase} (mínimo {MIN_MUESTRAS})"
        )

    # --- tonales confirmados ---
    tonales = grupos["tonal"]
    confiables = [
        m
        for m in tonales
        if m["duracion_s"] >= vigentes["armonico_confiable_dur_min_s"]
    ]
    if len(confiables) >= MIN_MUESTRAS:
        armonicos = _columna(confiables, "indice_armonico")
        fijar(
            "armonico_min",
            np.percentile(armonicos, 5),
            f"percentil 5 del índice armónico de {len(confiables)} tonales confirmados",
        )
        duraciones = _columna(tonales, "duracion_nucleo_s")
        fijar(
            "tonal_dur_max_s",
            duraciones.max() * 1.15,
            f"duración de núcleo máxima observada ({duraciones.max():.2f} s) + 15 %",
        )
    else:
        mantener("armonico_min", "tonales confirmados (dur ≥ 0.3 s)", len(confiables))
        mantener("tonal_dur_max_s", "tonales confirmados", len(tonales))

    # --- gunshot confirmados ---
    gunshots = grupos["gunshot"]
    if len(gunshots) >= MIN_MUESTRAS:
        n = len(gunshots)
        fijar(
            "gunshot_armonico_max",
            np.percentile(_columna(gunshots, "indice_armonico"), 95),
            f"percentil 95 del índice armónico de {n} gunshot confirmados",
        )
        fijar(
            "cresta_min",
            np.percentile(_columna(gunshots, "factor_cresta"), 5),
            f"percentil 5 del factor de cresta de {n} gunshot confirmados",
        )
        fijar(
            "concentracion_min",
            np.percentile(_columna(gunshots, "concentracion_energia"), 5),
            f"percentil 5 de la concentración de energía de {n} gunshot",
        )
        reporte.append(
            "  · gunshot_dur_min_s / gunshot_dur_max_s: se mantienen — la duración "
            "de un impulso no es medible desde el clip recortado (el ring-down "
            "queda sobre el piso del clip ~1 s; la ventana del informe se midió "
            "contra el umbral VAD del archivo completo)"
        )
    else:
        for clave in ("gunshot_armonico_max", "cresta_min", "concentracion_min"):
            mantener(clave, "gunshot confirmados", len(gunshots))

    # --- descartados: control de separación (no fija umbrales, avisa) ---
    descartados = grupos["descartado"]
    if descartados:
        armonicos = _columna(descartados, "indice_armonico")
        solapados = int(np.count_nonzero(armonicos >= nuevos["armonico_min"]))
        if solapados:
            reporte.append(
                f"  ⚠ {solapados} de {len(descartados)} descartados quedan POR ENCIMA "
                f"de armonico_min={nuevos['armonico_min']} — el índice armónico solo "
                "no los separa (esperable: se descartaron por otros criterios)"
            )
    return nuevos, reporte


def recalibrar(
    ruta_db: Path | str = base.RUTA_DB,
    sitio: str = "global",
    nota: str | None = None,
) -> tuple[int, dict, list[str]]:
    """Corre el loop completo. Devuelve (version_nueva, parametros, reporte)."""
    con = base.conectar(ruta_db)
    try:
        version_vigente, vigentes = base.calibracion_vigente(con, sitio)
        print(f"Midiendo clips con veredicto (calibración vigente: v{version_vigente})…")
        grupos = medir_clips(con)
        n_confirmados = len(grupos["tonal"]) + len(grupos["gunshot"])
        n_descartados = len(grupos["descartado"])
        print(
            f"  {len(grupos['tonal'])} tonales + {len(grupos['gunshot'])} gunshot "
            f"confirmados · {n_descartados} descartados"
        )
        nuevos, reporte = derivar_parametros(vigentes, grupos)

        version_nueva = (
            con.execute(
                "SELECT COALESCE(MAX(version), 0) FROM calibracion WHERE sitio = ?",
                (sitio,),
            ).fetchone()[0]
            + 1
        )
        con.execute(
            """
            INSERT INTO calibracion (sitio, version, parametros, n_confirmados,
                                     n_descartados, nota)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                sitio,
                version_nueva,
                json.dumps(nuevos),
                n_confirmados,
                n_descartados,
                nota
                or f"recalibración automática desde {n_confirmados} confirmados "
                f"y {n_descartados} descartados",
            ),
        )
        con.commit()
    finally:
        con.close()
    return version_nueva, nuevos, reporte


def main(argv: list[str]) -> int:
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    sitio = argv[argv.index("--sitio") + 1] if "--sitio" in argv else "global"
    ruta_db = Path(argv[argv.index("--db") + 1]) if "--db" in argv else base.RUTA_DB
    nota = argv[argv.index("--nota") + 1] if "--nota" in argv else None

    version, _, reporte = recalibrar(ruta_db, sitio, nota)
    print(f"\nCalibración v{version} (sitio {sitio!r}) creada — la anterior queda en el historial:")
    for linea in reporte:
        print(linea)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
