"""Procesa los Excel de ejecución descargados y genera los CSV limpios."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config
from .etl.ejecucion import leer_libro
from .scraper import leer_manifiesto
from .senales import senales_tabla
from .validacion import validar_metadatos, validar_programas, validar_tabla

SALIDA = config.PROCESSED / "una"


def corte_del_libro(tablas):
    """La fecha de corte más repetida entre las hojas (algunas traen títulos desactualizados)."""
    from collections import Counter

    cortes = Counter(t.corte for t in tablas if t.corte)
    if not cortes:
        return None
    maximo = max(cortes.values())
    empatados = [c for c, n in cortes.items() if n == maximo]
    integrado = next((t.corte for t in tablas if t.programa == "integrado" and t.corte in empatados), None)
    return integrado or max(empatados)


def procesar_ejecucion(salida: Path = SALIDA, log=print, con_anomalias: bool = True) -> dict[str, Path]:
    manifiesto = [m for m in leer_manifiesto("ejecucion")
                  if Path(m["nombre"]).suffix.lower() in (".xlsx", ".xlsm")]
    if not manifiesto:
        raise SystemExit("No hay archivos en el manifiesto. Corre primero: finanzas descargar --serie ejecucion --formatos xlsx")

    filas, mods, validaciones, senales, informes = [], [], [], [], []
    for m in manifiesto:
        ruta = config.DATA / m["ruta_local"]
        if not ruta.exists():
            log(f"  falta {ruta}, se omite")
            continue
        log(f"Procesando {m['anio']} · {m['item_titulo']} · {m['nombre']}")
        try:
            tablas = leer_libro(ruta)
        except Exception as exc:  # un libro dañado no detiene todo
            validaciones.append({"bitstream_id": m["bitstream_id"], "regla": "lectura",
                                 "detalle": f"No se pudo leer el libro: {exc}"})
            continue
        if not tablas:
            validaciones.append({"bitstream_id": m["bitstream_id"], "regla": "lectura",
                                 "detalle": "No se encontraron hojas de ejecución por programa"})
            continue
        corte = corte_del_libro(tablas)
        ctx = {
            "bitstream_id": int(m["bitstream_id"]),
            "anio": corte.year if corte else int(m["anio"] or 0),
            "corte": corte.isoformat() if corte else "",
            "mes_corte": corte.month if corte else None,
        }
        validaciones.extend(validar_metadatos(ctx, corte, m["nombre"], m["item_titulo"]))
        for t in tablas:
            if t.corte and corte and t.corte != corte:
                validaciones.append({**ctx, "programa": t.programa, "regla": "metadatos", "campo": "corte",
                                     "detalle": f"La hoja {t.hoja!r} tiene corte {t.corte} distinto al libro ({corte})"})
            if t.unidad_inferida:
                validaciones.append({**ctx, "programa": t.programa, "regla": "metadatos", "campo": "unidad",
                                     "detalle": f"La hoja {t.hoja!r} no dice si las cifras están en colones o en "
                                                f"miles; se asumió ×{t.unidad:g} como el resto del libro"})
            base = {**ctx, "fuente_url": m["url"], "fuente_item": m["item_handle"], "hoja": t.hoja,
                    "formato": t.formato}
            for f in t.filas:
                filas.append({**base, **f})
            for x in t.modificaciones:
                mods.append({**ctx, **x})
            validaciones.extend(validar_tabla(t, ctx))
            senales.extend(senales_tabla(t, {**ctx, "fuente_url": m["url"]}))
            partidas = [f for f in t.filas if f["nivel"] == "partida"]
            informes.append({
                **ctx, "programa": t.programa, "hoja": t.hoja, "formato": t.formato, "unidad_original": t.unidad,
                "presupuesto_inicial": sum(f["presupuesto_inicial"] for f in partidas),
                "presupuesto_total": sum(f["presupuesto_total"] for f in partidas),
                "total_gastado": sum(f["total_gastado"] for f in partidas),
                "total_documento_gastado": (t.total_documento or {}).get("total_gastado"),
                "cuentas": len(t.filas), "fuente_url": m["url"], "titulo_item": m["item_titulo"],
            })
        validaciones.extend(validar_programas(tablas, ctx))

    salida.mkdir(parents=True, exist_ok=True)
    ej = pd.DataFrame(filas)
    # Si hay dos documentos con el mismo corte, se queda el más reciente (mayor bitstream_id)
    duplicados = ej.drop_duplicates(["corte", "bitstream_id"]).groupby("corte")["bitstream_id"].nunique()
    for c in duplicados[duplicados > 1].index:
        validaciones.append({"corte": c, "regla": "duplicado",
                             "detalle": f"Hay varios documentos con corte {c}; se usa el más reciente"})
    ultimo = ej.groupby("corte")["bitstream_id"].transform("max")
    ej = ej[ej["bitstream_id"] == ultimo]

    rutas = {
        "ejecucion": salida / "ejecucion.csv",
        "modificaciones": salida / "modificaciones.csv",
        "validacion": salida / "validacion.csv",
        "senales": salida / "senales.csv",
        "informes": salida / "informes.csv",
    }
    ej.sort_values(["corte", "programa", "codigo"]).to_csv(rutas["ejecucion"], index=False)
    pd.DataFrame(mods).to_csv(rutas["modificaciones"], index=False)
    pd.DataFrame(validaciones).to_csv(rutas["validacion"], index=False)
    pd.DataFrame(senales).to_csv(rutas["senales"], index=False)
    pd.DataFrame(informes).sort_values(["corte", "programa"]).to_csv(rutas["informes"], index=False)

    if con_anomalias:
        from .anomalias import puntuar

        an = puntuar(ej)
        if not an.empty:
            rutas["anomalias"] = salida / "anomalias.csv"
            an.to_csv(rutas["anomalias"], index=False)
    for k, r in rutas.items():
        log(f"  → {r.relative_to(config.RAIZ) if r.is_relative_to(config.RAIZ) else r}")
    return rutas
