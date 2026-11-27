"""Señales para revisar: patrones de ejecución que merecen una pregunta.

Una señal NO es una acusación ni prueba de irregularidad. Es un punto de
partida para preguntar a la institución o revisar el documento. Los umbrales
están documentados en docs/metodologia.md y son deliberadamente simples para
que cualquiera pueda reproducirlos.
"""

from __future__ import annotations

import math

from .etl.ejecucion import TablaEjecucion

UMBRALES = {
    "monto_minimo": 1_000_000,          # ₡1 millón: debajo de esto no se señala
    "sobregiro_minimo": 100_000,        # diferencia mínima para "sobregiro"
    "modificacion_ratio": 0.5,          # variaciones > 50 % del presupuesto inicial
    "modificacion_base": 10_000_000,    # sobre presupuestos iniciales de al menos ₡10 M
    "subejecucion_ratio": 0.5,          # menos del 50 % ejecutado al cierre
    "subejecucion_base": 50_000_000,    # sobre presupuestos de al menos ₡50 M
    "diciembre_ratio": 0.30,            # más del 30 % del girado anual en diciembre
    "diciembre_base": 50_000_000,
}

DESCRIPCIONES = {
    "gasto_sin_presupuesto": "Hay gasto registrado en una cuenta sin presupuesto asignado.",
    "sobregiro": "El gasto supera el presupuesto total de la cuenta.",
    "modificacion_alta": "Las modificaciones cambiaron el presupuesto inicial en más de la mitad.",
    "creada_por_modificacion": "La cuenta no tenía presupuesto inicial y se financió con modificaciones.",
    "subejecucion": "Al cierre del año se ejecutó menos de la mitad del presupuesto.",
    "concentracion_diciembre": "Una parte alta del gasto del año se giró en diciembre.",
}


def _ok(*v):
    return all(not (isinstance(x, float) and math.isnan(x)) for x in v)


def senales_tabla(t: TablaEjecucion, contexto: dict, u: dict = UMBRALES) -> list[dict]:
    salida: list[dict] = []
    es_cierre = t.corte is not None and t.corte.month == 12

    def agregar(f, senal, monto, referencia, ratio=None):
        salida.append({
            **contexto,
            "programa": t.programa,
            "codigo": f["codigo"],
            "partida": f["partida"],
            "partida_nombre": f["partida_nombre"],
            "nombre": f["nombre"],
            "senal": senal,
            "monto": monto,
            "referencia": referencia,
            "ratio": ratio,
            "descripcion": DESCRIPCIONES[senal],
        })

    for f in t.filas:
        if f["nivel"] != "subpartida":
            continue
        ini, tot, gas = f["presupuesto_inicial"], f["presupuesto_total"], f["total_gastado"]
        var = f["recortes"] + f["total_variaciones"]
        if not _ok(ini, tot, gas, var):
            continue

        if tot <= 0 and gas >= u["monto_minimo"]:
            agregar(f, "gasto_sin_presupuesto", gas, tot)
        elif tot > 0 and gas - tot >= u["sobregiro_minimo"]:
            agregar(f, "sobregiro", gas - tot, tot, gas / tot)

        if ini >= u["modificacion_base"] and abs(var) > u["modificacion_ratio"] * ini:
            agregar(f, "modificacion_alta", var, ini, var / ini)
        elif ini <= 0 and var >= u["modificacion_base"]:
            agregar(f, "creada_por_modificacion", var, ini)

        if es_cierre and tot >= u["subejecucion_base"] and gas / tot < u["subejecucion_ratio"]:
            agregar(f, "subejecucion", tot - gas, tot, gas / tot)

        dic, gir = f.get("girado_m12", math.nan), f["girado"]
        if es_cierre and _ok(dic) and gir >= u["diciembre_base"] and dic / gir > u["diciembre_ratio"]:
            agregar(f, "concentracion_diciembre", dic, gir, dic / gir)
    return salida
