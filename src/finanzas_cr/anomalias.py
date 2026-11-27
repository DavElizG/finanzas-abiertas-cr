"""Detección exploratoria de anomalías (Isolation Forest).

Compara cada subpartida al cierre de año contra el resto de subpartidas y
contra su propia historia. El puntaje indica qué tan *distinta* es una cuenta,
no si algo está mal. Requiere el extra `ml` (scikit-learn).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RASGOS = [
    "ejecucion",            # gastado / presupuesto total
    "variacion_relativa",   # variaciones / presupuesto inicial
    "peso_diciembre",       # girado en diciembre / girado anual
    "log_presupuesto",      # escala de la cuenta
    "cambio_interanual",    # presupuesto total vs año anterior (log)
]


PRESUPUESTO_MINIMO = 10_000_000  # ₡10 M: las cuentas pequeñas solo agregan ruido


def preparar(ejecucion: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (año, programa, subpartida) usando solo informes de cierre (diciembre).

    Se excluye el integrado porque es la suma de los otros tres programas.
    """
    df = ejecucion[(ejecucion["nivel"] == "subpartida") & (ejecucion["mes_corte"] == 12)
                   & (ejecucion["programa"] != "integrado")].copy()
    df = df[df["presupuesto_total"] >= PRESUPUESTO_MINIMO]
    if df.empty:
        return df
    df["ejecucion"] = (df["total_gastado"] / df["presupuesto_total"]).clip(-1, 3)
    base = df["presupuesto_inicial"].where(df["presupuesto_inicial"] > 0)
    df["variacion_relativa"] = (df["total_variaciones"] / base).clip(-3, 3).fillna(0)
    df["peso_diciembre"] = (df["girado_m12"] / df["girado"].where(df["girado"] > 0)).clip(0, 1).fillna(0)
    df["log_presupuesto"] = np.log10(df["presupuesto_total"].clip(lower=1))
    df = df.sort_values("anio")
    previo = df.groupby(["programa", "codigo"])["presupuesto_total"].shift(1)
    df["cambio_interanual"] = np.log10(df["presupuesto_total"] / previo).replace([np.inf, -np.inf], np.nan)
    df["cambio_interanual"] = df["cambio_interanual"].clip(-2, 2).fillna(0)
    return df


def puntuar(ejecucion: pd.DataFrame, contaminacion: float = 0.03, semilla: int = 42) -> pd.DataFrame:
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:  # pragma: no cover
        return pd.DataFrame()
    df = preparar(ejecucion)
    if len(df) < 50:
        return pd.DataFrame()
    X = df[RASGOS].to_numpy(dtype=float)
    modelo = IsolationForest(n_estimators=300, contamination=contaminacion, random_state=semilla)
    modelo.fit(X)
    df["puntaje_anomalia"] = -modelo.score_samples(X)  # mayor = más atípico
    df["atipico"] = modelo.predict(X) == -1
    columnas = ["anio", "corte", "programa", "codigo", "partida_nombre", "nombre",
                "presupuesto_total", "total_gastado", *RASGOS, "puntaje_anomalia", "atipico", "fuente_url"]
    return df[columnas].sort_values("puntaje_anomalia", ascending=False)
