"""Modelo de anomalías y dashboard con datos sintéticos (sin red ni archivos reales)."""

import numpy as np
import pandas as pd
import pytest

from finanzas_cr import anomalias
from finanzas_cr.dashboard import datos as D


def ejecucion_sintetica(n_cuentas=40, anios=(2021, 2022, 2023), semilla=0):
    rng = np.random.default_rng(semilla)
    filas = []
    for anio in anios:
        for programa in ("academico", "administrativo", "integrado"):
            for i in range(n_cuentas):
                pres = float(rng.uniform(20e6, 500e6))
                gas = pres * float(rng.uniform(0.7, 0.98))
                girado = {f"girado_m{m:02d}": gas / 12 for m in range(1, 13)}
                filas.append({
                    "anio": anio, "corte": f"{anio}-12-31", "mes_corte": 12, "bitstream_id": anio,
                    "programa": programa, "codigo": f"1.01.{i:02d}", "nivel": "subpartida", "partida": "1",
                    "partida_nombre": "Servicios", "nombre": f"Cuenta {i}", "presupuesto_inicial": pres,
                    "recortes": 0.0, "total_variaciones": 0.0, "presupuesto_total": pres, "total_gastado": gas,
                    "girado": gas, "compromisos": 0.0, "disponible": pres - gas, "fuente_url": "https://x", **girado,
                })
    df = pd.DataFrame(filas)
    # una cuenta muy distinta: 0 % ejecutada y triplicada por modificaciones
    rara = (df["anio"] == 2023) & (df["programa"] == "academico") & (df["codigo"] == "1.01.07")
    df.loc[rara, ["total_gastado", "girado", "total_variaciones", "presupuesto_total"]] = [0.0, 0.0, 900e6, 1000e6]
    return df


def test_anomalias_excluye_integrado_y_cuentas_pequenas():
    df = ejecucion_sintetica()
    df.loc[0, "presupuesto_total"] = 5e6
    prep = anomalias.preparar(df)
    assert "integrado" not in set(prep["programa"])
    assert (prep["presupuesto_total"] >= anomalias.PRESUPUESTO_MINIMO).all()


def test_anomalias_encuentra_la_cuenta_rara():
    pytest.importorskip("sklearn")
    res = anomalias.puntuar(ejecucion_sintetica())
    primera = res.iloc[0]
    assert (primera["anio"], primera["programa"], primera["codigo"]) == (2023, "academico", "1.01.07")
    assert primera["atipico"]


def test_formatos():
    assert D.colones_m(12_345_678_901) == "₡12.346 M"
    assert D.porcentaje(0.858) == "85,8 %"
    assert D.colones_m(float("nan")) == "—"


def test_informe_por_anio_prefiere_el_cierre():
    df = pd.DataFrame({"anio": [2024, 2024, 2025], "corte": ["2024-06-30", "2024-12-31", "2025-06-30"],
                       "bitstream_id": [1, 2, 3], "fuente_url": ["a", "b", "c"]})
    r = D.informe_por_anio(df)
    assert list(r["corte"]) == ["2025-06-30", "2024-12-31"]
    assert list(r["es_cierre"]) == [False, True]


def test_dashboard_se_construye(tmp_path):
    pytest.importorskip("dash")
    from finanzas_cr.dashboard.app import TEMAS, crear_app, fig_anual, fig_partidas

    ej = ejecucion_sintetica(n_cuentas=3)
    partidas = ej.groupby(["anio", "corte", "mes_corte", "bitstream_id", "programa", "fuente_url"], as_index=False)[
        ["presupuesto_inicial", "recortes", "total_variaciones", "presupuesto_total", "total_gastado", "girado"]].sum()
    partidas = partidas.assign(codigo="1.00.00", nivel="partida", partida="1")
    pd.concat([ej, partidas]).to_csv(tmp_path / "ejecucion.csv", index=False)
    app = crear_app(tmp_path)
    assert app.title == "Finanzas Abiertas CR"

    datos = D.cargar(tmp_path)
    filas = D.filas_informe(datos, "2023-12-31", "academico")
    assert len(fig_partidas(D.por_partida(filas), TEMAS["claro"]).data) == 2
    assert len(fig_anual(D.serie_anual(datos, "academico"), TEMAS["oscuro"]).data) == 2


def test_dashboard_sin_datos(tmp_path):
    pytest.importorskip("dash")
    from finanzas_cr.dashboard.app import crear_app

    app = crear_app(tmp_path)
    assert "finanzas procesar" in str(app.layout)
