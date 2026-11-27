"""Parser de ejecución con filas reales de los informes de la UNA."""

import datetime as dt
import math

import pytest

from finanzas_cr.etl.ejecucion import (
    clasificar_columna,
    codigo_de,
    detectar_corte,
    detectar_programa,
    leer_numero,
    mes_de,
    nivel_de,
    padre_de,
    parsear_filas,
)


def por_codigo(tabla):
    return {f["codigo"]: f for f in tabla.filas}


# --- Formato detallado (2024) -------------------------------------------------

def test_detallado_2024_metadatos(filas):
    t = parsear_filas(filas("una_2024_06_integrado"), "integrado")
    assert t.programa == "integrado"
    assert t.corte == dt.date(2024, 6, 30)
    assert t.unidad == 1.0
    assert t.formato == "detallado"


def test_detallado_2024_montos(filas):
    t = parsear_filas(filas("una_2024_06_integrado"), "integrado")
    f = por_codigo(t)["0.01.01"]
    assert f["nombre"] == "Sueldos para Cargos Fijos"
    assert f["nivel"] == "subpartida" and f["padre"] == "0.01.00"
    assert f["presupuesto_inicial"] == pytest.approx(33982103340.18)
    assert f["presupuesto_total"] == pytest.approx(32289563211.95)
    assert f["girado_m01"] == pytest.approx(2200430733.39)
    assert f["girado_m06"] == pytest.approx(2706938156.55)
    assert f["girado_m07"] == 0
    assert f["girado"] == pytest.approx(15697611535.43)
    assert f["total_gastado"] == pytest.approx(15697611535.43)
    assert f["disponible"] == pytest.approx(16591951676.52)


def test_detallado_2024_modificaciones(filas):
    t = parsear_filas(filas("una_2024_06_integrado"), "integrado")
    mods = [m for m in t.modificaciones if m["codigo"] == "0.01.01"]
    por_numero = {m["numero"]: m["monto"] for m in mods if m["tipo"] == "interna"}
    assert por_numero[6] == pytest.approx(-1577853729.74)
    assert sum(por_numero.values()) == pytest.approx(por_codigo(t)["0.01.01"]["total_modificaciones"])
    # los residuos de redondeo (p. ej. -8e-07) no cuentan como modificación
    assert all(abs(m["monto"]) >= 0.5 for m in t.modificaciones)


def test_detallado_2024_ref_en_dietas(filas):
    t = parsear_filas(filas("una_2024_06_integrado"), "integrado")
    errores = [e for e in t.errores_celda if e["codigo"] == "0.02.05"]
    assert errores and errores[0]["valor"] == "#REF!"
    assert math.isnan(por_codigo(t)["0.02.05"]["girado_m05"])


def test_detallado_2024_no_lee_la_copia_en_miles(filas):
    t = parsear_filas(filas("una_2024_06_integrado"), "integrado")
    codigos = [f["codigo"] for f in t.filas]
    assert len(codigos) == len(set(codigos))
    assert t.total_documento["presupuesto_inicial"] == pytest.approx(154028076784.95)


# --- Formato resumen (2018): encabezados corridos y miles ---------------------

def test_resumen_2018_columnas_corridas(filas):
    t = parsear_filas(filas("una_2018_06_academico"), "academico")
    assert t.formato == "resumen"
    assert t.unidad == 1000.0
    f = por_codigo(t)["0.00.00"]
    assert f["presupuesto_inicial"] == pytest.approx(60789981.60234 * 1000)
    assert f["recortes"] == pytest.approx(-474579.20663 * 1000)
    assert f["presupuesto_total"] == pytest.approx(60315402.39571 * 1000)
    assert f["total_gastado"] == pytest.approx(28112820.74001 * 1000)
    assert f["disponible"] == pytest.approx(32202581.6557 * 1000)
    assert math.isnan(f["girado_m01"])  # el resumen no trae girado mensual


# --- Encabezados con número de serie de Excel (2022) --------------------------

def test_2022_fecha_serial_y_errata(filas):
    t = parsear_filas(filas("una_2022_12_academico"), "academico")
    assert t.corte == dt.date(2022, 12, 31)  # el título dice "DICIEMRE"
    assert t.unidad == 1000.0
    f = por_codigo(t)["0.00.00"]
    assert f["girado_m01"] == pytest.approx(8405013.61739 * 1000)  # encabezado 44562
    assert f["girado_m02"] == pytest.approx(3751465.20638 * 1000)  # encabezado 44593
    assert f["girado"] == pytest.approx(f["total_gastado"], rel=1e-9)


# --- Inconsistencia real del documento (2025) ---------------------------------

def test_2025_activos_financieros_gastado_en_cero(filas):
    t = parsear_filas(filas("una_2025_06_integrado"), "integrado")
    f = por_codigo(t)["4.02.06"]
    assert f["girado"] == pytest.approx(22487503407.3)
    assert f["total_gastado"] == 0
    assert f["disponible"] == pytest.approx(22487503407.3)


# --- Programa y unidad --------------------------------------------------------

def test_2019_programa_academico_no_consolidado(filas):
    t = parsear_filas(filas("una_2019_06_academico"), "academico")
    assert t.programa == "academico"
    assert t.corte == dt.date(2019, 3, 31)  # título desactualizado en el propio documento


def test_2016_sin_unidad_usa_la_del_libro(filas):
    t = parsear_filas(filas("una_2016_12_administrativo"), "Administrativo")
    assert t.unidad_inferida and t.unidad == 1.0
    t = parsear_filas(filas("una_2016_12_administrativo"), "Administrativo", unidad_defecto=1000.0)
    assert t.unidad_inferida and t.unidad == 1000.0
    assert por_codigo(t)["0.00.00"]["presupuesto_inicial"] == pytest.approx(17033180.67899 * 1000)


def test_hoja_que_no_es_de_ejecucion():
    assert parsear_filas([("CUADRO DE INGRESOS",), ("CODIGO", "DESCRIPCION")]) is None


# --- Utilidades ---------------------------------------------------------------

@pytest.mark.parametrize("texto,esperado", [
    ("0 01 01", "0.01.01"), ("5 02 99", "5.02.99"), ("0.01.01", "0.01.01"),
    ("COD.", None), (None, None), (101, None),
])
def test_codigo_de(texto, esperado):
    assert codigo_de(texto) == esperado


def test_niveles_y_padres():
    assert nivel_de("0.00.00") == "partida" and padre_de("0.00.00") is None
    assert nivel_de("0.01.00") == "grupo" and padre_de("0.01.00") == "0.00.00"
    assert nivel_de("0.01.05") == "subpartida" and padre_de("0.01.05") == "0.01.00"


@pytest.mark.parametrize("palabra,mes", [
    ("DICIEMBRE", 12), ("DICIEMRE", 12), ("DEDICIEMBRE", 12), ("SETIEMBRE", 9), ("SEPTIEMBRE", 9), ("JUNIO", 6),
])
def test_mes_de(palabra, mes):
    assert mes_de(palabra) == mes


@pytest.mark.parametrize("texto,fecha", [
    ("AL 30 DE JUNIO DE 2024", dt.date(2024, 6, 30)),
    ("AL 30 DE JUNIO 2025", dt.date(2025, 6, 30)),
    ("AL 31 DE DICIEMBRE DEL 2016", dt.date(2016, 12, 31)),
    ("AL 31 DEDICIEMBRE DE 2022", dt.date(2022, 12, 31)),
    ("AL 31 DE SETIEMBRE DE 2018", dt.date(2018, 9, 30)),  # día inexistente → fin de mes
])
def test_detectar_corte(texto, fecha):
    assert detectar_corte([texto]) == fecha


@pytest.mark.parametrize("etiqueta,campo", [
    ("PRES. INICIAL", ("presupuesto_inicial", None)),
    ("RECORTES Y RECLASIF.", ("recortes", None)),
    ("ENERO MODIF. INTER. NO.1-2024", ("modificacion", 1)),
    ("TOTAL MOD.INTER.", ("total_modificaciones", None)),
    ("PRESUP.EXT. NO.2-2024", ("extraordinario", 2)),
    ("TOTAL PRESUP.EXTR", ("total_extraordinarios", None)),
    ("TOT. MODIF. Y PRES.EXTRA.", ("total_variaciones", None)),
    ("TOTAL PRESUP.", ("presupuesto_total", None)),
    ("GIRADO 2024-03", ("girado_mes", 3)),
    ("GIRADO ACUMULADO 2024-03", None),
    ("GIRADO ENERO A JUNIO", None),
    ("2021-01 GIRADO AL 31-01-21", None),
    ("COMPROM.", ("compromisos", None)),
    ("TOTAL GASTADO", ("total_gastado", None)),
    ("MONTO DISPONIBLE", ("disponible", None)),
])
def test_clasificar_columna(etiqueta, campo):
    assert clasificar_columna(etiqueta) == campo


def test_detectar_programa_prioriza_el_especifico():
    titulos = ["CONSOLIDADO DE EGRESOS POR PROGRAMA", "PROGRAMA VIDA ESTUDIANTIL"]
    assert detectar_programa(titulos) == "vida_universitaria"
    assert detectar_programa(["CONSOLIDADO DE EGRESOS"]) == "integrado"
    assert detectar_programa([], "EGRESOS ADM") == "administrativo"


def test_leer_numero():
    assert leer_numero(None).valor == 0
    assert leer_numero("1,234.5").valor == 1234.5
    assert leer_numero("-").valor == 0
    v = leer_numero("#REF!")
    assert math.isnan(v.valor) and v.error == "#REF!"
