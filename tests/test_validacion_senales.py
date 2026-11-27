"""Validaciones y señales, con casos reales y sintéticos."""

import datetime as dt

import pytest

from finanzas_cr.etl.ejecucion import TablaEjecucion, parsear_filas
from finanzas_cr.senales import senales_tabla
from finanzas_cr.validacion import validar_metadatos, validar_programas, validar_tabla

CTX = {"bitstream_id": 1, "anio": 2024, "corte": "2024-12-31"}


def fila(codigo, **montos):
    base = {k: 0.0 for k in ("presupuesto_inicial", "recortes", "total_modificaciones", "total_extraordinarios",
                             "total_variaciones", "presupuesto_total", "girado", "compromisos",
                             "total_gastado", "disponible")}
    base.update({f"girado_m{m:02d}": 0.0 for m in range(1, 13)})
    base.update(montos)
    p, g, s = codigo.split(".")
    nivel = "partida" if g == s == "00" else "grupo" if s == "00" else "subpartida"
    padre = None if nivel == "partida" else f"{p}.00.00" if nivel == "grupo" else f"{p}.{g}.00"
    return {"codigo": codigo, "nivel": nivel, "padre": padre, "partida": p, "partida_nombre": "X",
            "nombre": f"Cuenta {codigo}", **base}


def tabla(filas, programa="academico", corte=dt.date(2024, 12, 31), mods=()):
    return TablaEjecucion(programa=programa, corte=corte, unidad=1.0, formato="detallado",
                          filas=list(filas), modificaciones=list(mods))


def reglas(resultado):
    return {(r["regla"], r["codigo"]) for r in resultado}


# --- Validación ---------------------------------------------------------------

def test_tabla_consistente_no_genera_hallazgos():
    sub = fila("1.01.01", presupuesto_inicial=100e6, presupuesto_total=100e6, girado=60e6,
               total_gastado=60e6, disponible=40e6, girado_m01=60e6)
    t = tabla([fila("1.00.00", **{k: v for k, v in sub.items() if isinstance(v, float)}),
               fila("1.01.00", **{k: v for k, v in sub.items() if isinstance(v, float)}), sub])
    assert validar_tabla(t, CTX) == []


def test_identidades_rotas():
    f = fila("1.01.01", presupuesto_inicial=100e6, total_variaciones=10e6, total_modificaciones=10e6,
             presupuesto_total=100e6, girado=50e6, total_gastado=40e6, disponible=0.0)
    r = reglas(validar_tabla(tabla([f]), CTX))
    assert ("identidad_presupuesto", "1.01.01") in r
    assert ("identidad_gasto", "1.01.01") in r
    assert ("identidad_disponible", "1.01.01") in r
    assert ("suma_modificaciones", "1.01.01") in r  # no hay detalle de modificaciones que sume 10 M


def test_tolerancia_de_redondeo():
    f = fila("1.01.01", presupuesto_inicial=100e6, presupuesto_total=100e6 + 0.4, total_gastado=0.0,
             disponible=100e6)
    assert validar_tabla(tabla([f]), CTX) == []


def test_jerarquia():
    padre = fila("2.00.00", presupuesto_total=10e6, disponible=10e6, presupuesto_inicial=10e6)
    hijo = fila("2.01.00", presupuesto_total=7e6, disponible=7e6, presupuesto_inicial=7e6)
    r = validar_tabla(tabla([padre, hijo]), CTX)
    assert {(x["regla"], x["campo"]) for x in r} >= {("jerarquia", "presupuesto_total")}


def test_caso_real_2025_activos_financieros(filas):
    t = parsear_filas(filas("una_2025_06_integrado"), "integrado")
    r = validar_tabla(t, CTX)
    gasto = [x for x in r if x["regla"] == "identidad_gasto" and x["codigo"] == "4.02.06"]
    assert gasto and gasto[0]["esperado"] == pytest.approx(22487503407.3)
    assert gasto[0]["encontrado"] == 0


def test_caso_real_2024_ref_se_reporta(filas):
    t = parsear_filas(filas("una_2024_06_integrado"), "integrado")
    r = validar_tabla(t, CTX)
    assert any(x["regla"] == "error_celda" and x["codigo"] == "0.02.05" for x in r)


def test_suma_de_programas():
    def t(programa, monto):
        return tabla([fila("0.00.00", presupuesto_total=monto, disponible=monto)], programa=programa)

    ok = [t("integrado", 6e6), t("academico", 1e6), t("administrativo", 2e6), t("vida_universitaria", 3e6)]
    assert validar_programas(ok, CTX) == []
    mal = [t("integrado", 7e6), *ok[1:]]
    assert [x["regla"] for x in validar_programas(mal, CTX)] == ["suma_programas"]


def test_metadatos_detecta_anio_equivocado():
    r = validar_metadatos(CTX, dt.date(2024, 12, 31), "Informe de ejec semetral CGR dic 2025.xlsx",
                          "Informe de Ejecución Presupuestaria a diciembre 2024")
    assert len(r) == 1 and r[0]["campo"] == "nombre_archivo"
    assert validar_metadatos(CTX, dt.date(2025, 6, 30), "Inf Ejec Presupuestaria Jun 25 CGR.xlsx", "junio 2025") == []


# --- Señales ------------------------------------------------------------------

def senales(*filas, corte=dt.date(2024, 12, 31)):
    return {s["senal"] for s in senales_tabla(tabla(filas, corte=corte), CTX)}


def test_gasto_sin_presupuesto():
    assert "gasto_sin_presupuesto" in senales(fila("0.99.99", total_gastado=43e6))


def test_sobregiro():
    assert "sobregiro" in senales(fila("1.99.99", presupuesto_inicial=50e6, presupuesto_total=50e6,
                                       total_gastado=152e6))


def test_modificacion_alta_y_creada():
    assert "modificacion_alta" in senales(fila("1.01.01", presupuesto_inicial=20e6, total_variaciones=15e6,
                                               presupuesto_total=35e6))
    assert "creada_por_modificacion" in senales(fila("1.01.01", total_variaciones=20e6, presupuesto_total=20e6))


def test_subejecucion_solo_al_cierre():
    f = fila("5.01.01", presupuesto_inicial=200e6, presupuesto_total=200e6, total_gastado=20e6)
    assert "subejecucion" in senales(f)
    assert "subejecucion" not in senales(f, corte=dt.date(2024, 6, 30))


def test_concentracion_diciembre():
    f = fila("2.01.01", presupuesto_inicial=100e6, presupuesto_total=100e6, total_gastado=90e6,
             girado=90e6, girado_m12=45e6)
    assert "concentracion_diciembre" in senales(f)


def test_sin_senales_en_grupos_ni_partidas():
    assert senales(fila("0.00.00", total_gastado=43e6)) == set()
