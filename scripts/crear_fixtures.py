"""Genera tests/fixtures/*.json con filas REALES de los informes de la UNA.

Uso (después de `finanzas descargar --serie ejecucion --formatos xlsx`):

    python scripts/crear_fixtures.py

Cada fixture guarda el bloque de títulos y encabezados de una hoja, algunas
filas de datos elegidas porque ilustran un caso del parser, y la fila de
TOTAL. Las fechas se guardan como {"$date": "AAAA-MM-DD"}.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import openpyxl

RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "data" / "raw" / "una" / "ejecucion"
DESTINO = RAIZ / "tests" / "fixtures"

# (nombre, archivo, hoja, filas 1-based a copiar, descripción)
CASOS = [
    ("una_2024_06_integrado", "2024/46606_*.xlsx", "integrado",
     [*range(1, 16), 22, 247, *range(254, 262)],
     "Formato detallado en colones; la fila 22 (Dietas) trae #REF!; luego empieza la copia en miles."),
    ("una_2018_06_academico", "2018/26214_*.xlsx", "academico", [*range(1, 15)],
     "Formato resumen en miles; el encabezado PARTIDA cubre código y nombre (columnas corridas)."),
    ("una_2022_12_academico", "2022/41771_*.xlsx", "academico", [*range(1, 14)],
     "Encabezados de enero y febrero como número de serie de Excel; cifras en miles; título con 'DICIEMRE'."),
    ("una_2025_06_integrado", "2025/49064_*.xlsx", "integrado", [*range(1, 11), 168, 169, 170, 172, 173],
     "Activos financieros: girado mensual de ₡22.487 M pero TOTAL GASTADO en 0 (inconsistencia del documento)."),
    ("una_2016_12_administrativo", "2016/25000_*.xlsx", "Administrativo", [*range(1, 14)],
     "Hoja sin la línea '(Cifras en miles de colones)'."),
    ("una_2019_06_academico", "2019/30938_*.xlsx", "academico", [*range(1, 14)],
     "Título 'CONSOLIDADO DE EGRESOS POR PROGRAMA / PROGRAMA ACADEMICO' y fecha de corte desactualizada (marzo)."),
]


def a_json(v):
    if isinstance(v, (dt.datetime, dt.date)):
        return {"$date": v.strftime("%Y-%m-%d")}
    return v


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nombre, patron, hoja, filas, descripcion in CASOS:
        ruta = next(RAW.glob(patron))
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        todas = list(wb[hoja].iter_rows(max_col=60, values_only=True))
        wb.close()
        datos = []
        for n in filas:
            fila = list(todas[n - 1])
            while fila and fila[-1] is None:
                fila.pop()
            datos.append([a_json(v) for v in fila])
        salida = {"descripcion": descripcion, "fuente": ruta.name, "hoja": hoja, "filas_excel": filas, "filas": datos}
        (DESTINO / f"{nombre}.json").write_text(json.dumps(salida, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"{nombre}.json  ({len(datos)} filas de {ruta.name})")


if __name__ == "__main__":
    main()
