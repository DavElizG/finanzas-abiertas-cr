"""Parser de los informes de ejecución presupuestaria de la UNA (Excel).

Cada libro trae una hoja por programa (integrado, académico, administrativo y
vida universitaria). El formato ha cambiado con los años, así que las columnas
se identifican por el texto del encabezado y no por su posición.

Formatos conocidos:

* Detallado (≈2021 en adelante): presupuesto inicial, recortes, 15
  modificaciones internas, 3 presupuestos extraordinarios, girado de cada mes,
  compromisos, total gastado y disponible. La tabla aparece dos veces en la
  hoja: primero en colones y luego en miles. Solo se lee la primera.
* Resumen (≈2018): presupuesto inicial, recortes, total, girado por trimestre,
  compromisos, gastado y disponible, en miles de colones. El encabezado
  "PARTIDA" cubre el código y el nombre, por lo que los encabezados numéricos
  quedan corridos una columna respecto a los datos.

Todas las cifras se normalizan a colones.
"""

from __future__ import annotations

import datetime as dt
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

PROGRAMAS = ("integrado", "academico", "administrativo", "vida_universitaria")

PARTIDAS = {
    "0": "Remuneraciones",
    "1": "Servicios",
    "2": "Materiales y suministros",
    "3": "Intereses y comisiones",
    "4": "Activos financieros",
    "5": "Bienes duraderos",
    "6": "Transferencias corrientes",
    "7": "Transferencias de capital",
    "8": "Amortización",
    "9": "Cuentas especiales",
}

CAMPOS_MONTO = [
    "presupuesto_inicial", "recortes", "total_modificaciones", "total_extraordinarios",
    "total_variaciones", "presupuesto_total", "girado", "compromisos", "total_gastado", "disponible",
]

_CODIGO = re.compile(r"^\s*(\d)[\s.\-]?(\d{2})[\s.\-]?(\d{2})\s*$")
_CORTE = re.compile(r"\bAL\s+(\d{1,2})\s+(?:DE\s+)?([A-Z]+)\s+(?:DE[L]?\s+)?(\d{4})")
_NUMERO = re.compile(r"NO\.?\s*(\d+)")
_ERROR_EXCEL = re.compile(r"^#(REF!|DIV/0!|VALUE!|N/A|NAME\?|NUM!|NULL!)")


def normalizar(texto) -> str:
    if texto is None:
        return ""
    if isinstance(texto, (dt.datetime, dt.date)):
        return texto.strftime("%Y-%m")
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().upper()


def codigo_de(valor) -> str | None:
    """'0 01 01' -> '0.01.01'."""
    if valor is None or isinstance(valor, (int, float)):
        return None
    m = _CODIGO.match(str(valor))
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else None


def nivel_de(codigo: str) -> str:
    _, g, s = codigo.split(".")
    if g == "00" and s == "00":
        return "partida"
    if s == "00":
        return "grupo"
    return "subpartida"


def padre_de(codigo: str) -> str | None:
    p, g, s = codigo.split(".")
    nivel = nivel_de(codigo)
    if nivel == "subpartida":
        return f"{p}.{g}.00"
    if nivel == "grupo":
        return f"{p}.00.00"
    return None


@dataclass
class ValorCelda:
    valor: float
    error: str | None = None


def leer_numero(v) -> ValorCelda:
    if v is None:
        return ValorCelda(0.0)
    if isinstance(v, bool):
        return ValorCelda(float(v))
    if isinstance(v, (int, float)):
        return ValorCelda(float(v)) if math.isfinite(v) else ValorCelda(math.nan, "no finito")
    s = str(v).strip()
    if s in ("", "-", "—"):
        return ValorCelda(0.0)
    if _ERROR_EXCEL.match(s):
        return ValorCelda(math.nan, s)
    try:
        return ValorCelda(float(s.replace(",", "")))
    except ValueError:
        return ValorCelda(math.nan, f"texto: {s[:30]}")


def clasificar_columna(etiqueta: str) -> tuple[str, int | str | None] | None:
    """Devuelve (campo, extra) para un encabezado normalizado, o None si no interesa."""
    e = etiqueta
    if not e:
        return None
    if "PRES. INICIAL" in e or "PRESUPUESTO INICIAL" in e:
        return ("presupuesto_inicial", None)
    if "RECORTES" in e:
        return ("recortes", None)
    if "TOT. MODIF" in e or ("MODIF" in e and "EXTRA" in e and "TOT" in e):
        return ("total_variaciones", None)
    if "PRESUP.EXT" in e or "PRES.EXT" in e or "EXTRAORD" in e:
        if e.startswith("TOTAL") or "TOTAL PRESUP.EXTR" in e:
            return ("total_extraordinarios", None)
        m = _NUMERO.search(e)
        return ("extraordinario", int(m.group(1)) if m else None)
    if "MOD.INTER" in e and "TOTAL" in e:
        return ("total_modificaciones", None)
    if "MODIF. INTER" in e or "MODIF.INTER" in e:
        m = _NUMERO.search(e)
        return ("modificacion", int(m.group(1)) if m else None)
    if "TOTAL PRESUP" in e or e == "TOTAL PRESUPUESTO":
        return ("presupuesto_total", None)
    if "GIRADO" in e:
        # "GIRADO ACUMULADO", "GIRADO SEMESTRAL", "ENERO A JUNIO" y "GIRADO AL 31-01-21"
        # son saldos a una fecha, no montos del mes.
        if "ACUMULADO" in e or "SEMESTRAL" in e or " A " in e or "GIRADO AL" in e or "TRIMESTRAL" in e:
            return None
        m = re.search(r"(\d{4})-(\d{2})", e)
        if m:
            return ("girado_mes", int(m.group(2)))
        return None  # formato resumen: trimestres ambiguos, se usa total gastado
    if "COMPROM" in e:
        return ("compromisos", None)
    if "GASTADO" in e:
        return ("total_gastado", None)
    if "DISPONIBLE" in e:
        return ("disponible", None)
    return None


def detectar_programa(textos: list[str], nombre_hoja: str = "") -> str | None:
    """Programa presupuestario de la hoja.

    Los títulos suelen decir "CONSOLIDADO DE EGRESOS POR PROGRAMA" y en la
    línea siguiente "PROGRAMA ACADEMICO", así que primero se buscan los
    programas específicos y solo después el integrado/consolidado.
    """
    candidatos = textos + [normalizar(nombre_hoja)]
    especificos = (
        ("academico", ("PROGRAMA ACADEMIC",)),
        ("administrativo", ("PROGRAMA ADMINISTRATIV", "DESARROLLO INSTITUCIONAL")),
        ("vida_universitaria", ("VIDA UNIVERS", "VIDA ESTUDIANTIL")),
    )
    for t in candidatos:
        for programa, claves in especificos:
            if any(k in t for k in claves):
                return programa
    for t in candidatos:
        if "INTEGRADO" in t or "CONSOLID" in t:
            return "integrado"
    hoja = normalizar(nombre_hoja)  # último recurso: el nombre de la hoja ("ACADEMICO", "EGRESOS ADM")
    for programa, claves in (("academico", ("ACAD",)), ("administrativo", ("ADMIN", "ADM")),
                             ("vida_universitaria", ("VIDA", "VU", "VID"))):
        if any(re.search(rf"\b{k}", hoja) for k in claves):
            return programa
    return None


def mes_de(palabra: str) -> int | None:
    """Mes por prefijo, tolerante a erratas reales ("DICIEMRE", "DEDICIEMBRE")."""
    p = palabra.upper()
    if p.startswith("DE") and len(p) > 6:  # "DEDICIEMBRE"
        p = p[2:]
    prefijos = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, "JUL": 7,
                "AGO": 8, "SET": 9, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12}
    return prefijos.get(p[:3])


def detectar_corte(textos: list[str]) -> dt.date | None:
    for t in textos:
        m = _CORTE.search(t)
        if m and mes_de(m.group(2)):
            anio, mes = int(m.group(3)), mes_de(m.group(2))
            dia = int(m.group(1))
            try:
                return dt.date(anio, mes, dia)
            except ValueError:  # p. ej. "31 de setiembre"
                siguiente = dt.date(anio + (mes == 12), mes % 12 + 1, 1)
                return siguiente - dt.timedelta(days=1)
    return None


def detectar_unidad(textos: list[str]) -> float | None:
    """Factor para pasar a colones según el título; None si la hoja no lo declara."""
    for t in textos:
        if re.search(r"MILES\s+DE\s+COLONES", t):
            return 1000.0
        if re.search(r"MILLONES\s+DE\s+COLONES", t):
            return 1_000_000.0
        if "COLONES" in t:
            return 1.0
    return None


@dataclass
class TablaEjecucion:
    programa: str
    corte: dt.date | None
    unidad: float
    formato: str
    filas: list[dict] = field(default_factory=list)
    modificaciones: list[dict] = field(default_factory=list)
    total_documento: dict | None = None
    errores_celda: list[dict] = field(default_factory=list)
    hoja: str = ""
    unidad_inferida: bool = False


def parsear_filas(filas: list[tuple], nombre_hoja: str = "", unidad_defecto: float | None = None) -> TablaEjecucion | None:
    """Convierte las filas crudas de una hoja en una TablaEjecucion (o None si no es de ejecución).

    `unidad_defecto` se usa cuando el título no dice si las cifras están en
    colones o en miles; en ese caso `unidad_inferida` queda en True.
    """
    # 1. Encabezado
    fila_enc = None
    for i, fila in enumerate(filas[:40]):
        if any(normalizar(v).startswith(("PRES. INICIAL", "PRESUPUESTO INICIAL")) for v in fila):
            fila_enc = i
            break
    if fila_enc is None:
        return None

    titulos = [normalizar(f[0]) for f in filas[:fila_enc] if f and f[0] is not None]
    programa = detectar_programa(titulos, nombre_hoja)
    if programa is None:
        return None
    corte = detectar_corte(titulos)
    unidad = detectar_unidad(titulos)
    unidad_inferida = unidad is None
    if unidad is None:
        unidad = unidad_defecto if unidad_defecto is not None else 1.0

    # 2. Columna del código: la primera columna con códigos en las filas siguientes
    col_codigo = None
    for fila in filas[fila_enc + 1: fila_enc + 15]:
        for j, v in enumerate(fila[:4]):
            if codigo_de(v):
                col_codigo = j
                break
        if col_codigo is not None:
            break
    if col_codigo is None:
        return None
    col_nombre = col_codigo + 1

    # 3. Etiquetas por columna (fila anterior, encabezado y subencabezado)
    enc = filas[fila_enc]
    ancho = max(len(f) for f in filas[max(0, fila_enc - 1): fila_enc + 2])
    sub = filas[fila_enc + 1] if fila_enc + 1 < len(filas) else ()
    sub_es_dato = len(sub) > col_codigo and codigo_de(sub[col_codigo]) is not None
    previa = filas[fila_enc - 1] if fila_enc > 0 else ()

    def celda(f, j):
        return f[j] if j < len(f) else None

    def etiqueta(v):
        # Algunas fechas de encabezado llegan como número de serie de Excel (p. ej. 44562 = 2022-01-01)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and 36000 < v < 60000:
            return normalizar(dt.date(1899, 12, 30) + dt.timedelta(days=int(v)))
        return normalizar(v)

    etiquetas = []
    for j in range(ancho):
        partes = []
        if j >= 2:
            partes.append(etiqueta(celda(previa, j)))
        partes.append(etiqueta(celda(enc, j)))
        if not sub_es_dato:
            partes.append(etiqueta(celda(sub, j)))
        etiquetas.append(" ".join(p for p in partes if p))

    col_inicial = next(j for j, e in enumerate(etiquetas) if clasificar_columna(e) == ("presupuesto_inicial", None))
    desfase = (col_nombre + 1) - col_inicial
    formato = "detallado" if any("MODIF. INTER" in e for e in etiquetas) else "resumen"

    mapa: dict[int, tuple[str, object]] = {}
    vistos: set[str] = set()
    for j, e in enumerate(etiquetas):
        c = clasificar_columna(e)
        if c is None:
            continue
        campo, extra = c
        if campo in ("modificacion", "extraordinario", "girado_mes"):
            mapa[j + desfase] = (campo, extra)
        elif campo not in vistos:  # solo la primera aparición (p. ej. "disponible")
            vistos.add(campo)
            mapa[j + desfase] = (campo, extra)

    # 4. Filas de datos
    tabla = TablaEjecucion(programa=programa, corte=corte, unidad=unidad, formato=formato, hoja=nombre_hoja,
                           unidad_inferida=unidad_inferida)
    inicio = fila_enc + (1 if sub_es_dato else 2)
    for i in range(inicio, len(filas)):
        fila = filas[i]
        c0 = normalizar(celda(fila, col_codigo))
        if c0.startswith("TOTAL"):
            tabla.total_documento = _leer_montos(fila, mapa, unidad, i, tabla, codigo="TOTAL")[0]
            break
        if c0 == "UNIVERSIDAD NACIONAL":  # empieza la copia en miles
            break
        codigo = codigo_de(celda(fila, col_codigo))
        if not codigo:
            continue
        montos, mods = _leer_montos(fila, mapa, unidad, i, tabla, codigo=codigo)
        nombre = str(celda(fila, col_nombre) or "").strip()
        registro = {
            "programa": programa,
            "codigo": codigo,
            "nivel": nivel_de(codigo),
            "partida": codigo[0],
            "partida_nombre": PARTIDAS.get(codigo[0], ""),
            "padre": padre_de(codigo),
            "nombre": nombre,
            "fila_excel": i + 1,
            **montos,
        }
        tabla.filas.append(registro)
        for m in mods:
            tabla.modificaciones.append({"programa": programa, "codigo": codigo, "nivel": registro["nivel"],
                                         "nombre": nombre, **m})
    return tabla


def _leer_montos(fila, mapa, unidad, i, tabla: TablaEjecucion, codigo: str):
    montos = {c: 0.0 for c in CAMPOS_MONTO}
    girado_mes = {m: 0.0 for m in range(1, 13)}
    hay_girado_mes = False
    mods = []
    for j, (campo, extra) in mapa.items():
        v = leer_numero(fila[j] if j < len(fila) else None)
        if v.error:
            tabla.errores_celda.append({"programa": tabla.programa, "codigo": codigo, "fila_excel": i + 1,
                                        "columna_excel": j + 1, "campo": campo, "valor": v.error})
            valor = math.nan
        else:
            valor = v.valor * unidad
        if campo == "girado_mes":
            girado_mes[int(extra)] = valor
            hay_girado_mes = True
        elif campo in ("modificacion", "extraordinario"):
            if math.isnan(valor) or abs(valor) >= 0.5:  # se ignoran residuos de redondeo
                mods.append({"tipo": "interna" if campo == "modificacion" else "extraordinario",
                             "numero": extra, "monto": valor})
        else:
            montos[campo] = valor
    if hay_girado_mes:
        montos["girado"] = sum(v for v in girado_mes.values() if not math.isnan(v))
    else:
        g = montos["total_gastado"] - montos["compromisos"]
        montos["girado"] = g
    for m, v in girado_mes.items():
        montos[f"girado_m{m:02d}"] = v if hay_girado_mes else math.nan
    return montos, mods


def leer_libro(ruta: Path) -> list[TablaEjecucion]:
    """Lee todas las hojas de ejecución por programa de un libro de Excel."""
    import openpyxl

    from collections import Counter

    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    hojas: list[tuple[str, list[tuple]]] = []
    try:
        for ws in wb.worksheets:
            # Vistazo rápido: ¿es una hoja de ejecución por programa?
            cabeza = list(ws.iter_rows(min_row=1, max_row=25, max_col=12, values_only=True))
            texto = " ".join(normalizar(v) for f in cabeza for v in f if v is not None)
            if "INICIAL" in texto:
                hojas.append((ws.title, list(ws.iter_rows(max_col=70, values_only=True))))
    finally:
        wb.close()

    leidas = [(nombre, filas, parsear_filas(filas, nombre)) for nombre, filas in hojas]
    # Hojas que no declaran la unidad: se asume la más común del mismo libro
    declaradas = Counter(t.unidad for _, _, t in leidas if t and t.filas and not t.unidad_inferida)
    defecto = declaradas.most_common(1)[0][0] if declaradas else None
    tablas: dict[str, TablaEjecucion] = {}
    for nombre, filas, t in leidas:
        if t is not None and t.unidad_inferida and defecto is not None:
            t = parsear_filas(filas, nombre, unidad_defecto=defecto)
        if t is None or not t.filas:
            continue
        # Varias hojas por programa (p. ej. en la liquidación: «conformación» con el gasto en 0 y
        # «ejecución» con el gasto): manda la que trae gasto y, a igualdad, la que tiene más cuentas.
        previa = tablas.get(t.programa)
        if previa is None or prioridad(t) > prioridad(previa):
            tablas[t.programa] = t
    return [tablas[p] for p in PROGRAMAS if p in tablas]


def prioridad(t: TablaEjecucion) -> tuple[bool, int]:
    tiene_gasto = any(abs(f["total_gastado"]) > 0 for f in t.filas if f["total_gastado"] == f["total_gastado"])
    return tiene_gasto, len(t.filas)
