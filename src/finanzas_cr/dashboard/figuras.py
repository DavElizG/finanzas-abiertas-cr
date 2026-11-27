"""Gráficos del dashboard.

Reglas (skill dataviz): una sola escala por gráfico, colores por entidad
(presupuesto = azul, ejecutado = naranja) que no cambian entre vistas, escala
secuencial de un solo tono para magnitudes y divergente azul/rojo con centro
neutro para «recibió / cedió». Las cifras van en el hover y en tablas, no
encima de cada marca.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from . import datos as D

TEMAS = {
    "claro": {
        "superficie": "#fcfcfb", "tinta": "#0b0b0b", "tinta2": "#52514e", "tenue": "#898781",
        "rejilla": "#e1e0d9", "base": "#c3c2b7", "neutro": "#f0efec",
        "presupuesto": "#2a78d6", "gastado": "#eb6834", "sube": "#2a78d6", "baja": "#e34948",
        # secuencial azul (100 → 700): poco → mucho
        "secuencial": ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"],
    },
    "oscuro": {
        "superficie": "#1a1a19", "tinta": "#f0efec", "tinta2": "#c3c2b7", "tenue": "#898781",
        "rejilla": "#2c2c2a", "base": "#383835", "neutro": "#383835",
        "presupuesto": "#3987e5", "gastado": "#d95926", "sube": "#3987e5", "baja": "#e66767",
        # en oscuro «mucho» es más claro (más contraste con la superficie)
        "secuencial": ["#104281", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"],
    },
}
FUENTE = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def tema(nombre: str | None) -> dict:
    return TEMAS.get(nombre or "claro", TEMAS["claro"])


def tinta_sobre(hexa: str) -> str:
    """Negro o blanco, lo que contraste más con el relleno (luminancia relativa WCAG)."""
    r, g, b = (int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    lum = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    return "#0b0b0b" if (lum + 0.05) / 0.05 > 1.05 / (lum + 0.05) else "#ffffff"


def escala(t: dict) -> list[list]:
    pasos = t["secuencial"]
    return [[i / (len(pasos) - 1), c] for i, c in enumerate(pasos)]


def base(fig: go.Figure, t: dict, alto: int = 340, leyenda: bool = True) -> go.Figure:
    fig.update_layout(
        height=alto, margin=dict(l=8, r=16, t=28 if leyenda else 8, b=8),
        paper_bgcolor=t["superficie"], plot_bgcolor=t["superficie"],
        font=dict(family=FUENTE, color=t["tinta2"], size=13), separators=",.",
        barcornerradius=4, bargap=0.35, bargroupgap=0.12, showlegend=leyenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(color=t["tinta2"])),
        hoverlabel=dict(bgcolor=t["superficie"], bordercolor=t["base"], font=dict(color=t["tinta"], family=FUENTE)),
        clickmode="event",
    )
    eje = dict(gridcolor=t["rejilla"], linecolor=t["base"], zerolinecolor=t["base"], tickfont=dict(color=t["tenue"]),
               tickformat=",.0f", automargin=True, title_font=dict(color=t["tenue"], size=12))
    fig.update_xaxes(**eje)
    fig.update_yaxes(**eje)
    return fig


def unidad(*series) -> tuple[float, str]:
    """Divisor y sufijo legibles para un eje en colones: «₡12 mil M», «₡850 M» o «₡12.000»."""
    mayor = max((pd.Series(x).abs().max() for x in series), default=0)
    mayor = 0 if pd.isna(mayor) else mayor
    if mayor >= 2e9:
        return 1e9, " mil M"
    if mayor >= 2e6:
        return 1e6, " M"
    return 1.0, ""


def eje_dinero(fig: go.Figure, eje: str, sufijo: str) -> None:
    getattr(fig, f"update_{eje}axes")(tickprefix="₡", ticksuffix=sufijo, tickformat=",~r")


def vacio(t: dict, mensaje: str, alto: int = 220) -> go.Figure:
    fig = base(go.Figure(), t, alto, leyenda=False)
    fig.add_annotation(text=mensaje, showarrow=False, font=dict(color=t["tenue"], size=14),
                       x=0.5, y=0.5, xref="paper", yref="paper")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


# --- Resumen ------------------------------------------------------------------

def de_cada_100(comp: pd.DataFrame, t: dict) -> go.Figure:
    """¿A dónde va cada ₡100? Una barra por partida, ordenada; clic para explorar."""
    if comp.empty:
        return vacio(t, "Sin datos")
    c = comp.sort_values("de_cada_100")
    fig = go.Figure(go.Bar(
        y=c["partida_nombre"], x=c["de_cada_100"], orientation="h", marker_color=t["presupuesto"],
        customdata=list(zip(c["codigo"], [D.dinero(v) for v in c["presupuesto_total"]],
                            [D.porcentaje(v, 0) for v in c["ejecucion"]])),
        text=[f"₡{v:.0f}" if v >= 1 else "<₡1" for v in c["de_cada_100"]], textposition="outside",
        textfont=dict(color=t["tinta2"]), cliponaxis=False,
        hovertemplate="<b>%{customdata[1]}</b> · ₡%{x:.1f} de cada ₡100<br>%{y}<br>"
                      "Ejecutado: %{customdata[2]}<extra>Clic para ver el detalle</extra>",
    ))
    fig = base(fig, t, alto=max(260, 38 * len(c)), leyenda=False)
    fig.update_xaxes(visible=False, range=[0, c["de_cada_100"].max() * 1.15])
    fig.update_yaxes(showgrid=False)
    return fig


def anual(s: pd.DataFrame, t: dict, alto: int = 320) -> go.Figure:
    """Línea con los años cerrados; los años sin informe de cierre van como punto suelto (hueco)."""
    if s["presupuesto_total"].isna().all():
        return vacio(t, "Sin datos por año")
    div, suf = unidad(s["presupuesto_total"], s["total_gastado"])
    cierre = s["es_cierre"].eq(True)
    parcial = s["es_cierre"].eq(False)
    fig = go.Figure()
    for col, nombre, color in (("presupuesto_total", "Presupuesto total", t["presupuesto"]),
                               ("total_gastado", "Ejecutado", t["gastado"])):
        fig.add_trace(go.Scatter(
            x=s["anio"], y=(s[col] / div).where(cierre), name=nombre, mode="lines+markers", connectgaps=False,
            legendgroup=nombre, line=dict(color=color, width=2),
            marker=dict(size=8, color=color, line=dict(color=t["superficie"], width=2)),
            customdata=[D.dinero(v) for v in s[col]],
            hovertemplate="<b>%{customdata}</b><extra>" + nombre + " · año cerrado</extra>",
        ))
        if parcial.any():
            fig.add_trace(go.Scatter(
                x=s.loc[parcial, "anio"], y=s.loc[parcial, col] / div, name=nombre, legendgroup=nombre,
                showlegend=False, mode="markers",
                marker=dict(size=9, color=t["superficie"], symbol="circle", line=dict(color=color, width=2)),
                customdata=list(zip([D.dinero(v) for v in s.loc[parcial, col]],
                                    [D.fecha_larga(c) for c in s.loc[parcial, "corte"]])),
                hovertemplate="<b>%{customdata[0]}</b> al %{customdata[1]}<extra>" + nombre +
                              " · año sin cierre</extra>",
            ))
    fig.update_layout(hovermode="x unified")
    fig = base(fig, t, alto)
    fig.update_yaxes(rangemode="tozero")
    eje_dinero(fig, "y", suf)
    fig.update_xaxes(dtick=1, showgrid=False, tickformat="d")
    return fig


def programas(p: pd.DataFrame, t: dict) -> go.Figure:
    if p.empty:
        return vacio(t, "Sin datos por programa")
    div, suf = unidad(p["presupuesto_total"], p["total_gastado"])
    fig = go.Figure()
    for col, nombre, color in (("total_gastado", "Ejecutado", t["gastado"]),
                               ("presupuesto_total", "Presupuesto total", t["presupuesto"])):
        fig.add_trace(go.Bar(
            y=p["nombre"], x=p[col] / div, name=nombre, orientation="h", marker_color=color,
            customdata=list(zip([D.dinero(v) for v in p[col]], [D.porcentaje(v, 0) for v in p["ejecucion"]])),
            hovertemplate="<b>%{customdata[0]}</b> · %{customdata[1]} ejecutado<extra>" + nombre + "</extra>",
        ))
    fig.update_layout(barmode="group", legend_traceorder="reversed")
    fig = base(fig, t, 260)
    eje_dinero(fig, "x", suf)
    return fig


def mapa_calor(m: pd.DataFrame, t: dict) -> go.Figure:
    """Partida × año → % ejecutado al cierre. Un solo tono: más oscuro = más ejecutado."""
    if m.empty:
        return vacio(t, "No hay informes de cierre para este programa")
    m = m.loc[m.max(axis=1).sort_values(ascending=False).index]
    z = m.clip(lower=0, upper=1.0)
    texto = [[("" if pd.isna(v) else D.porcentaje(max(v, 0), 0)) for v in fila] for fila in m.values]
    fig = go.Figure(go.Heatmap(
        z=z.values, x=[str(c) for c in m.columns], y=m.index, colorscale=escala(t), zmin=0, zmax=1,
        text=texto, xgap=2, ygap=2,
        hovertemplate="%{y} · %{x}<br><b>%{text}</b> ejecutado<extra></extra>",
        colorbar=dict(title=dict(text="% ejecutado", side="top", font=dict(color=t["tenue"], size=12)),
                      tickformat=".0%", tickfont=dict(color=t["tenue"]), thickness=12, outlinewidth=0),
    ))
    # etiqueta de cada celda con la tinta que contrasta con su relleno
    pasos = t["secuencial"]
    for i, fila in enumerate(z.values):
        for j, v in enumerate(fila):
            if pd.isna(v):
                continue
            relleno = pasos[min(int(v * (len(pasos) - 1) + 0.5), len(pasos) - 1)]
            # posición por índice: en un eje de categorías, «2016» se leería como la categoría n.º 2016
            fig.add_annotation(x=j, y=i, text=texto[i][j], showarrow=False,
                               font=dict(size=11, color=tinta_sobre(relleno)))
    fig = base(fig, t, alto=max(260, 34 * len(m) + 60), leyenda=False)
    fig.update_xaxes(showgrid=False, type="category")
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig


# --- Explorar -----------------------------------------------------------------

def treemap(a: pd.DataFrame, t: dict, nivel: str | None) -> go.Figure:
    """Tamaño = presupuesto total; color = % ejecutado. Clic en un bloque para entrar."""
    if a.empty:
        return vacio(t, "Sin datos", 520)
    ids = ["TOTAL"] + list(a["codigo"])
    padres = [""] + list(a["padre_id"])
    etiquetas = ["Todo el presupuesto"] + list(a["nombre_corto"])
    valores = [0.0] + list(a["valor"])
    ejec_total = a.loc[a["nivel"] == "partida", "total_gastado"].sum() / \
        max(a.loc[a["nivel"] == "partida", "presupuesto_total"].sum(), 1)
    colores = [min(ejec_total, 1.0)] + list(a["ejecucion"].clip(upper=1.0).fillna(0))
    custom = [["", D.dinero(a.loc[a["nivel"] == "partida", "presupuesto_total"].sum()), D.porcentaje(ejec_total, 0)]]
    custom += [[c, D.dinero(p), D.porcentaje(e, 0)] for c, p, e in
               zip(a["codigo"], a["presupuesto_total"], a["ejecucion"])]
    fig = go.Figure(go.Treemap(
        ids=ids, parents=padres, labels=etiquetas, values=valores, branchvalues="remainder",
        level=nivel if nivel in set(ids) else "TOTAL", maxdepth=2,
        marker=dict(colors=colores, colorscale=escala(t), cmin=0, cmax=1, line=dict(color=t["superficie"], width=2),
                    colorbar=dict(title=dict(text="% ejecutado", font=dict(color=t["tenue"])), tickformat=".0%",
                                  tickfont=dict(color=t["tenue"]), thickness=12, outlinewidth=0)),
        customdata=custom, texttemplate="<b>%{label}</b><br>%{customdata[1]}", textfont=dict(family=FUENTE),
        hovertemplate="<b>%{label}</b><br>Presupuesto: %{customdata[1]}<br>Ejecutado: %{customdata[2]}"
                      "<extra>%{customdata[0]}</extra>",
        pathbar=dict(visible=True, textfont=dict(family=FUENTE)), tiling=dict(pad=2),
        root=dict(color=t["superficie"]),
    ))
    fig = base(fig, t, 540, leyenda=False)
    fig.update_layout(margin=dict(l=4, r=4, t=30, b=4))
    return fig


def subcuentas(h: pd.DataFrame, t: dict) -> go.Figure:
    h = h[(h["presupuesto_total"] != 0) | (h["total_gastado"] != 0)].sort_values("presupuesto_total")
    if h.empty:
        return vacio(t, "Sin subcuentas con presupuesto")
    ejec = (h["total_gastado"] / h["presupuesto_total"].where(h["presupuesto_total"] != 0))
    div, suf = unidad(h["presupuesto_total"], h["total_gastado"])
    fig = go.Figure()
    for col, nombre, color in (("total_gastado", "Ejecutado", t["gastado"]),
                               ("presupuesto_total", "Presupuesto total", t["presupuesto"])):
        fig.add_trace(go.Bar(
            y=h["nombre_corto"], x=h[col] / div, name=nombre, orientation="h", marker_color=color,
            customdata=list(zip(h["codigo"], [D.dinero(v) for v in h[col]], [D.porcentaje(v, 0) for v in ejec])),
            hovertemplate="<b>%{customdata[1]}</b> · %{customdata[2]} ejecutado<br>%{y}"
                          "<extra>Clic para entrar</extra>",
        ))
    fig.update_layout(barmode="group", legend_traceorder="reversed")
    fig = base(fig, t, alto=max(240, 52 * len(h) + 40))
    eje_dinero(fig, "x", suf)
    return fig


def mensual(m: pd.DataFrame | None, t: dict, alto: int = 260) -> go.Figure:
    if m is None:
        return vacio(t, "Este informe no trae lo pagado mes a mes", alto)
    m = m.dropna()
    m = m[m["mes"] <= max(m.loc[m["girado"] != 0, "mes"].max(), 1)] if (m["girado"] != 0).any() else m
    div, suf = unidad(m["girado"])
    fig = go.Figure(go.Bar(
        x=[D.MESES[i - 1] for i in m["mes"]], y=m["girado"] / div, marker_color=t["gastado"],
        customdata=[D.dinero(v) for v in m["girado"]],
        hovertemplate="<b>%{customdata}</b><extra>%{x}</extra>",
    ))
    fig = base(fig, t, alto, leyenda=False)
    eje_dinero(fig, "y", suf)
    fig.update_xaxes(showgrid=False)
    return fig


def mods_cuenta(m: pd.DataFrame, t: dict) -> go.Figure:
    if m.empty:
        return vacio(t, "Esta cuenta no tuvo modificaciones este año", 200)
    colores = [t["sube"] if v > 0 else t["baja"] for v in m["monto"]]
    div, suf = unidad(m["monto"])
    fig = go.Figure(go.Bar(
        x=m["etiqueta"], y=m["monto"] / div, marker_color=colores,
        customdata=[D.dinero(v) for v in m["monto"]],
        hovertemplate="<b>%{customdata}</b><extra>%{x}</extra>",
    ))
    fig = base(fig, t, 240, leyenda=False)
    fig.update_yaxes(zeroline=True, zerolinewidth=1)
    eje_dinero(fig, "y", suf)
    fig.update_xaxes(showgrid=False, type="category")
    return fig


# --- Cambios al presupuesto ---------------------------------------------------

def linea_mods(g: pd.DataFrame, t: dict) -> go.Figure:
    """Cada modificación: lo que recibieron unas cuentas (arriba) y lo que cedieron otras (abajo)."""
    if g.empty:
        return vacio(t, "Este informe no detalla las modificaciones (formato resumen)", 300)
    div, suf = unidad(g["recibio"], g["cedio"])
    corto = [("M" if t_ == "interna" else "E") + (str(int(n)) if pd.notna(n) else "")
             for t_, n in zip(g["tipo"], g["numero"])]
    fig = go.Figure([
        go.Bar(x=corto, y=g["recibio"] / div, name="Recibieron", marker_color=t["sube"],
               customdata=list(zip([D.dinero(v) for v in g["recibio"]], g["cuentas"])),
               hovertemplate="<b>%{customdata[0]}</b> recibido · %{customdata[1]} cuentas tocadas<extra>%{x}</extra>"),
        go.Bar(x=corto, y=g["cedio"] / div, name="Cedieron", marker_color=t["baja"],
               customdata=[D.dinero(v) for v in g["cedio"]],
               hovertemplate="<b>%{customdata}</b> cedido<extra>%{x}</extra>"),
    ])
    fig.update_layout(barmode="relative", bargap=0.3)
    fig = base(fig, t, 320)
    fig.update_yaxes(zeroline=True, zerolinewidth=1)
    eje_dinero(fig, "y", suf)
    fig.update_xaxes(showgrid=False, type="category", tickangle=0,
                     title=dict(text="M = modificación interna · E = presupuesto extraordinario"))
    return fig


def cambios_partida(p: pd.DataFrame, t: dict) -> go.Figure:
    p = p[p["variaciones"].abs() >= 1e6].sort_values("variaciones")
    if p.empty:
        return vacio(t, "Sin cambios relevantes")
    div, suf = unidad(p["variaciones"])
    fig = go.Figure(go.Bar(
        y=p["partida_nombre"], x=p["variaciones"] / div, orientation="h",
        marker_color=[t["sube"] if v > 0 else t["baja"] for v in p["variaciones"]],
        customdata=list(zip(p["codigo"], [D.dinero(v) for v in p["variaciones"]],
                            [D.dinero(v) for v in p["presupuesto_inicial"]])),
        hovertemplate="<b>%{customdata[1]}</b><br>%{y}<br>Inicial: %{customdata[2]}<extra>Clic para ver</extra>",
    ))
    fig = base(fig, t, alto=max(220, 44 * len(p)), leyenda=False)
    fig.update_xaxes(zeroline=True, zerolinewidth=1)
    eje_dinero(fig, "x", suf)
    fig.update_yaxes(showgrid=False)
    return fig


def mayores_cambios(c: pd.DataFrame, t: dict) -> go.Figure:
    if c.empty:
        return vacio(t, "Sin cambios relevantes")
    div, suf = unidad(c["cambio"])
    fig = go.Figure(go.Bar(
        y=[f"{n} ({cod})" for n, cod in zip(c["nombre_corto"], c["codigo"])], x=c["cambio"] / div, orientation="h",
        marker_color=[t["sube"] if v > 0 else t["baja"] for v in c["cambio"]],
        customdata=list(zip(c["codigo"], [D.dinero(v) for v in c["cambio"]],
                            [D.dinero(v) for v in c["presupuesto_inicial"]],
                            [D.dinero(v) for v in c["presupuesto_total"]])),
        hovertemplate="<b>%{customdata[1]}</b><br>Inicial %{customdata[2]} → total %{customdata[3]}"
                      "<extra>Clic para ver</extra>",
    ))
    fig = base(fig, t, alto=max(260, 34 * len(c) + 40), leyenda=False)
    fig.update_xaxes(zeroline=True, zerolinewidth=1)
    eje_dinero(fig, "x", suf)
    fig.update_yaxes(showgrid=False)
    return fig


# --- Señales y calidad --------------------------------------------------------

def senales_por_partida(s: pd.DataFrame, t: dict) -> go.Figure:
    if s.empty:
        return vacio(t, "Sin señales para esta selección", 200)
    g = s.groupby("partida_nombre").size().sort_values()
    fig = go.Figure(go.Bar(y=g.index, x=g.values, orientation="h", marker_color=t["presupuesto"],
                           hovertemplate="<b>%{x}</b> señales<extra>%{y}</extra>"))
    fig = base(fig, t, alto=max(200, 36 * len(g) + 30), leyenda=False)
    fig.update_xaxes(dtick=max(1, int(g.max() / 5)))
    fig.update_yaxes(showgrid=False)
    return fig


def calidad(v: pd.DataFrame, t: dict) -> go.Figure:
    if v.empty:
        return vacio(t, "Ninguna inconsistencia en este informe 🎉", 200)
    g = v["regla"].map(D.REGLAS).fillna(v["regla"]).value_counts().sort_values()
    fig = go.Figure(go.Bar(y=g.index, x=g.values, orientation="h", marker_color=t["presupuesto"],
                           hovertemplate="<b>%{x}</b> casos<extra>%{y}</extra>"))
    fig = base(fig, t, alto=max(200, 36 * len(g) + 30), leyenda=False)
    fig.update_yaxes(showgrid=False)
    return fig
