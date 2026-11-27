"""Liquidación presupuestaria: elección de hoja, combinación con la ejecución y validación cruzada."""

import datetime as dt

from finanzas_cr.etl.ejecucion import TablaEjecucion, prioridad
from finanzas_cr.pipeline import EJECUCION, LIQUIDACION, Libro, combinar
from finanzas_cr.validacion import validar_documentos


def fila(codigo, programa="academico", **montos):
    base = {"programa": programa, "codigo": codigo, "nivel": "subpartida", "nombre": f"Cuenta {codigo}",
            "presupuesto_inicial": 100.0e6, "presupuesto_total": 100.0e6, "total_gastado": 80.0e6}
    base.update(montos)
    return base


def libro(documento, anio, mes, filas, bitstream=1):
    corte = dt.date(anio, mes, 31 if mes == 12 else 30).isoformat()
    ctx = {"bitstream_id": bitstream, "anio": anio, "corte": corte, "mes_corte": mes, "documento": documento}
    return Libro(documento, ctx, filas=[{**ctx, **f} for f in filas])


def test_prioriza_la_hoja_con_gasto():
    """En la liquidación 2016-2017 la hoja de «conformación» trae el gasto en 0."""
    conformacion = TablaEjecucion("academico", None, 1000.0, "resumen",
                                  filas=[fila("1.01.01", total_gastado=0.0) for _ in range(150)])
    ejecucion = TablaEjecucion("academico", None, 1000.0, "resumen", filas=[fila("1.01.01")] * 140)
    assert prioridad(ejecucion) > prioridad(conformacion)


def test_liquidacion_llena_el_anio_sin_cierre():
    ej = [libro(EJECUCION, 2019, 9, [fila("1.01.01")], 10), libro(EJECUCION, 2020, 12, [fila("1.01.01")], 11)]
    liq = [libro(LIQUIDACION, 2019, 12, [fila("1.01.01")], 20), libro(LIQUIDACION, 2020, 12, [fila("1.01.01")], 21)]
    usados, cruzadas = combinar(ej, liq)
    cortes = {(lib.documento, lib.ctx["corte"]) for lib in usados}
    assert (LIQUIDACION, "2019-12-31") in cortes  # 2019 no tenía informe de diciembre
    assert (LIQUIDACION, "2020-12-31") not in cortes  # 2020 sí: manda el informe de ejecución
    assert (EJECUCION, "2020-12-31") in cortes
    assert cruzadas == []  # 2020 coincide en todo


def test_combinar_reporta_diferencias_y_duplicados():
    ej = [libro(EJECUCION, 2021, 12, [fila("0.02.01", total_gastado=611e6)], 1),
          libro(EJECUCION, 2021, 12, [fila("0.02.01", total_gastado=611e6)], 2)]
    liq = [libro(LIQUIDACION, 2021, 12, [fila("0.02.01", total_gastado=917e6)], 3)]
    usados, cruzadas = combinar(ej, liq)
    assert [lib.ctx["bitstream_id"] for lib in usados] == [2]  # el más reciente
    assert {c["regla"] for c in cruzadas} == {"duplicado", "liquidacion_vs_ejecucion"}


def test_validar_documentos_caso_real_2021():
    """Entre el informe de diciembre 2021 y la liquidación se movieron ₡306 M entre dos cuentas."""
    ej = [fila("0.02.01", total_gastado=0.0), fila("0.02.02", total_gastado=322.1484e6)]
    liq = [fila("0.02.01", total_gastado=306.0215e6), fila("0.02.02", total_gastado=16.1269e6)]
    r = validar_documentos(ej, liq, {"anio": 2021, "corte": "2021-12-31"})
    assert {(x["codigo"], x["campo"]) for x in r} == {("0.02.01", "total_gastado"), ("0.02.02", "total_gastado")}
    assert abs(sum(x["diferencia"] for x in r)) < 1e3  # se compensan: es un traslado, no dinero nuevo


def test_validar_documentos_cuenta_que_falta():
    r = validar_documentos([fila("1.01.01")], [fila("1.01.01"), fila("1.09.99", presupuesto_total=620_000.0)],
                           {"anio": 2016})
    assert len(r) == 1 and r[0]["campo"] == "cuenta" and "solo aparece en la liquidación" in r[0]["detalle"]
    # montos dentro de la tolerancia no se reportan
    assert validar_documentos([fila("1.01.01")], [fila("1.01.01", total_gastado=80.0e6 + 50)], {}) == []
