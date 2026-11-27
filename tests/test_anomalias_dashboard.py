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
    assert D.dinero(156_705_000_000) == "₡156,7 mil millones"
    assert D.dinero(845_300_000) == "₡845 millones"
    assert D.dinero(12_345_678) == "₡12,3 millones"
    assert D.dinero(-12_345) == "−₡12.345"
    assert D.dinero(float("nan")) == "—"
    assert D.porcentaje(0.858) == "85,8 %"
    assert D.porcentaje(-0.0001, 0) == "0 %"  # nunca «-0 %»
    assert D.fecha_larga("2025-06-30") == "30 de junio de 2025"


def test_nombre_cuenta():
    assert D.nombre_cuenta("0.00.00", "REMUNERACIONES") == "Remuneraciones"
    assert D.nombre_cuenta("0.01.00", "REMUNERACIONES BASICAS") == "Remuneraciones basicas"
    assert D.nombre_cuenta("0.01.01", "Sueldos para Cargos Fijos") == "Sueldos para Cargos Fijos"


def test_ruta_y_prefijo():
    assert D.ruta_cuenta("0.01.05") == ["0.00.00", "0.01.00", "0.01.05"]
    assert D.ruta_cuenta("5.02.00") == ["5.00.00", "5.02.00"]
    assert D.ruta_cuenta("5.00.00") == ["5.00.00"]
    assert D.prefijo("5.00.00") == "5." and D.prefijo("5.02.00") == "5.02." and D.prefijo("5.02.01") == "5.02.01"


def test_informe_por_anio_prefiere_el_cierre():
    df = pd.DataFrame({"anio": [2024, 2024, 2025], "corte": ["2024-06-30", "2024-12-31", "2025-06-30"],
                       "bitstream_id": [1, 2, 3], "fuente_url": ["a", "b", "c"]})
    r = D.informe_por_anio(df)
    assert list(r["corte"]) == ["2025-06-30", "2024-12-31"]
    assert list(r["es_cierre"]) == [False, True]


def con_partidas(ej):
    """Agrega las filas de partida y grupo que suman a las subpartidas sintéticas."""
    claves = ["anio", "corte", "mes_corte", "bitstream_id", "programa", "fuente_url"]
    montos = ["presupuesto_inicial", "recortes", "total_variaciones", "presupuesto_total", "total_gastado", "girado",
              "compromisos", "disponible"] + [f"girado_m{m:02d}" for m in range(1, 13)]
    p = ej.groupby(claves, as_index=False)[montos].sum()
    partida = p.assign(codigo="1.00.00", nivel="partida", partida="1", padre=None, nombre="SERVICIOS",
                       partida_nombre="Servicios", hoja="h", fila_excel=10)
    grupo = p.assign(codigo="1.01.00", nivel="grupo", partida="1", padre="1.00.00", nombre="ALQUILERES",
                     partida_nombre="Servicios", hoja="h", fila_excel=11)
    sub = ej.assign(padre="1.01.00", hoja="h", fila_excel=12)
    return pd.concat([partida, grupo, sub], ignore_index=True)


def guardar(tmp_path, n_cuentas=3):
    ej = con_partidas(ejecucion_sintetica(n_cuentas=n_cuentas))
    ej.to_csv(tmp_path / "ejecucion.csv", index=False)
    mods = pd.DataFrame([
        {"corte": "2023-12-31", "programa": "academico", "codigo": "1.01.00", "nivel": "subpartida",
         "tipo": "interna", "numero": 1, "monto": 5e6},
        {"corte": "2023-12-31", "programa": "academico", "codigo": "1.01.01", "nivel": "subpartida",
         "tipo": "interna", "numero": 1, "monto": -5e6},
        {"corte": "2023-12-31", "programa": "academico", "codigo": "1.01.02", "nivel": "subpartida",
         "tipo": "extraordinario", "numero": 1, "monto": 2e6},
    ])
    mods.to_csv(tmp_path / "modificaciones.csv", index=False)
    return D.cargar(tmp_path)


def test_arbol_las_hojas_llevan_el_valor(tmp_path):
    d = guardar(tmp_path)
    a = D.arbol(D.filas_informe(d, "2023-12-31", "academico"))
    assert set(a.loc[a["hoja"], "nivel"]) == {"subpartida"}
    assert (a.loc[~a["hoja"], "valor"] == 0).all()
    assert a.loc[a["codigo"] == "1.00.00", "padre_id"].item() == "TOTAL"


def test_modificaciones_internas_netean_cero(tmp_path):
    d = guardar(tmp_path)
    g = D.modificaciones_informe(d, "2023-12-31", "academico")
    interna = g[g["tipo"] == "interna"].iloc[0]
    assert interna["recibio"] == 5e6 and interna["cedio"] == -5e6 and interna["etiqueta"] == "Mod. 1"
    assert g[g["tipo"] == "extraordinario"].iloc[0]["etiqueta"] == "Extra. 1"


def test_narrativa(tmp_path):
    d = guardar(tmp_path)
    frases = D.narrativa(d, "2023-12-31", "academico")
    assert frases[0].startswith("En 2023, el programa académico tuvo un presupuesto de ₡")
    assert any("de cada ₡100" in f for f in frases)
    assert any("1 modificaciones internas" in f for f in frases)


def test_serie_anual_marca_los_cierres(tmp_path):
    d = guardar(tmp_path)
    s = D.serie_anual(d, "academico")
    assert list(s["anio"]) == [2021, 2022, 2023]
    assert s["es_cierre"].all()


def test_tinta_contrasta():
    from finanzas_cr.dashboard.figuras import tinta_sobre

    assert tinta_sobre("#cde2fb") == "#0b0b0b"  # celda clara → texto oscuro
    assert tinta_sobre("#0d366b") == "#ffffff"  # celda oscura → texto claro


def test_figuras_con_datos_reales_del_formato(tmp_path):
    pytest.importorskip("plotly")
    from finanzas_cr.dashboard import figuras as F

    d = guardar(tmp_path)
    filas = D.filas_informe(d, "2023-12-31", "academico")
    for nombre in ("claro", "oscuro"):
        t = F.tema(nombre)
        assert len(F.treemap(D.arbol(filas), t, "1.01.00").data) == 1
        assert len(F.de_cada_100(D.composicion(filas), t).data) == 1
        assert len(F.anual(D.serie_anual(d, "academico"), t).data) == 2
        assert F.mapa_calor(D.mapa_ejecucion(d, "academico"), t).layout.annotations
        assert len(F.linea_mods(D.modificaciones_informe(d, "2023-12-31", "academico"), t).data) == 2


def test_dashboard_se_construye(tmp_path):
    pytest.importorskip("dash")
    from finanzas_cr.dashboard.app import crear_app, ficha
    from finanzas_cr.dashboard import figuras as F

    d = guardar(tmp_path)
    app = crear_app(tmp_path)
    assert app.title == "Finanzas Abiertas CR"
    assert len(app.callback_map) >= 6
    # la ficha funciona en los tres niveles y sin cuenta elegida
    for codigo in (None, "1.00.00", "1.01.00", "1.01.01"):
        assert ficha(d, "2023-12-31", "academico", codigo, F.tema("claro"))


def test_dashboard_sin_datos(tmp_path):
    pytest.importorskip("dash")
    from finanzas_cr.dashboard.app import crear_app

    app = crear_app(tmp_path)
    assert "finanzas procesar" in str(app.layout)
