"""Configuración: fuentes, series y rutas del proyecto."""

from __future__ import annotations

import os
from pathlib import Path

# Raíz del repositorio (src/finanzas_cr/config.py -> ../../)
RAIZ = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("FINANZAS_DATA", RAIZ / "data"))
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
MANIFEST = DATA / "manifest"

# Repositorio DSpace 6 de la Universidad Nacional
UNA_BASE_URL = "https://documentos.una.ac.cr"
UNA_REST = f"{UNA_BASE_URL}/rest"

# Pausa entre solicitudes al servidor (segundos). Es un servidor institucional: sé amable.
PAUSA_SEGUNDOS = float(os.environ.get("FINANZAS_PAUSA", "1.0"))

# User-Agent genérico; se puede cambiar con la variable de entorno.
USER_AGENT = os.environ.get("FINANZAS_USER_AGENT", "open-data-client/0.1 (datos financieros publicos)")

# Comunidades de "Información Financiera" (Programa de Gestión Financiera, comunidad 369).
# Cada comunidad contiene una colección por año.
SERIES_UNA: dict[str, dict] = {
    "estados_auditados": {"comunidad": 371, "titulo": "Estados financieros auditados"},
    "estados_mensuales": {"comunidad": 372, "titulo": "Estados financieros no auditados (mensuales)"},
    "presupuesto_ordinario": {"comunidad": 373, "titulo": "Presupuesto ordinario"},
    "proyecto_presupuesto": {"comunidad": 473, "titulo": "Proyecto de presupuesto ordinario"},
    "ejecucion": {"comunidad": 375, "titulo": "Ejecución presupuestaria"},
    "liquidacion": {"comunidad": 376, "titulo": "Liquidación presupuestaria"},
    "extraordinarios": {"comunidad": 374, "titulo": "Presupuestos extraordinarios"},
    "activos_inmuebles": {"comunidad": 377, "titulo": "Activos inmuebles"},
    "alquileres": {"comunidad": 378, "titulo": "Alquileres"},
    "auditoria_liquidacion": {"comunidad": 677, "titulo": "Auditoría externa de la liquidación"},
}

# Formatos por extensión de archivo
FORMATOS = {
    "xlsx": (".xlsx", ".xlsm", ".xls"),
    "pdf": (".pdf",),
    "zip": (".zip",),
}
