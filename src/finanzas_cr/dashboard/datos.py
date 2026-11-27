"""Carga y agregaciones del dashboard (sin dependencias de Dash, para poder probarlas)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .. import config
from ..etl.ejecucion import PARTIDAS

PROGRAMAS = {
    "integrado": "Toda la universidad (integrado)",
    "academico": "Programa académico",
    "administrativo": "Programa administrativo",
    "vida_universitaria": "Vida universitaria",
}

SENALES = {
    "gasto_sin_presupuesto": "Gasto sin presupuesto",
    "sobregiro": "Sobregiro",
    "modificacion_alta": "Modificación alta (>50 %)",
    "creada_por_modificacion": "Creada por modificación",
    "subejecucion": "Subejecución al cierre (<50 %)",
    "concentracion_diciembre": "Gasto concentrado en diciembre",
}

REGLAS = {
    "identidad_presupuesto": "Inicial + variaciones ≠ total",
    "identidad_gasto": "Girado + compromisos ≠ gastado",
    "identidad_disponible": "Total − gastado ≠ disponible",
    "suma_modificaciones": "Detalle de modificaciones ≠ total",
    "suma_extraordinarios": "Detalle de extraordinarios ≠ total",
    "suma_variaciones": "Modificaciones + extraordinarios ≠ variaciones",
    "jerarquia": "Subcuentas no suman a la cuenta",
    "total_documento": "Partidas no suman al TOTAL del documento",
    "suma_programas": "Programas no suman al integrado",
    "error_celda": "Celda con error de Excel (#REF!)",
    "metadatos": "Fecha, unidad o nombre inconsistentes",
    "duplicado": "Documento duplicado",
    "lectura": "No se pudo leer",
}


@dataclass
class Datos:
    ejecucion: pd.DataFrame
    senales: pd.DataFrame
    validacion: pd.DataFrame
    anomalias: pd.DataFrame
    modificaciones: pd.DataFrame

    @property
    def vacio(self) -> bool:
        return self.ejecucion.empty


def _leer(ruta: Path) -> pd.DataFrame:
    if not ruta.exists() or ruta.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(ruta, dtype={"codigo": str, "partida": str})
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def cargar(carpeta: Path | None = None) -> Datos:
    carpeta = carpeta or config.PROCESSED / "una"
    return Datos(
        ejecucion=_leer(carpeta / "ejecucion.csv"),
        senales=_leer(carpeta / "senales.csv"),
        validacion=_leer(carpeta / "validacion.csv"),
        anomalias=_leer(carpeta / "anomalias.csv"),
        modificaciones=_leer(carpeta / "modificaciones.csv"),
    )


def informe_por_anio(ej: pd.DataFrame) -> pd.DataFrame:
    """Un informe por año: el de cierre (diciembre) o, si no hay, el último disponible."""
    cortes = ej[["anio", "corte", "bitstream_id", "fuente_url"]].drop_duplicates("corte")
    cortes = cortes.sort_values("corte")
    elegido = cortes.groupby("anio").tail(1).copy()
    elegido["es_cierre"] = pd.to_datetime(elegido["corte"]).dt.month == 12
    return elegido.sort_values("anio", ascending=False).reset_index(drop=True)


def filas_informe(d: Datos, corte: str, programa: str) -> pd.DataFrame:
    e = d.ejecucion
    return e[(e["corte"] == corte) & (e["programa"] == programa)]


def por_partida(filas: pd.DataFrame) -> pd.DataFrame:
    p = filas[filas["nivel"] == "partida"].copy()
    p["partida_nombre"] = p["partida"].map(PARTIDAS)
    p["variaciones"] = p["recortes"] + p["total_variaciones"]
    p = p[(p["presupuesto_total"].abs() > 0) | (p["total_gastado"].abs() > 0) | (p["variaciones"].abs() > 0)]
    return p


def serie_anual(d: Datos, programa: str) -> pd.DataFrame:
    """Presupuesto y gasto al cierre de cada año (solo informes de diciembre)."""
    e = d.ejecucion
    p = e[(e["programa"] == programa) & (e["nivel"] == "partida") & (e["mes_corte"] == 12)]
    s = p.groupby(["anio", "corte"], as_index=False)[["presupuesto_inicial", "presupuesto_total", "total_gastado"]].sum()
    s = s.sort_values("corte").groupby("anio").tail(1)
    todos = pd.DataFrame({"anio": range(int(e["anio"].min()), int(e["anio"].max()) + 1)})
    return todos.merge(s, on="anio", how="left")


def girado_mensual(filas: pd.DataFrame) -> pd.DataFrame | None:
    p = filas[filas["nivel"] == "partida"]
    columnas = [f"girado_m{m:02d}" for m in range(1, 13)]
    if p.empty or p[columnas].isna().all().all():
        return None
    meses = p[columnas].sum(min_count=1)
    return pd.DataFrame({"mes": range(1, 13), "girado": meses.values})


def colones_m(x: float | None) -> str:
    """₡ en millones con formato costarricense: ₡12.345 M."""
    if x is None or pd.isna(x):
        return "—"
    return f"₡{x / 1e6:,.0f} M".replace(",", ".")


def porcentaje(x: float | None) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x * 100:.1f} %".replace(".", ",")
