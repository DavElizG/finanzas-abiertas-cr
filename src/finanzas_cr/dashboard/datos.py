"""Carga, agregaciones y textos del dashboard (sin dependencias de Dash, para poder probarlos)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .. import config
from ..etl.ejecucion import PARTIDAS

PROGRAMAS = {
    "integrado": "Toda la universidad",
    "academico": "Programa académico",
    "administrativo": "Programa administrativo",
    "vida_universitaria": "Vida universitaria",
}
PROGRAMAS_CORTOS = {"academico": "Académico", "administrativo": "Administrativo", "vida_universitaria": "Vida universitaria"}

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]
MESES_LARGOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "setiembre",
                "octubre", "noviembre", "diciembre"]

SENALES = {
    "gasto_sin_presupuesto": ("Gasto sin presupuesto", "Se gastó en una cuenta que no tenía presupuesto asignado."),
    "sobregiro": ("Sobregiro", "Se gastó más de lo que la cuenta tenía presupuestado."),
    "modificacion_alta": ("Cambio grande al presupuesto", "Durante el año, la cuenta subió o bajó más de la mitad de "
                          "lo que se aprobó al inicio."),
    "creada_por_modificacion": ("Cuenta creada sobre la marcha", "No tenía presupuesto inicial y se financió con "
                                "modificaciones durante el año."),
    "subejecucion": ("Poco ejecutado al cierre", "Al terminar el año se había gastado menos de la mitad de lo "
                     "presupuestado."),
    "concentracion_diciembre": ("Gasto concentrado en diciembre", "Más del 30 % de lo girado en el año se pagó en "
                                "diciembre."),
}

REGLAS = {
    "identidad_presupuesto": "Inicial + cambios ≠ presupuesto total",
    "identidad_gasto": "Pagado + comprometido ≠ gastado",
    "identidad_disponible": "Presupuesto − gastado ≠ disponible",
    "suma_modificaciones": "Detalle de modificaciones ≠ su total",
    "suma_extraordinarios": "Detalle de extraordinarios ≠ su total",
    "suma_variaciones": "Modificaciones + extraordinarios ≠ cambios",
    "jerarquia": "Las subcuentas no suman a la cuenta",
    "total_documento": "Las partidas no suman al total del documento",
    "suma_programas": "Los programas no suman al total de la universidad",
    "error_celda": "Celda con error de Excel (#REF!)",
    "metadatos": "Fecha, unidad o nombre inconsistentes",
    "duplicado": "Documento duplicado",
    "lectura": "No se pudo leer el archivo",
    "liquidacion_vs_ejecucion": "La liquidación no coincide con el informe de diciembre",
}

GLOSARIO = [
    ("Presupuesto inicial", "Lo que se aprobó para el año antes de empezar."),
    ("Modificación interna", "Un traslado de dinero entre cuentas durante el año. No agrega plata nueva: lo que "
                             "una cuenta recibe, otra lo cede."),
    ("Presupuesto extraordinario", "Dinero nuevo que se agrega durante el año (o que se rebaja), aprobado aparte."),
    ("Presupuesto total", "El inicial más todos los cambios del año. Es el límite de lo que se puede gastar."),
    ("Girado", "Lo que efectivamente se pagó."),
    ("Comprometido", "Lo que ya está contratado pero todavía no se ha pagado."),
    ("Ejecutado (gastado)", "Girado + comprometido."),
    ("Partida → grupo → subpartida", "Los tres niveles del clasificador por objeto del gasto de Hacienda, de lo "
                                     "general (p. ej. Servicios) a lo específico (p. ej. Servicios de limpieza)."),
]


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
        return pd.read_csv(ruta, dtype={"codigo": str, "partida": str, "padre": str})
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def cargar(carpeta: Path | None = None) -> Datos:
    carpeta = carpeta or config.PROCESSED / "una"
    ej = _leer(carpeta / "ejecucion.csv")
    if not ej.empty:
        if "documento" not in ej:  # CSV generados antes de incluir la liquidación
            ej["documento"] = "informe de ejecución"
        ej["nombre_corto"] = [nombre_cuenta(c, n) for c, n in zip(ej["codigo"], ej["nombre"])]
    return Datos(
        ejecucion=ej,
        senales=_leer(carpeta / "senales.csv"),
        validacion=_leer(carpeta / "validacion.csv"),
        anomalias=_leer(carpeta / "anomalias.csv"),
        modificaciones=_leer(carpeta / "modificaciones.csv"),
    )


# --- Formato ------------------------------------------------------------------

def nombre_cuenta(codigo: str, nombre: str) -> str:
    """Nombre legible: las partidas usan el clasificador; los MAYÚSCULOS pasan a oración."""
    if codigo and codigo.endswith(".00.00") and codigo[0] in PARTIDAS:
        return PARTIDAS[codigo[0]]
    nombre = str(nombre or "").strip()
    if nombre.isupper():
        nombre = nombre.capitalize()
    return nombre or codigo


def _num(x: float, decimales: int) -> str:
    return f"{x:,.{decimales}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def dinero(x: float | None) -> str:
    """₡ legible: ₡156,7 mil millones · ₡845 millones · ₡12.345."""
    if x is None or pd.isna(x):
        return "—"
    s = "−" if x < 0 else ""
    a = abs(x)
    if a >= 1e9:
        return f"{s}₡{_num(a / 1e9, 1)} mil millones"
    if a >= 1e6:
        return f"{s}₡{_num(a / 1e6, 0 if a >= 1e8 else 1)} millones"
    return f"{s}₡{_num(a, 0)}"


def colones_m(x: float | None) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"₡{_num(x / 1e6, 0)} M"


def porcentaje(x: float | None, decimales: int = 1) -> str:
    if x is None or pd.isna(x):
        return "—"
    texto = _num(x * 100, decimales)
    return f"{texto.lstrip('-') if texto.strip('-0,') == '' else texto} %"  # sin «-0 %»


def fecha_larga(corte: str) -> str:
    a, m, d = corte.split("-")
    return f"{int(d)} de {MESES_LARGOS[int(m) - 1]} de {a}"


# --- Selección de informes ----------------------------------------------------

def informe_por_anio(ej: pd.DataFrame) -> pd.DataFrame:
    """Un informe por año: el de cierre (diciembre) o, si no hay, el último disponible."""
    columnas = ["anio", "corte", "bitstream_id", "fuente_url"] + (["documento"] if "documento" in ej else [])
    cortes = ej[columnas].drop_duplicates("corte").sort_values("corte")
    elegido = cortes.groupby("anio").tail(1).copy()
    elegido["es_cierre"] = pd.to_datetime(elegido["corte"]).dt.month == 12
    return elegido.sort_values("anio", ascending=False).reset_index(drop=True)


def nombre_documento(documento: str | None) -> str:
    return "Liquidación presupuestaria" if documento == "liquidación" else "Informe de ejecución"


def es_cierre(corte: str) -> bool:
    return corte[5:7] == "12"


def filas_informe(d: Datos, corte: str, programa: str) -> pd.DataFrame:
    e = d.ejecucion
    return e[(e["corte"] == corte) & (e["programa"] == programa)]


# --- Agregaciones -------------------------------------------------------------

def por_partida(filas: pd.DataFrame) -> pd.DataFrame:
    p = filas[filas["nivel"] == "partida"].copy()
    p["partida_nombre"] = p["partida"].map(PARTIDAS)
    p["variaciones"] = p["recortes"] + p["total_variaciones"]
    p = p[(p["presupuesto_total"].abs() > 0) | (p["total_gastado"].abs() > 0) | (p["variaciones"].abs() > 0)]
    return p


def composicion(filas: pd.DataFrame) -> pd.DataFrame:
    """Cuánto de cada ₡100 del presupuesto total va a cada partida."""
    p = por_partida(filas)
    p = p[p["presupuesto_total"] > 0].copy()
    total = p["presupuesto_total"].sum()
    p["de_cada_100"] = 100 * p["presupuesto_total"] / total if total else 0
    p["ejecucion"] = p["total_gastado"] / p["presupuesto_total"]
    return p.sort_values("presupuesto_total", ascending=False)


def hijos(filas: pd.DataFrame, codigo: str | None) -> pd.DataFrame:
    """Cuentas hijas de `codigo` (o las partidas si es None)."""
    if codigo is None:
        return filas[filas["nivel"] == "partida"]
    return filas[filas["padre"] == codigo]


def ruta_cuenta(codigo: str) -> list[str]:
    """'0.01.05' -> ['0.00.00', '0.01.00', '0.01.05']."""
    p, g, s = codigo.split(".")
    ruta = [f"{p}.00.00"]
    if g != "00":
        ruta.append(f"{p}.{g}.00")
    if s != "00":
        ruta.append(codigo)
    return ruta


def arbol(filas: pd.DataFrame) -> pd.DataFrame:
    """Nodos para un treemap: las hojas llevan su presupuesto; los padres suman a sus hijos."""
    f = filas[filas["presupuesto_total"] > 0].copy()
    padres = set(f["padre"].dropna())
    f["hoja"] = ~f["codigo"].isin(padres)
    f["valor"] = f["presupuesto_total"].where(f["hoja"], 0.0)
    f["padre_id"] = f["padre"].fillna("TOTAL")
    f["ejecucion"] = (f["total_gastado"] / f["presupuesto_total"]).clip(0, 1.5)
    return f


def serie_anual(d: Datos, programa: str, codigo: str | None = None) -> pd.DataFrame:
    """Presupuesto y ejecutado por año (el informe de cierre o, si no hay, el último del año)."""
    e = d.ejecucion
    base = e[e["programa"] == programa]
    base = base[base["nivel"] == "partida"] if codigo is None else base[base["codigo"] == codigo]
    s = base.groupby(["anio", "corte"], as_index=False)[
        ["presupuesto_inicial", "presupuesto_total", "total_gastado"]].sum()
    s = s.sort_values("corte").groupby("anio").tail(1)
    s["es_cierre"] = s["corte"].map(es_cierre)
    todos = pd.DataFrame({"anio": range(int(e["anio"].min()), int(e["anio"].max()) + 1)})
    return todos.merge(s, on="anio", how="left")


def girado_mensual(filas: pd.DataFrame, codigo: str | None = None) -> pd.DataFrame | None:
    p = filas[filas["nivel"] == "partida"] if codigo is None else filas[filas["codigo"] == codigo]
    columnas = [f"girado_m{m:02d}" for m in range(1, 13)]
    if p.empty or p[columnas].isna().all().all():
        return None
    meses = p[columnas].sum(min_count=1)
    return pd.DataFrame({"mes": range(1, 13), "girado": meses.values})


def comparar_programas(d: Datos, corte: str) -> pd.DataFrame:
    e = d.ejecucion
    p = e[(e["corte"] == corte) & (e["nivel"] == "partida") & (e["programa"] != "integrado")]
    s = p.groupby("programa", as_index=False)[["presupuesto_total", "total_gastado"]].sum()
    s["nombre"] = s["programa"].map(PROGRAMAS_CORTOS)
    s["ejecucion"] = s["total_gastado"] / s["presupuesto_total"]
    return s.sort_values("presupuesto_total")


def mapa_ejecucion(d: Datos, programa: str) -> pd.DataFrame:
    """Partida × año → % ejecutado, usando solo informes de cierre."""
    e = d.ejecucion
    p = e[(e["programa"] == programa) & (e["nivel"] == "partida") & (e["mes_corte"] == 12)]
    p = p[p["presupuesto_total"] > 0]
    p = p.sort_values("corte").groupby(["anio", "partida"]).tail(1)
    p = p.assign(ejecucion=p["total_gastado"] / p["presupuesto_total"], nombre=p["partida"].map(PARTIDAS))
    return p.pivot_table(index="nombre", columns="anio", values="ejecucion")


def modificaciones_informe(d: Datos, corte: str, programa: str) -> pd.DataFrame:
    """Por cada modificación: cuánto recibieron y cuánto cedieron las subpartidas."""
    m = d.modificaciones
    if m.empty:
        return m
    m = m[(m["corte"] == corte) & (m["programa"] == programa) & (m["nivel"] == "subpartida")]
    g = m.groupby(["tipo", "numero"], as_index=False)["monto"].agg(
        recibio=lambda s: s[s > 0].sum(), cedio=lambda s: s[s < 0].sum(), cuentas="count")
    g["etiqueta"] = [etiqueta_mod(t, n) for t, n in zip(g["tipo"], g["numero"])]
    return g.sort_values(["tipo", "numero"], ascending=[False, True])


def etiqueta_mod(tipo: str, numero) -> str:
    base = "Mod." if tipo == "interna" else "Extra."
    return f"{base} {int(numero)}" if pd.notna(numero) else base


def mayores_cambios(filas: pd.DataFrame, n: int = 8) -> pd.DataFrame:
    """Subpartidas que más recibieron y más cedieron durante el año."""
    f = filas[filas["nivel"] == "subpartida"].copy()
    f["cambio"] = f["recortes"] + f["total_variaciones"]
    f = f[f["cambio"].abs() >= 1e6]
    return pd.concat([f.nlargest(n, "cambio"), f.nsmallest(n, "cambio")]).drop_duplicates("codigo") \
        .sort_values("cambio")


def modificaciones_cuenta(d: Datos, corte: str, programa: str, codigo: str) -> pd.DataFrame:
    m = d.modificaciones
    if m.empty:
        return m
    m = m[(m["corte"] == corte) & (m["programa"] == programa) & (m["codigo"] == codigo)].copy()
    m["etiqueta"] = [etiqueta_mod(t, n) for t, n in zip(m["tipo"], m["numero"])]
    return m


def senales_de(d: Datos, corte: str, programa: str, codigo: str | None = None) -> pd.DataFrame:
    s = d.senales
    if s.empty:
        return s
    s = s[(s["corte"] == corte) & (s["programa"] == programa)]
    if codigo is not None:
        s = s[s["codigo"].astype(str).str.startswith(prefijo(codigo))]
    return s


def prefijo(codigo: str) -> str:
    """Prefijo que comparten una cuenta y sus descendientes: '0.01.00' -> '0.01.'."""
    p, g, s = codigo.split(".")
    if g == "00":
        return f"{p}."
    if s == "00":
        return f"{p}.{g}."
    return codigo


def resumen_senales(s: pd.DataFrame) -> pd.DataFrame:
    if s.empty:
        return pd.DataFrame(columns=["senal", "cuentas", "monto"])
    g = s.groupby("senal", as_index=False).agg(cuentas=("codigo", "count"), monto=("monto", lambda x: x.abs().sum()))
    orden = list(SENALES)
    g["orden"] = g["senal"].map(orden.index)
    return g.sort_values("orden")


# --- Narrativa ----------------------------------------------------------------

def narrativa(d: Datos, corte: str, programa: str) -> list[str]:
    """Frases en lenguaje llano que resumen el informe seleccionado."""
    filas = filas_informe(d, corte, programa)
    comp = composicion(filas)
    if comp.empty:
        return ["No hay datos para esta selección."]
    pres, gas = comp["presupuesto_total"].sum(), comp["total_gastado"].sum()
    inicial = comp["presupuesto_inicial"].sum()
    quien = {"integrado": "la Universidad Nacional", "academico": "el programa académico",
             "administrativo": "el programa administrativo",
             "vida_universitaria": "el programa de vida universitaria"}[programa]
    frases = []
    documento = filas["documento"].iloc[0] if "documento" in filas and not filas.empty else ""
    if es_cierre(corte):
        frases.append(f"En {corte[:4]}, {quien} tuvo un presupuesto de {dinero(pres)} y ejecutó "
                      f"{dinero(gas)}, es decir, {porcentaje(gas / pres, 0)} de lo disponible.")
        if documento == "liquidación":
            frases.append(f"Para {corte[:4]} no hay informe de ejecución de diciembre en Excel; las cifras salen "
                          "de la liquidación presupuestaria, el cierre oficial del año.")
    else:
        frases.append(f"Al {fecha_larga(corte)}, {quien} tenía un presupuesto de {dinero(pres)} para el año y "
                      f"había ejecutado {dinero(gas)} ({porcentaje(gas / pres, 0)}). El año todavía no había cerrado.")
    top = comp.iloc[0]
    frases.append(f"{top['partida_nombre']} se lleva ₡{_num(top['de_cada_100'], 0)} de cada ₡100 del presupuesto.")
    if inicial:
        cambio = pres - inicial
        if abs(cambio) / inicial >= 0.005:
            frases.append(f"Durante el año el presupuesto {'creció' if cambio > 0 else 'bajó'} "
                          f"{dinero(abs(cambio))} respecto a lo aprobado al inicio ({dinero(inicial)}).")
    mods = modificaciones_informe(d, corte, programa)
    internas = mods[mods["tipo"] == "interna"] if not mods.empty else mods
    if not internas.empty:
        movido = internas["recibio"].sum()
        frases.append(f"Con {len(internas)} modificaciones internas se trasladaron {dinero(movido)} de unas "
                      f"cuentas a otras.")
    s = senales_de(d, corte, programa)
    if not s.empty:
        frases.append(f"Hay {len(s)} señales para revisar en {s['codigo'].nunique()} cuentas. "
                      "Son preguntas, no conclusiones.")
    return frases
