"""Listado y descarga de series de la UNA, con manifiesto versionable."""

from __future__ import annotations

import csv
from dataclasses import asdict, fields
from pathlib import Path

from . import config
from .dspace import Archivo, ClienteDSpace, nombre_seguro


def filtrar_formatos(archivos: list[Archivo], formatos: list[str] | None) -> list[Archivo]:
    if not formatos:
        return archivos
    exts = tuple(e for f in formatos for e in config.FORMATOS.get(f, (f".{f}",)))
    return [a for a in archivos if a.extension in exts]


def ruta_local(archivo: Archivo, raiz: Path | None = None) -> Path:
    raiz = raiz or config.RAW
    anio = str(archivo.anio) if archivo.anio else "sin_anio"
    return raiz / "una" / archivo.serie / anio / f"{archivo.bitstream_id}_{nombre_seguro(archivo.nombre)}"


def ruta_manifiesto(serie: str, raiz: Path | None = None) -> Path:
    return (raiz or config.MANIFEST) / f"una_{serie}.csv"


CAMPOS = [f.name for f in fields(Archivo)] + ["ruta_local"]


def escribir_manifiesto(archivos: list[Archivo], destino: Path) -> Path:
    """Guarda el manifiesto (CSV) combinándolo con el existente por bitstream_id."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    filas: dict[str, dict] = {}
    if destino.exists():
        with open(destino, encoding="utf-8", newline="") as fh:
            for fila in csv.DictReader(fh):
                filas[fila["bitstream_id"]] = fila
    for a in archivos:
        fila = asdict(a)
        fila["ruta_local"] = ruta_local(a).relative_to(config.DATA).as_posix()
        filas[str(a.bitstream_id)] = fila
    orden = sorted(filas.values(), key=lambda f: (f.get("anio") or "", f.get("item_fecha") or "", int(f["bitstream_id"])))
    with open(destino, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        w.writeheader()
        for f in orden:
            w.writerow({k: f.get(k, "") for k in CAMPOS})
    return destino


def leer_manifiesto(serie: str) -> list[dict]:
    ruta = ruta_manifiesto(serie)
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def listar(serie: str, formatos: list[str] | None, desde: int | None, hasta: int | None,
           cliente: ClienteDSpace | None = None) -> list[Archivo]:
    cliente = cliente or ClienteDSpace()
    return filtrar_formatos(cliente.archivos_serie(serie, desde, hasta), formatos)


def descargar(serie: str, formatos: list[str] | None, desde: int | None, hasta: int | None,
              cliente: ClienteDSpace | None = None, log=print) -> list[Path]:
    cliente = cliente or ClienteDSpace()
    archivos = listar(serie, formatos, desde, hasta, cliente)
    rutas = []
    for i, a in enumerate(archivos, 1):
        destino = ruta_local(a)
        log(f"[{i}/{len(archivos)}] {a.anio} · {a.item_titulo} · {a.nombre} ({a.bytes/1e6:.1f} MB)")
        rutas.append(cliente.descargar(a, destino))
    escribir_manifiesto(archivos, ruta_manifiesto(serie))
    return rutas
