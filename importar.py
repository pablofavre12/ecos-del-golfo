"""Importa una carpeta de datos (catalogo.csv + candidatos.csv + clips +
espectrogramas) a SQLite (ecos.db), la única fuente de verdad (D10).

Tolerante a esquema: valida las columnas contra el esquema esperado, mapea lo
que puede y reporta las diferencias (columnas faltantes/extra, filas inválidas,
clips referenciados que no existen) en un resumen claro — nunca un stack trace
pelado. Idempotente: re-correr no duplica (upsert por filename), y no pisa un
veredicto ya asentado por el revisor.

Uso: python importar.py <carpeta> [--db ruta/ecos.db]
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

import base

COLUMNAS_ESPERADAS = [
    "filename",
    "type",
    "recording_source",
    "recording_start",
    "offset_in_recording_s",
    "absolute_datetime",
    "status",
]

# Sinónimos que sabemos mapear si el CSV viene con otros nombres.
SINONIMOS = {
    "file": "filename",
    "archivo": "filename",
    "tipo": "type",
    "fuente": "recording_source",
    "source": "recording_source",
    "estado": "status",
    "offset_s": "offset_in_recording_s",
    "datetime": "absolute_datetime",
    "fecha_hora": "absolute_datetime",
}

ESTADOS_VALIDOS = set(base.ESTADOS)


@dataclass
class ReporteArchivo:
    nombre: str
    presentes: int = 0
    insertadas: int = 0
    actualizadas: int = 0
    columnas_faltantes: list = field(default_factory=list)
    columnas_extra: list = field(default_factory=list)
    columnas_mapeadas: dict = field(default_factory=dict)
    filas_invalidas: list = field(default_factory=list)  # (nro_fila, motivo)


@dataclass
class Reporte:
    carpeta: Path
    archivos: list = field(default_factory=list)
    clips_faltantes: list = field(default_factory=list)
    espectrogramas_faltantes: list = field(default_factory=list)
    errores: list = field(default_factory=list)

    @property
    def total_cargadas(self) -> int:
        return sum(a.insertadas + a.actualizadas for a in self.archivos)


def _resolver_columnas(cabecera: list[str], reporte: ReporteArchivo) -> dict[str, str]:
    """Mapea columna del CSV → columna esperada; anota lo que no matchea."""
    mapa = {}
    for col in cabecera:
        limpia = col.strip().lower()
        if limpia in COLUMNAS_ESPERADAS:
            mapa[col] = limpia
        elif limpia in SINONIMOS:
            mapa[col] = SINONIMOS[limpia]
            reporte.columnas_mapeadas[col] = SINONIMOS[limpia]
        elif limpia == "confirmed_by_ear":
            mapa[col] = "confirmed_by_ear"  # propia de candidatos.csv
        else:
            reporte.columnas_extra.append(col)
    resueltas = set(mapa.values())
    reporte.columnas_faltantes = [
        c for c in COLUMNAS_ESPERADAS if c not in resueltas and c != "status"
    ]
    if "status" not in resueltas and "confirmed_by_ear" not in resueltas:
        reporte.columnas_faltantes.append("status")
    return mapa


# Vocabulario de estados de los CSV reales de la sesión exploratoria
# (ajuste mínimo del gate WCH-467: mapear, no rechazar).
SINONIMOS_ESTADO = {
    "clasificado": "confirmado",
    "pendiente_revision": "propuesto",
    "pendiente": "propuesto",
}


def _normalizar_estado(crudo: str) -> str | None:
    """Mapea el status del CSV al vocabulario del catálogo; None si no se reconoce."""
    valor = (crudo or "").strip().lower()
    if valor in ESTADOS_VALIDOS:
        return valor
    if valor in SINONIMOS_ESTADO:
        return SINONIMOS_ESTADO[valor]
    if valor.startswith("descartado"):  # ej. "descartado_no_tonal_no_impulsivo"
        return "descartado"
    return None


def _normalizar_tipo(crudo: str) -> str:
    """'pulsive_call (dudoso, muy corto)' → 'pulsive_call' (la nota no es el tipo)."""
    return (crudo or "").split(" (")[0].split("(")[0].strip()


def _importar_csv(con, ruta_csv: Path, carpeta: Path, reporte: Reporte, es_candidatos: bool):
    rep = ReporteArchivo(nombre=ruta_csv.name)
    reporte.archivos.append(rep)

    try:
        with open(ruta_csv, newline="") as f:
            lector = csv.DictReader(f)
            if not lector.fieldnames:
                reporte.errores.append(f"{ruta_csv.name}: archivo vacío o sin cabecera")
                return
            mapa = _resolver_columnas(lector.fieldnames, rep)
            filas = list(lector)
    except OSError as e:
        reporte.errores.append(f"{ruta_csv.name}: no se pudo leer ({e})")
        return

    if "filename" not in mapa.values() or "type" not in mapa.values():
        reporte.errores.append(
            f"{ruta_csv.name}: sin columnas reconocibles de filename/type — no se importó nada"
        )
        return

    clips = carpeta / "clips"
    espectros = carpeta / "espectrogramas"

    for nro, cruda in enumerate(filas, start=2):  # 2 = primera fila de datos
        rep.presentes += 1
        fila = {destino: (cruda.get(orig) or "").strip() for orig, destino in mapa.items()}

        if not fila.get("filename"):
            rep.filas_invalidas.append((nro, "sin filename"))
            continue
        if not fila.get("type"):
            rep.filas_invalidas.append((nro, "sin type"))
            continue

        fila["type"] = _normalizar_tipo(fila["type"])

        if es_candidatos:
            # Candidato sin veredicto de escucha → entra como propuesto.
            oido = fila.get("confirmed_by_ear", "")
            estado = "confirmado" if oido.lower() in ("si", "sí", "yes", "true", "1") else "propuesto"
        else:
            estado = _normalizar_estado(fila.get("status", "")) or (
                "propuesto" if not fila.get("status") else None
            )
            if estado is None:
                rep.filas_invalidas.append(
                    (nro, f"status desconocido: {fila.get('status')!r}")
                )
                continue

        try:
            offset = float(fila["offset_in_recording_s"]) if fila.get("offset_in_recording_s") else None
        except ValueError:
            rep.filas_invalidas.append((nro, f"offset no numérico: {fila['offset_in_recording_s']!r}"))
            continue

        ruta_clip = clips / fila["filename"]
        if not ruta_clip.exists():
            # Ajuste del gate: los clips reales viven en subcarpetas por tipo.
            hallados = sorted(carpeta.rglob(fila["filename"]))
            if hallados:
                ruta_clip = hallados[0]
        ruta_espectro = espectros / (Path(fila["filename"]).stem + ".png")
        if not ruta_clip.exists():
            reporte.clips_faltantes.append(fila["filename"])
        if not ruta_espectro.exists() and ruta_clip.exists():
            # Los datos reales no traen espectrogramas: se generan acá.
            try:
                from generar_fixtures import escribir_espectrograma

                espectros.mkdir(parents=True, exist_ok=True)
                escribir_espectrograma(ruta_clip, ruta_espectro)
            except Exception as e:  # noqa: BLE001 — reportar, no romper
                reporte.espectrogramas_faltantes.append(
                    f"{ruta_espectro.name} (falló generación: {e})"
                )
        elif not ruta_espectro.exists():
            reporte.espectrogramas_faltantes.append(ruta_espectro.name)

        existia = con.execute(
            "SELECT 1 FROM segmento WHERE filename = ?", (fila["filename"],)
        ).fetchone()

        # Upsert por filename. Si el segmento ya fue revisado a mano
        # (revisado_en no nulo), el CSV NO pisa el veredicto del revisor.
        con.execute(
            """
            INSERT INTO segmento (filename, tipo, fuente, inicio_grabacion, offset_s,
                                  fecha_hora_absoluta, estado, clip_path, espectrograma_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(filename) DO UPDATE SET
                tipo = excluded.tipo,
                fuente = excluded.fuente,
                inicio_grabacion = excluded.inicio_grabacion,
                offset_s = excluded.offset_s,
                fecha_hora_absoluta = excluded.fecha_hora_absoluta,
                clip_path = excluded.clip_path,
                espectrograma_path = excluded.espectrograma_path,
                estado = CASE WHEN segmento.revisado_en IS NULL
                              THEN excluded.estado ELSE segmento.estado END,
                actualizado_en = datetime('now')
            """,
            (
                fila["filename"],
                fila["type"],
                fila.get("recording_source") or "desconocida",
                fila.get("recording_start") or None,
                offset,
                fila.get("absolute_datetime") or None,
                estado,
                str(ruta_clip.resolve()) if ruta_clip.exists() else None,
                str(ruta_espectro.resolve()) if ruta_espectro.exists() else None,
            ),
        )
        if existia:
            rep.actualizadas += 1
        else:
            rep.insertadas += 1

    con.commit()


def importar(carpeta: Path | str, ruta_db: Path | str = base.RUTA_DB) -> Reporte:
    carpeta = Path(carpeta)
    reporte = Reporte(carpeta=carpeta)

    if not carpeta.is_dir():
        reporte.errores.append(f"La carpeta {carpeta} no existe")
        return reporte

    con = base.conectar(ruta_db)
    try:
        hubo_csv = False
        for nombre, es_candidatos in (("catalogo.csv", False), ("candidatos.csv", True)):
            ruta = carpeta / nombre
            if ruta.exists():
                hubo_csv = True
                _importar_csv(con, ruta, carpeta, reporte, es_candidatos)
            else:
                reporte.errores.append(f"No se encontró {nombre} en {carpeta}/")
        if not hubo_csv:
            reporte.errores.append("Nada para importar: la carpeta no tiene ningún CSV esperado")
    finally:
        con.close()
    return reporte


def imprimir_resumen(r: Reporte) -> None:
    print(f"\nImportación de {r.carpeta}/")
    print("=" * 46)
    for a in r.archivos:
        print(f"\n{a.nombre}: {a.presentes} filas → {a.insertadas} nuevas, {a.actualizadas} actualizadas")
        if a.columnas_mapeadas:
            mapeos = ", ".join(f"{k} → {v}" for k, v in a.columnas_mapeadas.items())
            print(f"  Columnas mapeadas por sinónimo: {mapeos}")
        if a.columnas_faltantes:
            print(f"  ⚠ Columnas faltantes: {', '.join(a.columnas_faltantes)}")
        if a.columnas_extra:
            print(f"  ⚠ Columnas extra (ignoradas): {', '.join(a.columnas_extra)}")
        for nro, motivo in a.filas_invalidas:
            print(f"  ⚠ Fila {nro} salteada: {motivo}")
    if r.clips_faltantes:
        print(f"\n⚠ {len(r.clips_faltantes)} clips referenciados que no existen en clips/:")
        for c in r.clips_faltantes[:10]:
            print(f"    {c}")
        if len(r.clips_faltantes) > 10:
            print(f"    … y {len(r.clips_faltantes) - 10} más")
    if r.espectrogramas_faltantes:
        print(f"⚠ {len(r.espectrogramas_faltantes)} espectrogramas faltantes en espectrogramas/")
    for e in r.errores:
        print(f"⚠ {e}")
    print(f"\nTotal: {r.total_cargadas} segmentos cargados en la base.")


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(argv) >= 2 else 1
    carpeta = argv[1]
    ruta_db = base.RUTA_DB
    if "--db" in argv:
        ruta_db = Path(argv[argv.index("--db") + 1])
    reporte = importar(carpeta, ruta_db)
    imprimir_resumen(reporte)
    return 1 if (reporte.errores and reporte.total_cargadas == 0) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
