import datetime as dt
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _desde_json(v):
    if isinstance(v, dict) and "$date" in v:
        return dt.datetime.strptime(v["$date"], "%Y-%m-%d")
    return v


def cargar_filas(nombre: str) -> list[tuple]:
    """Filas reales de un informe de la UNA (ver scripts/crear_fixtures.py)."""
    datos = json.loads((FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))
    return [tuple(_desde_json(v) for v in fila) for fila in datos["filas"]]


@pytest.fixture
def filas():
    return cargar_filas
