"""Validaciones de consistencia interna de los informes de ejecución.

Una validación compara dos cifras que el propio documento dice que deberían
coincidir (p. ej. presupuesto inicial + variaciones = presupuesto total).
Una diferencia puede venir del documento o de una mala lectura del parser;
ambas cosas merecen revisión. Ver docs/metodologia.md.
"""

from __future__ import annotations

import math
from collections import defaultdict

from .etl.ejecucion import TablaEjecucion


def tolerancia(*valores: float) -> float:
    """1 000 colones o 0,0001 % del monto mayor (residuos de redondeo de Excel)."""
    mayor = max((abs(v) for v in valores if not math.isnan(v)), default=0.0)
    return max(1000.0, mayor * 1e-6)


def _dif(esperado: float, encontrado: float) -> float | None:
    if math.isnan(esperado) or math.isnan(encontrado):
        return math.nan
    d = encontrado - esperado
    return d if abs(d) > tolerancia(esperado, encontrado) else None


def validar_tabla(t: TablaEjecucion, contexto: dict) -> list[dict]:
    salida: list[dict] = []

    def reportar(regla, fila, campo, esperado, encontrado, detalle=""):
        d = _dif(esperado, encontrado)
        if d is None:
            return
        salida.append({
            **contexto,
            "programa": t.programa,
            "codigo": fila.get("codigo", "TOTAL"),
            "nivel": fila.get("nivel", "total"),
            "nombre": fila.get("nombre", "TOTAL EGRESOS"),
            "regla": regla,
            "campo": campo,
            "esperado": esperado,
            "encontrado": encontrado,
            "diferencia": d,
            "detalle": detalle,
        })

    mods_por_codigo: dict[str, dict[str, float]] = defaultdict(lambda: {"interna": 0.0, "extraordinario": 0.0})
    for m in t.modificaciones:
        mods_por_codigo[m["codigo"]][m["tipo"]] += m["monto"]

    for f in t.filas:
        reportar("identidad_presupuesto", f, "presupuesto_total",
                 f["presupuesto_inicial"] + f["recortes"] + f["total_variaciones"], f["presupuesto_total"],
                 "inicial + recortes + variaciones = total")
        if t.formato == "detallado":
            reportar("suma_modificaciones", f, "total_modificaciones",
                     mods_por_codigo[f["codigo"]]["interna"], f["total_modificaciones"],
                     "suma de modificaciones internas = total")
            reportar("suma_extraordinarios", f, "total_extraordinarios",
                     mods_por_codigo[f["codigo"]]["extraordinario"], f["total_extraordinarios"],
                     "suma de extraordinarios = total")
            reportar("suma_variaciones", f, "total_variaciones",
                     f["total_modificaciones"] + f["total_extraordinarios"], f["total_variaciones"],
                     "modificaciones + extraordinarios = variaciones")
            reportar("identidad_gasto", f, "total_gastado",
                     f["girado"] + f["compromisos"], f["total_gastado"],
                     "girado (suma de meses) + compromisos = total gastado")
        reportar("identidad_disponible", f, "disponible",
                 f["presupuesto_total"] - f["total_gastado"], f["disponible"],
                 "total - gastado = disponible")

    # Jerarquía: los hijos suman al padre
    por_codigo = {f["codigo"]: f for f in t.filas}
    for campo in ("presupuesto_inicial", "presupuesto_total", "total_gastado"):
        sumas: dict[str, float] = defaultdict(float)
        for f in t.filas:
            if f["padre"]:
                sumas[f["padre"]] += f[campo]
        for padre, suma in sumas.items():
            if padre in por_codigo:
                reportar("jerarquia", por_codigo[padre], campo, suma, por_codigo[padre][campo],
                         "suma de cuentas hijas = cuenta padre")

    # Total del documento
    if t.total_documento:
        partidas = [f for f in t.filas if f["nivel"] == "partida"]
        for campo in ("presupuesto_inicial", "presupuesto_total", "total_gastado", "disponible"):
            reportar("total_documento", {}, campo, sum(f[campo] for f in partidas), t.total_documento[campo],
                     "suma de partidas = TOTAL EGRESOS del documento")

    for e in t.errores_celda:
        salida.append({**contexto, "programa": t.programa, "codigo": e["codigo"], "nivel": "",
                       "nombre": "", "regla": "error_celda", "campo": e["campo"], "esperado": math.nan,
                       "encontrado": math.nan, "diferencia": math.nan,
                       "detalle": f"Celda con {e['valor']} (fila {e['fila_excel']}, columna {e['columna_excel']})"})
    return salida


def validar_programas(tablas: list[TablaEjecucion], contexto: dict) -> list[dict]:
    """Académico + administrativo + vida universitaria = integrado, cuenta por cuenta."""
    por_programa = {t.programa: {f["codigo"]: f for f in t.filas} for t in tablas}
    if "integrado" not in por_programa or len(por_programa) < 4:
        return []
    salida = []
    integrado = por_programa.pop("integrado")
    for codigo, fi in integrado.items():
        for campo in ("presupuesto_total", "total_gastado"):
            suma = sum(p.get(codigo, {}).get(campo, 0.0) for p in por_programa.values())
            d = _dif(suma, fi[campo])
            if d is not None:
                salida.append({**contexto, "programa": "integrado", "codigo": codigo, "nivel": fi["nivel"],
                               "nombre": fi["nombre"], "regla": "suma_programas", "campo": campo,
                               "esperado": suma, "encontrado": fi[campo], "diferencia": d,
                               "detalle": "académico + administrativo + vida universitaria = integrado"})
    return salida


def validar_metadatos(contexto: dict, corte, nombre_archivo: str, titulo_item: str) -> list[dict]:
    """Coherencia entre el año del documento, el título del ítem y el nombre del archivo."""
    import re

    salida = []
    if corte is None:
        salida.append({**contexto, "regla": "metadatos", "campo": "corte",
                       "detalle": "No se encontró la fecha de corte en la hoja"})
        return salida
    for origen, texto in (("nombre_archivo", nombre_archivo), ("titulo_item", titulo_item)):
        anios = {int(a) for a in re.findall(r"(20\d{2})", texto or "")}
        cortos = {2000 + int(a) for a in re.findall(r"(?<![\d])(\d{2})(?![\d])", texto or "") if 10 <= int(a) <= 40}
        anios = anios or cortos
        if anios and corte.year not in anios:
            salida.append({**contexto, "regla": "metadatos", "campo": origen,
                           "detalle": f"El documento tiene corte {corte.isoformat()} pero {origen} dice "
                                      f"{', '.join(map(str, sorted(anios)))}: «{texto}»"})
    return salida
