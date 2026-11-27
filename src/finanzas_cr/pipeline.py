"""Procesa los Excel descargados (ejecución y liquidación) y genera los CSV limpios.

Dos series traen las mismas tablas por programa:

* **Informes de ejecución** (marzo, junio, setiembre, diciembre): la fuente principal.
* **Liquidación presupuestaria**: el cierre oficial del año, con las mismas
  tablas al 31 de diciembre.

Regla de combinación: el informe de ejecución de diciembre manda. La
liquidación se usa para los años que no tienen informe de diciembre en Excel
(p. ej. 2019) y, donde existen ambos, se compara cuenta por cuenta
(`liquidacion_vs_ejecucion` en validacion.csv). Todas las filas de la
liquidación quedan además en liquidacion.csv.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config
from .etl.ejecucion import leer_libro
from .scraper import leer_manifiesto
from .senales import senales_tabla
from .validacion import validar_documentos, validar_metadatos, validar_programas, validar_tabla

SALIDA = config.PROCESSED / "una"
EJECUCION = "informe de ejecución"
LIQUIDACION = "liquidación"


def corte_del_libro(tablas):
    """La fecha de corte más repetida entre las hojas (algunas traen títulos desactualizados)."""
    cortes = Counter(t.corte for t in tablas if t.corte)
    if not cortes:
        return None
    maximo = max(cortes.values())
    empatados = [c for c, n in cortes.items() if n == maximo]
    integrado = next((t.corte for t in tablas if t.programa == "integrado" and t.corte in empatados), None)
    return integrado or max(empatados)


@dataclass
class Libro:
    """Todo lo que sale de un libro de Excel."""

    documento: str
    ctx: dict
    filas: list[dict] = field(default_factory=list)
    mods: list[dict] = field(default_factory=list)
    validaciones: list[dict] = field(default_factory=list)
    senales: list[dict] = field(default_factory=list)
    informes: list[dict] = field(default_factory=list)

    @property
    def es_cierre(self) -> bool:
        return self.ctx.get("mes_corte") == 12


def procesar_libro(m: dict, documento: str, log=print) -> Libro | None:
    ruta = config.DATA / m["ruta_local"]
    base_error = {"bitstream_id": int(m["bitstream_id"]), "documento": documento}
    if not ruta.exists():
        log(f"  falta {ruta}, se omite")
        return None
    log(f"Procesando {documento} {m['anio']} · {m['nombre']}")
    try:
        tablas = leer_libro(ruta)
    except Exception as exc:  # un libro dañado no detiene todo
        return Libro(documento, base_error, validaciones=[{**base_error, "regla": "lectura",
                                                           "detalle": f"No se pudo leer el libro: {exc}"}])
    if not tablas:
        return Libro(documento, base_error, validaciones=[{**base_error, "regla": "lectura",
                                                           "detalle": "No se encontraron hojas por programa"}])
    corte = corte_del_libro(tablas)
    ctx = {
        "bitstream_id": int(m["bitstream_id"]),
        "anio": corte.year if corte else int(m["anio"] or 0),
        "corte": corte.isoformat() if corte else "",
        "mes_corte": corte.month if corte else None,
        "documento": documento,
    }
    libro = Libro(documento, ctx)
    libro.validaciones.extend(validar_metadatos(ctx, corte, m["nombre"], m["item_titulo"]))
    for t in tablas:
        if t.corte and corte and t.corte != corte:
            libro.validaciones.append({**ctx, "programa": t.programa, "regla": "metadatos", "campo": "corte",
                                       "detalle": f"La hoja {t.hoja!r} tiene corte {t.corte} distinto al libro "
                                                  f"({corte})"})
        if t.unidad_inferida:
            libro.validaciones.append({**ctx, "programa": t.programa, "regla": "metadatos", "campo": "unidad",
                                       "detalle": f"La hoja {t.hoja!r} no dice si las cifras están en colones o en "
                                                  f"miles; se asumió ×{t.unidad:g} como el resto del libro"})
        base = {**ctx, "fuente_url": m["url"], "fuente_item": m["item_handle"], "hoja": t.hoja,
                "formato": t.formato}
        libro.filas.extend({**base, **f} for f in t.filas)
        libro.mods.extend({**ctx, **x} for x in t.modificaciones)
        libro.validaciones.extend(validar_tabla(t, ctx))
        libro.senales.extend(senales_tabla(t, {**ctx, "fuente_url": m["url"]}))
        partidas = [f for f in t.filas if f["nivel"] == "partida"]
        libro.informes.append({
            **ctx, "programa": t.programa, "hoja": t.hoja, "formato": t.formato, "unidad_original": t.unidad,
            "presupuesto_inicial": sum(f["presupuesto_inicial"] for f in partidas),
            "presupuesto_total": sum(f["presupuesto_total"] for f in partidas),
            "total_gastado": sum(f["total_gastado"] for f in partidas),
            "total_documento_gastado": (t.total_documento or {}).get("total_gastado"),
            "cuentas": len(t.filas), "fuente_url": m["url"], "titulo_item": m["item_titulo"],
        })
    libro.validaciones.extend(validar_programas(tablas, ctx))
    return libro


def leer_serie(serie: str, documento: str, log=print) -> list[Libro]:
    manifiesto = [m for m in leer_manifiesto(serie) if Path(m["nombre"]).suffix.lower() in (".xlsx", ".xlsm")]
    libros = [procesar_libro(m, documento, log) for m in manifiesto]
    return [lib for lib in libros if lib is not None]


def combinar(ejecucion: list[Libro], liquidacion: list[Libro]) -> tuple[list[Libro], list[dict]]:
    """Libros que entran a los datos principales y validaciones cruzadas entre documentos."""
    # Un libro por corte: si hay dos informes de ejecución con la misma fecha, el más reciente
    por_corte: dict[str, Libro] = {}
    duplicados: list[dict] = []
    for lib in sorted(ejecucion, key=lambda x: x.ctx.get("bitstream_id", 0)):
        corte = lib.ctx.get("corte")
        if not corte:
            continue
        if corte in por_corte:
            duplicados.append({"corte": corte, "regla": "duplicado", "documento": EJECUCION,
                               "detalle": f"Hay varios documentos con corte {corte}; se usa el más reciente"})
        por_corte[corte] = lib

    cierres = {lib.ctx["anio"]: lib for lib in por_corte.values() if lib.es_cierre}
    usados = list(por_corte.values())
    cruzadas = list(duplicados)
    for liq in liquidacion:
        anio = liq.ctx.get("anio")
        if not liq.filas:
            cruzadas.extend(liq.validaciones)  # error de lectura
        elif anio in cierres:
            cruzadas.extend(validar_documentos(cierres[anio].filas, liq.filas, liq.ctx))
        else:
            usados.append(liq)  # la liquidación es el único cierre de ese año
    return usados, cruzadas


def procesar(salida: Path = SALIDA, log=print, con_anomalias: bool = True) -> dict[str, Path]:
    ejecucion = leer_serie("ejecucion", EJECUCION, log)
    if not ejecucion:
        raise SystemExit("No hay archivos en el manifiesto. Corre primero: "
                         "finanzas descargar --serie ejecucion --formatos xlsx")
    liquidacion = leer_serie("liquidacion", LIQUIDACION, log)
    usados, cruzadas = combinar(ejecucion, liquidacion)
    sin_corte = [v for lib in ejecucion if not lib.ctx.get("corte") for v in lib.validaciones]

    def juntar(atributo: str, libros) -> list[dict]:
        return [x for lib in libros for x in getattr(lib, atributo)]

    salida.mkdir(parents=True, exist_ok=True)
    ej = pd.DataFrame(juntar("filas", usados))
    rutas = {
        "ejecucion": salida / "ejecucion.csv",
        "modificaciones": salida / "modificaciones.csv",
        "validacion": salida / "validacion.csv",
        "senales": salida / "senales.csv",
        "informes": salida / "informes.csv",
    }
    ej.sort_values(["corte", "programa", "codigo"]).to_csv(rutas["ejecucion"], index=False)
    pd.DataFrame(juntar("mods", usados)).to_csv(rutas["modificaciones"], index=False)
    pd.DataFrame(juntar("validaciones", usados) + cruzadas + sin_corte).to_csv(rutas["validacion"], index=False)
    pd.DataFrame(juntar("senales", usados)).to_csv(rutas["senales"], index=False)
    pd.DataFrame(juntar("informes", usados)).sort_values(["corte", "programa"]).to_csv(rutas["informes"],
                                                                                       index=False)
    if liquidacion:
        rutas["liquidacion"] = salida / "liquidacion.csv"
        liq = pd.DataFrame(juntar("filas", liquidacion))
        liq.sort_values(["corte", "programa", "codigo"]).to_csv(rutas["liquidacion"], index=False)

    if con_anomalias:
        from .anomalias import puntuar

        an = puntuar(ej)
        if not an.empty:
            rutas["anomalias"] = salida / "anomalias.csv"
            an.to_csv(rutas["anomalias"], index=False)
    for r in rutas.values():
        log(f"  → {r.relative_to(config.RAIZ) if r.is_relative_to(config.RAIZ) else r}")
    return rutas


procesar_ejecucion = procesar  # nombre anterior
