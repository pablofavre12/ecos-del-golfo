"""Ingesta de campañas nuevas (R17): un WAV crudo entra solo al pipeline.

    python ingerir.py <archivo.wav> [--fuente nombre] [--sitio global] [--db ruta]

Pipeline:
1. Chequeos de calidad R17: legible, no vacío/truncado, sample rate y duración
   sanos, advertencia de reloj si la fecha del nombre de archivo es sospechosa.
   Reporta claro, sin stack traces (estilo importar.py).
2. Detección con detectar.py y la CALIBRACIÓN VIGENTE (tabla `calibracion`).
3. DEDUPE contra el catálogo: toda detección que solape temporalmente (±1 s)
   con un segmento existente del mismo `recording_source` se descarta — al
   re-ingerir la grabación de la que salió el catálogo, solo entran los
   sonidos que la sesión exploratoria se perdió. El dedupe también hace la
   ingesta idempotente: re-correr no duplica nada.
4. Por cada detección nueva: recorte del clip WAV (sample rate nativo) +
   espectrograma a `datos/<fuente>/` (gitignoreada), embedding (el mismo
   embedder del índice), clasificación (modelo softmax vigente, fallback
   vecinos k-NN) → alta en `segmento` como `propuesto` con
   `tipo_propuesto_por` + `confianza` → a la cola de revisión.
5. Resumen: detectados / dedupeados / a la cola / distribución de tipos.
"""

from __future__ import annotations

import re
import sys
import wave
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

import base
import clasificar
import detectar
import embeddings
from generar_fixtures import escribir_espectrograma

RAIZ_DATOS = Path(__file__).parent / "datos"
TOLERANCIA_DEDUPE_S = 1.0
PAD_CLIP_S = 0.2  # aire antes/después del evento en el clip recortado
SR_MIN, SR_MAX = 8000, 192000
DURACION_MINIMA_S = 1.0

# La clase 'descarte' del clasificador no es un tipo del catálogo: se propone
# como posible_ruido_agua (categoría de descarte que la cola ya conoce) y el
# experto decide.
MAPA_TIPO = {clasificar.CLASE_DESCARTE: "posible_ruido_agua"}

# Nomenclaturas de grabadores conocidas → fecha/hora de inicio de grabación.
PATRONES_FECHA = (
    (re.compile(r"^(\d{8})_(\d{6})"), "%Y%m%d%H%M%S"),  # AudioMoth: 20251010_090000
    (re.compile(r"^(\d{6})-(\d{6})"), "%y%m%d%H%M%S"),  # Zoom H1n: 260803-173856
)


def fecha_de_filename(nombre: str) -> datetime | None:
    for patron, formato in PATRONES_FECHA:
        m = patron.match(nombre)
        if m:
            try:
                return datetime.strptime(m.group(1) + m.group(2), formato)
            except ValueError:
                return None
    return None


def chequear_calidad(ruta: Path) -> tuple[list[str], list[str], dict]:
    """R17: (errores fatales, advertencias, info del archivo)."""
    errores: list[str] = []
    advertencias: list[str] = []
    info: dict = {}

    if not ruta.exists():
        return [f"el archivo no existe: {ruta}"], [], {}
    if ruta.stat().st_size <= 44:  # una cabecera WAV pelada
        return [f"archivo vacío o truncado ({ruta.stat().st_size} bytes)"], [], {}

    try:
        with wave.open(str(ruta), "rb") as w:
            info["sr"] = w.getframerate()
            info["canales"] = w.getnchannels()
            info["bits"] = w.getsampwidth() * 8
            info["frames"] = w.getnframes()
    except (wave.Error, EOFError) as err:
        return [f"no se puede leer como WAV: {err}"], [], {}

    if info["frames"] == 0:
        errores.append("el WAV no tiene frames (grabación vacía, ¿falla de tarjeta?)")
    else:
        info["duracion_s"] = info["frames"] / info["sr"]
        if info["duracion_s"] < DURACION_MINIMA_S:
            errores.append(f"duración {info['duracion_s']:.2f} s — demasiado corto para una campaña")
    if not SR_MIN <= info["sr"] <= SR_MAX:
        errores.append(f"sample rate {info['sr']} Hz fuera del rango sano ({SR_MIN}-{SR_MAX})")
    if info["bits"] != 16:
        errores.append(f"solo se soporta PCM 16-bit (este es de {info['bits']} bits)")

    fecha = fecha_de_filename(ruta.name)
    info["inicio"] = fecha
    if fecha is None:
        advertencias.append(
            "no se pudo leer fecha/hora del nombre de archivo (ni AudioMoth ni Zoom): "
            "los segmentos quedarán sin fecha/hora absoluta"
        )
    elif fecha > datetime.now():
        advertencias.append(
            f"reloj sospechoso: el nombre dice {fecha:%Y-%m-%d %H:%M} (futuro) — "
            "¿reloj del grabador mal configurado?"
        )
    return errores, advertencias, info


def intervalos_existentes(con, fuente: str) -> list[tuple[float, float]]:
    """[(inicio_s, fin_s)] de los segmentos ya catalogados de esta fuente.
    El fin se estima con la duración del clip en disco (fallback: 1 s)."""
    filas = con.execute(
        "SELECT offset_s, clip_path FROM segmento WHERE fuente = ? AND offset_s IS NOT NULL",
        (fuente,),
    ).fetchall()
    intervalos = []
    for fila in filas:
        duracion = 1.0
        if fila["clip_path"]:
            try:
                with wave.open(fila["clip_path"], "rb") as w:
                    duracion = w.getnframes() / w.getframerate()
            except (OSError, wave.Error, EOFError, ZeroDivisionError):
                pass
        intervalos.append((float(fila["offset_s"]), float(fila["offset_s"]) + duracion))
    return intervalos


def solapa(inicio: float, fin: float, intervalos: list[tuple[float, float]]) -> bool:
    """¿[inicio, fin] solapa (con tolerancia ±1 s) algún intervalo existente?"""
    return any(
        inicio < b + TOLERANCIA_DEDUPE_S and fin > a - TOLERANCIA_DEDUPE_S
        for a, b in intervalos
    )


def escribir_clip(ruta: Path, y: np.ndarray, sr: int) -> None:
    """Clip mono int16 al sample rate NATIVO de la grabación."""
    datos = (np.clip(y, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(datos.tobytes())


def embedder_del_indice(con) -> embeddings.Embedder:
    """El mismo embedder con el que está indexado el catálogo (los vectores
    nuevos tienen que vivir en el mismo espacio). Sin índice: espectral."""
    fila = con.execute("SELECT DISTINCT embedder FROM embedding").fetchall()
    nombres = [f["embedder"] for f in fila]
    if len(nombres) > 1:
        raise SystemExit(f"El índice mezcla embedders ({nombres}): re-indexar primero.")
    por_nombre = {cls.nombre: cls for cls in embeddings.EMBEDDERS.values()}
    if nombres and nombres[0] in por_nombre:
        return por_nombre[nombres[0]]()
    return embeddings.EmbedderEspectral()


def ingerir(
    ruta_wav: Path | str,
    fuente: str | None = None,
    sitio: str = "global",
    ruta_db: Path | str = base.RUTA_DB,
    raiz_datos: Path | None = None,
) -> dict:
    """Pipeline completo. Devuelve el resumen (conteos y distribución)."""
    ruta = Path(ruta_wav)
    fuente = fuente or ruta.name
    raiz = raiz_datos or RAIZ_DATOS

    # 1. calidad
    errores, advertencias, info = chequear_calidad(ruta)
    for a in advertencias:
        print(f"  ⚠ {a}")
    if errores:
        print(f"El archivo {ruta.name} no pasa los chequeos de calidad:")
        for e in errores:
            print(f"  ✗ {e}")
        return {"ok": False, "errores": errores}
    print(
        f"  ✓ {ruta.name}: {info['duracion_s'] / 60:.1f} min, {info['sr']} Hz, "
        f"{info['canales']} canal(es), {info['bits']}-bit"
    )

    con = base.conectar(ruta_db)
    try:
        version_cal, params = base.calibracion_vigente(con, sitio)

        # inicio de grabación: del nombre de archivo, o del catálogo existente
        inicio = info.get("inicio")
        if inicio is None:
            fila = con.execute(
                "SELECT inicio_grabacion FROM segmento WHERE fuente = ? "
                "AND inicio_grabacion IS NOT NULL LIMIT 1",
                (fuente,),
            ).fetchone()
            if fila:
                inicio = datetime.fromisoformat(fila["inicio_grabacion"])

        # 2. detección
        print(f"  Detectando con calibración v{version_cal} (sitio {sitio!r})…")
        y, sr = detectar.leer_wav_mono(ruta)
        detecciones = detectar.detectar_en_senal(y, sr, params)
        candidatas = [d for d in detecciones if d.clase != "ruido"]
        print(
            f"  {len(detecciones)} eventos crudos → {len(candidatas)} candidatos "
            f"({sum(1 for d in candidatas if d.clase == 'tonal_candidato')} tonales, "
            f"{sum(1 for d in candidatas if d.clase == 'impulsivo_candidato')} impulsivos)"
        )

        # 3. dedupe contra el catálogo
        existentes = intervalos_existentes(con, fuente)
        nuevas = [d for d in candidatas if not solapa(d.inicio_s, d.fin_s, existentes)]
        dedupeadas = len(candidatas) - len(nuevas)
        print(f"  Dedupe contra {len(existentes)} segmentos de {fuente!r}: {dedupeadas} ya catalogados")

        # 4. alta de los nuevos
        carpeta = raiz / fuente
        clips = carpeta / "clips"
        espectros = carpeta / "espectrogramas"
        embedder = embedder_del_indice(con) if nuevas else None
        if nuevas:
            clips.mkdir(parents=True, exist_ok=True)
            espectros.mkdir(parents=True, exist_ok=True)

        ingresados: list[dict] = []
        for d in nuevas:
            momento = inicio + timedelta(seconds=d.inicio_s) if inicio else None

            desde = max(0, int((d.inicio_s - PAD_CLIP_S) * sr))
            hasta = min(len(y), int((d.fin_s + PAD_CLIP_S) * sr))
            clip = y[desde:hasta]

            vector = None
            resultado = None
            tipo = "no_clasificado"
            # nomenclatura de §5.3: {YYYY-MM-DD}_{HHhMMmSSs}_{tipo}.wav
            base_nombre = (
                f"{momento:%Y-%m-%d}_{momento:%Hh%Mm%Ss}"
                if momento
                else f"{ruta.stem}_{d.inicio_s:08.2f}s"
            )

            # clasificación primero (el tipo viaja en el nombre del clip)
            ruta_tmp = clips / f"{base_nombre}_tmp.wav"
            escribir_clip(ruta_tmp, clip, sr)
            try:
                vector = embedder.embed(ruta_tmp)
                resultado = clasificar.clasificar(con, vector, embedder.nombre)
            except Exception as err:  # un clip roto no frena la campaña
                print(f"  ⚠ no se pudo clasificar el evento en {d.inicio_s:.1f}s: {err}")
            finally:
                ruta_tmp.unlink(missing_ok=True)
            if resultado:
                tipo = MAPA_TIPO.get(resultado["tipo"], resultado["tipo"])

            filename = f"{base_nombre}_{tipo}.wav"
            n_copia = 2
            while con.execute(
                "SELECT 1 FROM segmento WHERE filename = ?", (filename,)
            ).fetchone():
                filename = f"{base_nombre}-{n_copia}_{tipo}.wav"
                n_copia += 1

            ruta_clip = clips / filename
            ruta_espectro = espectros / (ruta_clip.stem + ".png")
            escribir_clip(ruta_clip, clip, sr)
            escribir_espectrograma(ruta_clip, ruta_espectro)

            con.execute(
                """
                INSERT INTO segmento (filename, tipo, fuente, inicio_grabacion,
                    offset_s, fecha_hora_absoluta, estado, clip_path,
                    espectrograma_path, tipo_propuesto_por, confianza)
                VALUES (?, ?, ?, ?, ?, ?, 'propuesto', ?, ?, ?, ?)
                """,
                (
                    filename,
                    tipo,
                    fuente,
                    inicio.isoformat(timespec="seconds") if inicio else None,
                    round(d.inicio_s, 2),
                    momento.isoformat(timespec="seconds") if momento else None,
                    str(ruta_clip),
                    str(ruta_espectro),
                    resultado["motor"] if resultado else "detector",
                    resultado["confianza"] if resultado else None,
                ),
            )
            if vector is not None:
                con.execute(
                    """
                    INSERT INTO embedding (filename, embedder, dimension, vector)
                    VALUES (?, ?, ?, ?)
                    """,
                    (filename, embedder.nombre, len(vector), embeddings.vector_a_blob(vector)),
                )
            con.commit()
            ingresados.append({"filename": filename, "tipo": tipo, "deteccion": d, "resultado": resultado})
            confianza = f"{resultado['confianza']:.0%} ({resultado['motor']})" if resultado else "sin clasificar"
            print(f"    + {d.inicio_s:8.2f}s  {tipo:20s} {confianza}")
    finally:
        con.close()

    # 5. resumen
    distribucion: dict[str, list[float]] = {}
    for item in ingresados:
        distribucion.setdefault(item["tipo"], []).append(
            item["resultado"]["confianza"] if item["resultado"] else 0.0
        )
    print("\nResumen de la ingesta:")
    print(f"  eventos crudos detectados : {len(detecciones)}")
    print(f"  candidatos (no ruido)     : {len(candidatas)}")
    print(f"  dedupeados (ya en catálogo): {dedupeadas}")
    print(f"  nuevos a la cola          : {len(ingresados)}")
    for tipo, confianzas in sorted(distribucion.items()):
        media = sum(confianzas) / len(confianzas)
        print(f"    {tipo:20s} {len(confianzas):3d}  confianza media {media:.0%}")
    return {
        "ok": True,
        "detectados": len(detecciones),
        "candidatos": len(candidatas),
        "dedupeados": dedupeadas,
        "ingresados": len(ingresados),
        "distribucion": {t: len(c) for t, c in distribucion.items()},
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2 or "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    ruta = Path(argv[1])
    fuente = argv[argv.index("--fuente") + 1] if "--fuente" in argv else None
    sitio = argv[argv.index("--sitio") + 1] if "--sitio" in argv else "global"
    ruta_db = Path(argv[argv.index("--db") + 1]) if "--db" in argv else base.RUTA_DB

    resumen = ingerir(ruta, fuente, sitio, ruta_db)
    return 0 if resumen.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
