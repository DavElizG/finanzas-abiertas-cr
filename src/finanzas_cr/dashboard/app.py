"""Dashboard (Plotly Dash) sobre los CSV de data/processed/una/.

    finanzas dashboard            # http://127.0.0.1:8050
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, clientside_callback, dash_table, dcc, html

from . import datos as D

ASSETS = Path(__file__).parent / "assets"
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]

# Paleta validada (dataviz, paleta de referencia). Cada entidad conserva su color en todo el tablero.
TEMAS = {
    "claro": {
        "superficie": "#fcfcfb", "tinta": "#0b0b0b", "tinta2": "#52514e", "tenue": "#898781",
        "rejilla": "#e1e0d9", "base": "#c3c2b7",
        "presupuesto": "#2a78d6", "gastado": "#eb6834",
        "sube": "#2a78d6", "baja": "#e34948",
    },
    "oscuro": {
        "superficie": "#1a1a19", "tinta": "#f0efec", "tinta2": "#c3c2b7", "tenue": "#898781",
        "rejilla": "#2c2c2a", "base": "#383835",
        "presupuesto": "#3987e5", "gastado": "#d95926",
        "sube": "#3987e5", "baja": "#e66767",
    },
}

AVISO = (
    "Las señales y las inconsistencias son preguntas para investigar, no acusaciones ni prueba de "
    "irregularidades. Pueden venir del documento original o de un error de lectura de esta herramienta. "
    "Proyecto independiente, sin afiliación con la Universidad Nacional."
)


def _base(fig: go.Figure, t: dict, alto: int = 360) -> go.Figure:
    fig.update_layout(
        height=alto, margin=dict(l=8, r=16, t=8, b=8),
        paper_bgcolor=t["superficie"], plot_bgcolor=t["superficie"],
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', color=t["tinta2"], size=13),
        separators=",.", barcornerradius=4, bargap=0.35, bargroupgap=0.12,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(color=t["tinta2"])),
        hoverlabel=dict(bgcolor=t["superficie"], bordercolor=t["base"], font=dict(color=t["tinta"])),
    )
    eje = dict(gridcolor=t["rejilla"], linecolor=t["base"], zerolinecolor=t["base"], tickfont=dict(color=t["tenue"]),
               tickformat=",.0f")
    fig.update_xaxes(**eje)
    fig.update_yaxes(**eje)
    return fig


def _vacio(t: dict, mensaje: str, alto: int = 240) -> go.Figure:
    fig = _base(go.Figure(), t, alto)
    fig.add_annotation(text=mensaje, showarrow=False, font=dict(color=t["tenue"], size=14), x=0.5, y=0.5,
                       xref="paper", yref="paper")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def fig_partidas(p: pd.DataFrame, t: dict) -> go.Figure:
    if p.empty:
        return _vacio(t, "Sin datos para esta selección")
    p = p.sort_values("presupuesto_total")
    ejec = (p["total_gastado"] / p["presupuesto_total"].where(p["presupuesto_total"] != 0)).fillna(0)
    hover = "<b>%{x:,.0f}</b> M<br>%{y}<extra>%{fullData.name}</extra>"
    fig = go.Figure([
        go.Bar(y=p["partida_nombre"], x=p["presupuesto_total"] / 1e6, name="Presupuesto total", orientation="h",
               marker_color=t["presupuesto"], hovertemplate=hover),
        go.Bar(y=p["partida_nombre"], x=p["total_gastado"] / 1e6, name="Ejecutado", orientation="h",
               marker_color=t["gastado"], customdata=ejec,
               hovertemplate="<b>%{x:,.0f}</b> M · %{customdata:.1%} ejecutado<br>%{y}<extra>Ejecutado</extra>"),
    ])
    # en barras horizontales la primera traza queda abajo: se invierte para que «Presupuesto» vaya arriba
    fig.data = fig.data[::-1]
    fig.update_layout(barmode="group", legend_traceorder="reversed")
    fig.update_xaxes(title=dict(text="millones de colones", font=dict(color=t["tenue"])))
    return _base(fig, t, alto=max(300, 64 * len(p)))


def fig_anual(s: pd.DataFrame, t: dict) -> go.Figure:
    if s["presupuesto_total"].isna().all():
        return _vacio(t, "No hay informes de cierre (diciembre) para este programa")
    fig = go.Figure()
    for col, nombre, color in (("presupuesto_total", "Presupuesto total", t["presupuesto"]),
                               ("total_gastado", "Ejecutado", t["gastado"])):
        fig.add_trace(go.Scatter(
            x=s["anio"], y=s[col] / 1e9, name=nombre, mode="lines+markers", connectgaps=False,
            line=dict(color=color, width=2), marker=dict(size=8, color=color, line=dict(color=t["superficie"], width=2)),
            hovertemplate="<b>₡%{y:,.1f} mil M</b><extra>" + nombre + "</extra>",
        ))
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(title=dict(text="miles de millones de colones", font=dict(color=t["tenue"])), rangemode="tozero")
    fig = _base(fig, t, 340)
    fig.update_xaxes(dtick=1, showgrid=False, tickformat="d")  # años sin separador de miles
    return fig


def fig_modificaciones(p: pd.DataFrame, t: dict) -> go.Figure:
    p = p[p["variaciones"].abs() >= 1e6].sort_values("variaciones")
    if p.empty:
        return _vacio(t, "Sin modificaciones relevantes")
    colores = [t["sube"] if v > 0 else t["baja"] for v in p["variaciones"]]
    fig = go.Figure(go.Bar(
        y=p["partida_nombre"], x=p["variaciones"] / 1e6, orientation="h", marker_color=colores,
        customdata=p["presupuesto_inicial"] / 1e6,
        hovertemplate="<b>%{x:+,.0f}</b> M<br>%{y}<br>Presupuesto inicial: %{customdata:,.0f} M<extra></extra>",
        showlegend=False,
    ))
    fig.update_xaxes(title=dict(text="millones de colones (recibió + / cedió −)", font=dict(color=t["tenue"])),
                     zeroline=True, zerolinewidth=1)
    return _base(fig, t, alto=max(240, 48 * len(p)))


def fig_mensual(m: pd.DataFrame | None, t: dict) -> go.Figure:
    if m is None:
        return _vacio(t, "Este informe no trae el girado mes a mes (formato resumen)")
    m = m.dropna()
    m = m[m["girado"] != 0] if (m["girado"] != 0).any() else m
    fig = go.Figure(go.Bar(
        x=[MESES[i - 1] for i in m["mes"]], y=m["girado"] / 1e6, marker_color=t["gastado"], name="Girado",
        hovertemplate="<b>%{y:,.0f}</b> M<extra>%{x}</extra>", showlegend=False,
    ))
    fig.update_yaxes(title=dict(text="millones de colones", font=dict(color=t["tenue"])))
    fig.update_xaxes(showgrid=False)
    return _base(fig, t, 300)


def tarjeta(titulo: str, valor: str, nota: str = "") -> html.Div:
    return html.Div(className="tarjeta", children=[
        html.Div(titulo, className="tarjeta-titulo"),
        html.Div(valor, className="tarjeta-valor"),
        html.Div(nota, className="tarjeta-nota"),
    ])


def seccion(titulo: str, subtitulo: str, *hijos) -> html.Section:
    return html.Section(className="panel", children=[html.H2(titulo), html.P(subtitulo, className="sub"), *hijos])


TABLA_ESTILO = dict(
    style_table={"overflowX": "auto"},
    style_cell={"fontFamily": 'system-ui, -apple-system, "Segoe UI", sans-serif', "fontSize": "13px", "padding": "6px 8px", "textAlign": "left",
                "whiteSpace": "normal", "height": "auto", "maxWidth": "360px",
                "backgroundColor": "var(--superficie)", "color": "var(--tinta)", "border": "1px solid var(--rejilla)"},
    style_header={"fontWeight": "600", "backgroundColor": "var(--plano)", "color": "var(--tinta2)"},
    page_size=12, sort_action="native", filter_action="native", markdown_options={"link_target": "_blank"},
)


def crear_app(carpeta: Path | None = None) -> Dash:
    d = D.cargar(carpeta)
    app = Dash(__name__, title="Finanzas Abiertas CR", assets_folder=str(ASSETS))

    if d.vacio:
        app.layout = html.Main(className="pagina", children=[
            html.H1("Finanzas Abiertas CR"),
            html.P("No hay datos procesados. Corre primero:"),
            html.Pre("finanzas descargar --serie ejecucion --formatos xlsx\nfinanzas procesar"),
        ])
        return app

    informes = D.informe_por_anio(d.ejecucion)
    opciones_anio = [
        {"label": f"{int(r.anio)}" + ("" if r.es_cierre else f" (parcial, corte {r.corte})"), "value": r.corte}
        for r in informes.itertuples()
    ]

    app.layout = html.Main(className="pagina", children=[
        html.Header(className="cabecera", children=[
            html.Div([
                html.H1("Finanzas Abiertas CR"),
                html.P("¿En qué gasta la Universidad Nacional? Presupuesto, modificaciones y ejecución, "
                       "tomados de los informes públicos del Programa de Gestión Financiera.", className="sub"),
            ]),
            dcc.RadioItems(id="tema", value="auto", inline=True, className="tema",
                           options=[{"label": "Auto", "value": "auto"}, {"label": "Claro", "value": "claro"},
                                    {"label": "Oscuro", "value": "oscuro"}]),
        ]),
        html.Div(AVISO, className="aviso", role="note"),
        html.Div(className="filtros", children=[
            html.Label(["Año", dcc.Dropdown(id="anio", options=opciones_anio, value=opciones_anio[0]["value"],
                                            clearable=False)]),
            html.Label(["Programa", dcc.Dropdown(id="programa", value="integrado", clearable=False,
                                                 options=[{"label": v, "value": k} for k, v in D.PROGRAMAS.items()])]),
        ]),
        html.Div(id="tarjetas", className="tarjetas"),
        dcc.Store(id="tema-efectivo"),
        html.Div(className="rejilla", children=[
            seccion("¿En qué se gasta?", "Presupuesto total y ejecutado por partida del clasificador por objeto del gasto.",
                    dcc.Graph(id="g-partidas", config={"displaylogo": False, "displayModeBar": False})),
            seccion("Hacia dónde se movió el dinero", "Cambio neto por partida por modificaciones internas, "
                    "presupuestos extraordinarios y recortes.",
                    dcc.Graph(id="g-modificaciones", config={"displaylogo": False, "displayModeBar": False})),
            seccion("Presupuesto y ejecución por año", "Solo informes de cierre (31 de diciembre). Los años sin "
                    "informe de diciembre publicado en Excel quedan en blanco.",
                    dcc.Graph(id="g-anual", config={"displaylogo": False, "displayModeBar": False})),
            seccion("Girado mes a mes", "Un pico en diciembre puede indicar gasto acumulado para fin de año.",
                    dcc.Graph(id="g-mensual", config={"displaylogo": False, "displayModeBar": False})),
        ]),
        seccion("Señales para revisar", "Cuentas (subpartidas) que cumplen alguna regla de docs/metodologia.md. "
                "Haz clic en «documento» para ver la fuente original.",
                dash_table.DataTable(id="t-senales", **TABLA_ESTILO)),
        seccion("Inconsistencias del documento", "Cifras que el propio documento dice que deberían coincidir y no "
                "coinciden. Primero hay que descartar un error de lectura de esta herramienta.",
                dash_table.DataTable(id="t-validacion", **TABLA_ESTILO)),
        seccion("Cuentas atípicas (exploratorio)", "Isolation Forest sobre las subpartidas de ₡10 M o más al cierre "
                "de cada año. Un puntaje alto indica que la cuenta se comporta distinto al resto, no que esté mal.",
                dash_table.DataTable(id="t-anomalias", **TABLA_ESTILO)),
        html.Footer(className="pie", children=[
            "Fuente: ", html.A("documentos.una.ac.cr", href="https://documentos.una.ac.cr", target="_blank"),
            " (información pública, art. 30 de la Constitución y Ley 10554). Código MIT · datos procesados CC BY 4.0.",
        ]),
    ])

    clientside_callback(
        """function(valor){
            var t = valor;
            if (valor === 'auto') { t = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'oscuro' : 'claro'; }
            document.documentElement.setAttribute('data-theme', t === 'oscuro' ? 'dark' : 'light');
            return t;
        }""",
        Output("tema-efectivo", "data"), Input("tema", "value"),
    )

    @app.callback(
        Output("tarjetas", "children"), Output("g-partidas", "figure"), Output("g-modificaciones", "figure"),
        Output("g-anual", "figure"), Output("g-mensual", "figure"),
        Output("t-senales", "data"), Output("t-senales", "columns"),
        Output("t-validacion", "data"), Output("t-validacion", "columns"),
        Output("t-anomalias", "data"), Output("t-anomalias", "columns"),
        Input("anio", "value"), Input("programa", "value"), Input("tema-efectivo", "data"),
    )
    def actualizar(corte, programa, tema):
        t = TEMAS.get(tema or "claro", TEMAS["claro"])
        filas = D.filas_informe(d, corte, programa)
        p = D.por_partida(filas)
        anio = int(corte[:4])
        es_cierre = corte.endswith("-12-31") or corte.endswith("-12-30")

        pres = p["presupuesto_total"].sum()
        gas = p["total_gastado"].sum()
        sen = d.senales
        sen = sen[(sen["corte"] == corte) & (sen["programa"] == programa)] if not sen.empty else sen
        val = d.validacion
        val = val[(val["corte"] == corte) & ((val["programa"] == programa) | val["programa"].isna())] if not val.empty else val

        tarjetas = [
            tarjeta("Presupuesto total", D.colones_m(pres), f"inicial {D.colones_m(p['presupuesto_inicial'].sum())}"),
            tarjeta("Ejecutado", D.colones_m(gas), f"corte {corte}" + ("" if es_cierre else " · año en curso")),
            tarjeta("Ejecución", D.porcentaje(gas / pres if pres else None), "ejecutado / presupuesto total"),
            tarjeta("Señales para revisar", f"{len(sen)}", "en subpartidas"),
            tarjeta("Inconsistencias", f"{len(val)}", "en el documento o la lectura"),
        ]

        # Tablas
        cols_s = [("Señal", "senal_txt", "text"), ("Código", "codigo", "text"), ("Cuenta", "nombre", "text"),
                  ("Partida", "partida_nombre", "text"), ("Monto (₡ M)", "monto_m", "numeric"),
                  ("Referencia (₡ M)", "referencia_m", "numeric"), ("Fuente", "fuente", "text")]
        if not sen.empty:
            s = sen.assign(senal_txt=sen["senal"].map(D.SENALES), monto_m=(sen["monto"] / 1e6).round(1),
                           referencia_m=(sen["referencia"] / 1e6).round(1),
                           fuente=sen["fuente_url"].map(lambda u: f"[documento]({u})"))
            s = s.sort_values("monto_m", key=abs, ascending=False)
            datos_s = s[[c for _, c, _ in cols_s]].to_dict("records")
        else:
            datos_s = []
        columnas_s = [{"name": n, "id": c, "type": ty, **({"presentation": "markdown"} if c == "fuente" else {})}
                      for n, c, ty in cols_s]

        cols_v = [("Regla", "regla_txt", "text"), ("Código", "codigo", "text"), ("Cuenta", "nombre", "text"),
                  ("Campo", "campo", "text"), ("Diferencia (₡ M)", "dif_m", "numeric"), ("Detalle", "detalle", "text")]
        if not val.empty:
            v = val.assign(regla_txt=val["regla"].map(D.REGLAS).fillna(val["regla"]),
                           dif_m=(pd.to_numeric(val.get("diferencia"), errors="coerce") / 1e6).round(2))
            v = v.sort_values("dif_m", key=lambda x: x.abs(), ascending=False, na_position="first")
            datos_v = v[[c for _, c, _ in cols_v]].fillna("").to_dict("records")
        else:
            datos_v = []
        columnas_v = [{"name": n, "id": c, "type": ty} for n, c, ty in cols_v]

        cols_a = [("Año", "anio", "numeric"), ("Programa", "programa", "text"), ("Código", "codigo", "text"),
                  ("Cuenta", "nombre", "text"), ("Presupuesto (₡ M)", "pres_m", "numeric"),
                  ("Ejecución", "ejec", "text"), ("Puntaje", "puntaje", "numeric")]
        an = d.anomalias
        if not an.empty:
            a = an[an["atipico"]]
            if programa != "integrado":
                a = a[a["programa"] == programa]
            a = a.assign(programa=a["programa"].map(D.PROGRAMAS), pres_m=(a["presupuesto_total"] / 1e6).round(1), ejec=a["ejecucion"].map(D.porcentaje),
                         puntaje=a["puntaje_anomalia"].round(3))
            datos_a = a[[c for _, c, _ in cols_a]].to_dict("records")
        else:
            datos_a = []
        columnas_a = [{"name": n, "id": c, "type": ty} for n, c, ty in cols_a]

        return (
            tarjetas,
            fig_partidas(p, t),
            fig_modificaciones(p, t),
            fig_anual(D.serie_anual(d, programa), t),
            fig_mensual(D.girado_mensual(filas), t),
            datos_s, columnas_s, datos_v, columnas_v, datos_a, columnas_a,
        )

    return app


if __name__ == "__main__":  # pragma: no cover
    crear_app().run(debug=True)
