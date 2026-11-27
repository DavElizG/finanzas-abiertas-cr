"""Dashboard (Plotly Dash) sobre los CSV de data/processed/una/.

    finanzas dashboard            # http://127.0.0.1:8050

Organización:

* **Resumen**: qué pasó en el año, en frases y en cuatro gráficos.
* **Explorar el gasto**: mapa de bloques por el que se baja de partida a grupo y a
  subpartida; al lado, la ficha de la cuenta elegida (historia, pagos por mes,
  modificaciones, señales y fila exacta del documento).
* **Cambios al presupuesto**: modificaciones internas y extraordinarios.
* **Señales para revisar** y **Calidad de los datos**.

Todo clic en una cuenta (en cualquier pestaña) abre su ficha en «Explorar».
"""

from __future__ import annotations

from pathlib import Path

from dash import ALL, Dash, Input, Output, State, clientside_callback, ctx, dash_table, dcc, html, no_update

from . import datos as D
from . import figuras as F

ASSETS = Path(__file__).parent / "assets"
GRAFICO = {"displaylogo": False, "displayModeBar": False}

AVISO = (
    "Las señales e inconsistencias son preguntas para investigar, no acusaciones ni prueba de irregularidades. "
    "Pueden venir del documento original o de un error de lectura de esta herramienta. "
    "Proyecto independiente, sin afiliación con la Universidad Nacional."
)

TABLA_ESTILO = dict(
    style_table={"overflowX": "auto"},
    style_cell={"fontFamily": F.FUENTE, "fontSize": "13px", "padding": "8px 10px", "textAlign": "left",
                "whiteSpace": "normal", "height": "auto", "maxWidth": "380px",
                "backgroundColor": "var(--superficie)", "color": "var(--tinta)",
                "border": "none", "borderBottom": "1px solid var(--rejilla)"},
    style_cell_conditional=[{"if": {"column_type": "numeric"}, "textAlign": "right",
                             "fontVariantNumeric": "tabular-nums"}],
    style_header={"fontWeight": "600", "backgroundColor": "var(--superficie)", "color": "var(--tinta2)",
                  "borderBottom": "2px solid var(--rejilla)"},
    style_data_conditional=[{"if": {"state": "active"}, "backgroundColor": "var(--resalte)",
                             "border": "none", "borderBottom": "1px solid var(--rejilla)"}],
    page_size=10, sort_action="native", markdown_options={"link_target": "_blank"},
)


# --- Piezas de interfaz -------------------------------------------------------

def tarjeta(titulo: str, valor: str, nota: str = "", clase: str = "") -> html.Div:
    return html.Div(className=f"tarjeta {clase}", children=[
        html.Div(titulo, className="tarjeta-titulo"),
        html.Div(valor, className="tarjeta-valor"),
        html.Div(nota, className="tarjeta-nota"),
    ])


def panel(titulo: str, subtitulo: str | None, *hijos, clase: str = "") -> html.Section:
    cabeza = [html.H3(titulo)]
    if subtitulo:
        cabeza.append(html.P(subtitulo, className="sub"))
    return html.Section(className=f"panel {clase}", children=[*cabeza, *hijos])


def grafico(id_: str, **kw) -> dcc.Loading:
    return dcc.Loading(dcc.Graph(id=id_, config=GRAFICO, **kw), type="dot", color="var(--acento)")


def barra_ejecucion(ratio: float | None) -> html.Div:
    """Medidor simple: cuánto del presupuesto se ejecutó (el exceso se marca aparte)."""
    r = 0 if ratio is None or ratio != ratio else ratio
    return html.Div(className="medidor", title=f"{D.porcentaje(r)} ejecutado", children=[
        html.Div(className="medidor-relleno", style={"width": f"{min(r, 1) * 100:.1f}%"}),
        html.Div(className="medidor-exceso", style={"display": "block" if r > 1 else "none"}),
    ])


def glosario() -> html.Details:
    return html.Details(className="glosario", children=[
        html.Summary("¿Cómo leer esto? Glosario en 1 minuto"),
        html.Dl([x for termino, definicion in D.GLOSARIO for x in (html.Dt(termino), html.Dd(definicion))]),
    ])


def crear_layout(d: D.Datos) -> html.Main:
    informes = D.informe_por_anio(d.ejecucion)
    opciones_anio = [
        {"label": f"{int(r.anio)}" + ("" if r.es_cierre else f" · al {D.fecha_larga(r.corte)}"), "value": r.corte}
        for r in informes.itertuples()
    ]
    cierre = next((o["value"] for o in opciones_anio if D.es_cierre(o["value"])), opciones_anio[0]["value"])

    return html.Main(className="pagina", children=[
        dcc.Store(id="tema-efectivo"),
        dcc.Store(id="cuenta"),
        dcc.Store(id="filtro-senal"),
        html.Header(className="cabecera", children=[
            html.Div([
                html.Div("Finanzas Abiertas CR", className="marca"),
                html.H1("¿En qué gasta la Universidad Nacional?"),
                html.P("Presupuesto, cambios y ejecución, leídos de los informes públicos del Programa de Gestión "
                       "Financiera de la UNA.", className="sub"),
            ]),
            dcc.RadioItems(id="tema", value="auto", inline=True, className="tema",
                           options=[{"label": "Auto", "value": "auto"}, {"label": "Claro", "value": "claro"},
                                    {"label": "Oscuro", "value": "oscuro"}]),
        ]),
        html.Div(className="filtros", children=[
            html.Label(["Año", dcc.Dropdown(id="anio", options=opciones_anio, value=cierre, clearable=False)]),
            html.Label(["Programa", dcc.Dropdown(id="programa", value="integrado", clearable=False,
                                                 options=[{"label": v, "value": k} for k, v in D.PROGRAMAS.items()])]),
            glosario(),
        ]),
        html.Div(AVISO, className="aviso", role="note"),
        dcc.Tabs(id="pestanas", value="resumen", className="pestanas", parent_className="pestanas-contenedor",
                 children=[
            dcc.Tab(label="Resumen", value="resumen", className="pestana", selected_className="pestana-activa",
                    children=vista_resumen()),
            dcc.Tab(label="Explorar el gasto", value="explorar", className="pestana",
                    selected_className="pestana-activa", children=vista_explorar()),
            dcc.Tab(label="Cambios al presupuesto", value="cambios", className="pestana",
                    selected_className="pestana-activa", children=vista_cambios()),
            dcc.Tab(label="Señales para revisar", value="senales", className="pestana",
                    selected_className="pestana-activa", children=vista_senales()),
            dcc.Tab(label="Calidad de los datos", value="calidad", className="pestana",
                    selected_className="pestana-activa", children=vista_calidad()),
        ]),
        html.Footer(className="pie", children=[
            "Fuente: ", html.A("documentos.una.ac.cr", href="https://documentos.una.ac.cr", target="_blank"),
            " · información pública (art. 30 de la Constitución, Ley 10554). Código MIT · datos procesados "
            "CC BY 4.0 · ", html.A("Metodología", target="_blank",
                                   href="https://github.com/DavElizG/finanzas-abiertas-cr/blob/main/docs/metodologia.md"),
        ]),
    ])


def vista_resumen():
    return html.Div(className="vista", children=[
        html.Div(id="r-narrativa", className="narrativa"),
        html.Div(id="r-tarjetas", className="tarjetas"),
        html.Div(className="rejilla", children=[
            panel("¿A dónde va cada ₡100?", "Reparto del presupuesto total por partida. Haz clic en una barra para "
                  "ver qué hay adentro.", grafico("r-cada100")),
            panel("Presupuesto y ejecución por año", "La línea une los años cerrados. Un círculo vacío es el último informe de un año sin cierre publicado en Excel (2018, 2019) o todavía en curso.",
                  grafico("r-anual")),
            panel("¿Qué tanto se ejecuta cada partida?", "Porcentaje gastado al cierre de cada año. Color más intenso = "
                  "más ejecutado. Los años sin informe de diciembre en Excel no aparecen.", grafico("r-calor")),
            panel("Los tres programas", "Cómo se reparte el presupuesto de la universidad entre sus programas.",
                  grafico("r-programas")),
        ]),
    ])


def vista_explorar():
    return html.Div(className="vista", children=[
        html.P("Cada bloque es una cuenta: su tamaño es el presupuesto y su color, cuánto se ejecutó. Haz clic para "
               "bajar de partida a grupo y a subpartida; la barra de arriba sirve para volver.", className="ayuda"),
        html.Div(className="explorar", children=[
            panel("Mapa del presupuesto", None, grafico("e-treemap"), clase="explorar-mapa"),
            html.Div(id="e-ficha", className="explorar-ficha"),
        ]),
    ])


def vista_cambios():
    return html.Div(className="vista", children=[
        html.Div(id="c-narrativa", className="narrativa"),
        html.Div(className="rejilla", children=[
            panel("Modificación por modificación", "En cada modificación interna lo que unas cuentas reciben "
                  "(azul) otras lo ceden (rojo). Los extraordinarios agregan o quitan dinero.", grafico("c-linea")),
            panel("Cambio neto por partida", "Suma de todos los cambios del año: recortes, modificaciones y "
                  "extraordinarios.", grafico("c-partidas")),
        ]),
        panel("Las cuentas que más ganaron y más perdieron", "Subpartidas con el mayor cambio neto en el año. Haz "
              "clic para ver la ficha.", grafico("c-mayores")),
    ])


def vista_senales():
    return html.Div(className="vista", children=[
        html.P("Reglas simples y públicas que marcan cuentas para mirar con más cuidado. Haz clic en un tipo de "
               "señal para filtrar, y en una fila para abrir la ficha de la cuenta.", className="ayuda"),
        html.Div(id="s-tipos", className="tipos-senal"),
        html.Div(className="rejilla rejilla-1-2", children=[
            panel("¿En qué partidas?", None, grafico("s-partidas")),
            panel("Detalle", None, html.Div(id="s-filtro-activo", className="filtro-activo"),
                  dash_table.DataTable(id="s-tabla", **TABLA_ESTILO)),
        ]),
        panel("Cuentas atípicas (exploratorio)", "Un modelo de aprendizaje automático (Isolation Forest) compara "
              "cada subpartida de ₡10 millones o más con las demás y con su propia historia. «Atípica» significa "
              "distinta, no incorrecta.", dash_table.DataTable(id="s-anomalias", **TABLA_ESTILO)),
    ])


def vista_calidad():
    return html.Div(className="vista", children=[
        html.P("Cifras que el propio documento dice que deberían coincidir y no coinciden. Antes de atribuirlas "
               "al documento hay que descartar un error de lectura de esta herramienta.", className="ayuda"),
        html.Div(className="rejilla rejilla-1-2", children=[
            panel("Tipos de inconsistencia", None, grafico("q-reglas")),
            panel("Casos", None, dash_table.DataTable(id="q-tabla", **TABLA_ESTILO)),
        ]),
    ])


# --- Ficha de cuenta ----------------------------------------------------------

def ficha(d: D.Datos, corte: str, programa: str, codigo: str | None, t: dict):
    filas = D.filas_informe(d, corte, programa)
    if codigo is None or codigo not in set(filas["codigo"]):
        comp = D.composicion(filas)
        return [panel("Elige una cuenta", "Haz clic en un bloque del mapa o en una barra de esta lista.",
                      dcc.Graph(id="e-hijos", config=GRAFICO, figure=F.subcuentas(D.hijos(filas, None), t)),
                      html.P(f"{len(comp)} partidas con presupuesto en este informe.", className="nota"))]

    fila = filas[filas["codigo"] == codigo].iloc[0]
    ruta = D.ruta_cuenta(codigo)
    nombres = dict(zip(filas["codigo"], filas["nombre_corto"]))
    migas = [html.Button("Todo", id={"tipo": "miga", "codigo": "TOTAL"}, className="miga")]
    for c in ruta:
        migas += [html.Span("›", className="miga-sep"),
                  html.Button(nombres.get(c, c), id={"tipo": "miga", "codigo": c},
                              className="miga actual" if c == codigo else "miga")]

    pres, gas = fila["presupuesto_total"], fila["total_gastado"]
    ratio = gas / pres if pres else None
    cambio = fila["recortes"] + fila["total_variaciones"]
    nivel = {"partida": "Partida", "grupo": "Grupo", "subpartida": "Subpartida"}[fila["nivel"]]

    hijos = D.hijos(filas, codigo)
    s = D.senales_de(d, corte, programa, codigo)
    contenido = [
        html.Div(migas, className="migas"),
        html.Div(className="ficha-cabeza", children=[
            html.Div([html.Span(f"{nivel} {codigo}", className="etiqueta"), html.H2(fila["nombre_corto"])]),
            html.A("Ver documento original ↗", href=fila["fuente_url"], target="_blank", className="boton-enlace"),
        ]),
        html.P(f"Hoja «{fila['hoja']}», fila {int(fila['fila_excel'])} del Excel.", className="nota"),
        html.Div(className="tarjetas tarjetas-ficha", children=[
            tarjeta("Presupuesto inicial", D.dinero(fila["presupuesto_inicial"])),
            tarjeta("Cambios en el año", D.dinero(cambio), "recortes, modificaciones y extraordinarios"),
            tarjeta("Presupuesto total", D.dinero(pres)),
            tarjeta("Ejecutado", D.dinero(gas), D.porcentaje(ratio, 0) + " del total"),
        ]),
        barra_ejecucion(ratio),
    ]
    if not s.empty:
        contenido.append(html.Div(className="lista-senales", children=[
            html.H4(f"Señales para revisar ({len(s)})"),
            html.Ul([html.Li([html.Strong(D.SENALES[x.senal][0]), f" · {x.nombre} ({x.codigo}): ",
                              D.SENALES[x.senal][1], f" Monto: {D.dinero(x.monto)}."])
                     for x in s.itertuples()]),
        ]))
    if not hijos.empty:
        contenido.append(panel(f"Qué hay adentro ({len(hijos)})", "Clic en una barra para bajar un nivel.",
                               dcc.Graph(id="e-hijos", config=GRAFICO, figure=F.subcuentas(hijos, t))))
    else:
        contenido.append(dcc.Graph(id="e-hijos", style={"display": "none"}, figure=F.vacio(t, "")))
    contenido += [
        html.Div(className="rejilla", children=[
            panel("Historia de esta cuenta", "Línea: años cerrados. Círculo vacío: año sin cierre o en curso.",
                  dcc.Graph(config=GRAFICO, figure=F.anual(D.serie_anual(d, programa, codigo), t, 260))),
            panel("Pagado mes a mes", None,
                  dcc.Graph(config=GRAFICO, figure=F.mensual(D.girado_mensual(filas, codigo), t))),
        ]),
        panel("Modificaciones de este año", "Azul: la cuenta recibió dinero. Rojo: lo cedió.",
              dcc.Graph(config=GRAFICO, figure=F.mods_cuenta(D.modificaciones_cuenta(d, corte, programa, codigo), t))),
    ]
    return contenido


# --- App ----------------------------------------------------------------------

def crear_app(carpeta: Path | None = None) -> Dash:
    d = D.cargar(carpeta)
    app = Dash(__name__, title="Finanzas Abiertas CR", assets_folder=str(ASSETS), suppress_callback_exceptions=True)

    if d.vacio:
        app.layout = html.Main(className="pagina", children=[
            html.H1("Finanzas Abiertas CR"),
            html.P("No hay datos procesados. Corre primero:"),
            html.Pre("finanzas descargar --serie ejecucion --formatos xlsx\nfinanzas procesar"),
        ])
        return app

    app.layout = crear_layout(d)

    clientside_callback(
        """function(valor){
            var t = valor;
            if (valor === 'auto') { t = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'oscuro' : 'claro'; }
            document.documentElement.setAttribute('data-theme', t === 'oscuro' ? 'dark' : 'light');
            return t;
        }""",
        Output("tema-efectivo", "data"), Input("tema", "value"),
    )

    # Resumen ------------------------------------------------------------------
    @app.callback(
        Output("r-narrativa", "children"), Output("r-tarjetas", "children"), Output("r-cada100", "figure"),
        Output("r-anual", "figure"), Output("r-calor", "figure"), Output("r-programas", "figure"),
        Input("anio", "value"), Input("programa", "value"), Input("tema-efectivo", "data"),
    )
    def resumen(corte, programa, tema):
        t = F.tema(tema)
        filas = D.filas_informe(d, corte, programa)
        comp = D.composicion(filas)
        pres, gas = comp["presupuesto_total"].sum(), comp["total_gastado"].sum()
        inicial = comp["presupuesto_inicial"].sum()
        s = D.senales_de(d, corte, programa)
        frases = D.narrativa(d, corte, programa)
        narrativa = [html.P(frases[0], className="titular")] + [html.P(f) for f in frases[1:]]
        tarjetas = [
            tarjeta("Presupuesto total", D.dinero(pres), f"inicial {D.dinero(inicial)}"),
            tarjeta("Ejecutado", D.dinero(gas), "al " + D.fecha_larga(corte)),
            html.Div(className="tarjeta", children=[
                html.Div("Ejecución", className="tarjeta-titulo"),
                html.Div(D.porcentaje(gas / pres if pres else None, 1), className="tarjeta-valor"),
                barra_ejecucion(gas / pres if pres else None),
            ]),
            tarjeta("Señales para revisar", str(len(s)), f"en {s['codigo'].nunique() if not s.empty else 0} cuentas"),
        ]
        return (narrativa, tarjetas, F.de_cada_100(comp, t), F.anual(D.serie_anual(d, programa), t),
                F.mapa_calor(D.mapa_ejecucion(d, programa), t), F.programas(D.comparar_programas(d, corte), t))

    # Explorar -----------------------------------------------------------------
    @app.callback(
        Output("e-treemap", "figure"), Output("e-ficha", "children"),
        Input("anio", "value"), Input("programa", "value"), Input("tema-efectivo", "data"), Input("cuenta", "data"),
    )
    def explorar(corte, programa, tema, codigo):
        t = F.tema(tema)
        filas = D.filas_informe(d, corte, programa)
        arbol = D.arbol(filas)
        # el mapa se abre en la cuenta elegida; si es una hoja, en su cuenta padre para ver a sus hermanas
        nivel = codigo
        if codigo is not None and codigo not in set(arbol["padre_id"]):
            padre = arbol.loc[arbol["codigo"] == codigo, "padre_id"]
            nivel = padre.iloc[0] if not padre.empty else None
        return F.treemap(arbol, t, nivel), ficha(d, corte, programa, codigo, t)

    @app.callback(
        Output("cuenta", "data"), Output("pestanas", "value"),
        Input("e-treemap", "clickData"), Input("e-hijos", "clickData"), Input("r-cada100", "clickData"),
        Input("c-partidas", "clickData"), Input("c-mayores", "clickData"),
        Input({"tipo": "miga", "codigo": ALL}, "n_clicks"), Input("s-tabla", "active_cell"),
        State("s-tabla", "derived_viewport_data"), State("cuenta", "data"),
        prevent_initial_call=True,
    )
    def elegir_cuenta(c_tree, c_hijos, c_100, c_part, c_may, migas, celda, filas_tabla, actual):
        origen = ctx.triggered_id
        if origen is None:
            return no_update, no_update
        if isinstance(origen, dict):  # miga de pan
            if not ctx.triggered[0]["value"]:  # botón recién creado, sin clic
                return no_update, no_update
            return (None if origen["codigo"] == "TOTAL" else origen["codigo"]), no_update
        if origen == "s-tabla":
            if not celda or not filas_tabla:
                return no_update, no_update
            return filas_tabla[celda["row"]]["codigo"], "explorar"
        clic = {"e-treemap": c_tree, "e-hijos": c_hijos, "r-cada100": c_100,
                "c-partidas": c_part, "c-mayores": c_may}[origen]
        if not clic or not clic.get("points"):
            return no_update, no_update
        punto = clic["points"][0]
        if origen == "e-treemap":
            codigo = punto.get("id")
            if codigo == "TOTAL":
                return None, no_update
            # al hacer clic en la cuenta ya abierta, el treemap sube un nivel
            if codigo == actual and punto.get("parent") not in (None, "", "TOTAL"):
                return punto["parent"], no_update
            return (None if codigo == actual else codigo), no_update
        codigo = (punto.get("customdata") or [None])[0]
        if not codigo:
            return no_update, no_update
        return codigo, ("explorar" if origen != "e-hijos" else no_update)

    # Cambios ------------------------------------------------------------------
    @app.callback(
        Output("c-narrativa", "children"), Output("c-linea", "figure"), Output("c-partidas", "figure"),
        Output("c-mayores", "figure"),
        Input("anio", "value"), Input("programa", "value"), Input("tema-efectivo", "data"),
    )
    def cambios(corte, programa, tema):
        t = F.tema(tema)
        filas = D.filas_informe(d, corte, programa)
        p = D.por_partida(filas)
        mods = D.modificaciones_informe(d, corte, programa)
        inicial, total = p["presupuesto_inicial"].sum(), p["presupuesto_total"].sum()
        frases = [f"Se aprobaron {D.dinero(inicial)} al inicio del año y el presupuesto terminó en "
                  f"{D.dinero(total)} ({'+' if total >= inicial else '−'}{D.dinero(abs(total - inicial))})."]
        if not mods.empty:
            internas = mods[mods["tipo"] == "interna"]
            extra = mods[mods["tipo"] == "extraordinario"]
            if not internas.empty:
                frases.append(f"Hubo {len(internas)} modificaciones internas que trasladaron "
                              f"{D.dinero(internas['recibio'].sum())} entre cuentas. La más grande fue la "
                              f"{internas.loc[internas['recibio'].idxmax(), 'etiqueta']} "
                              f"({D.dinero(internas['recibio'].max())}).")
            if not extra.empty:
                neto = extra["recibio"].sum() + extra["cedio"].sum()
                frases.append(f"Los {len(extra)} presupuestos extraordinarios "
                              f"{'agregaron' if neto >= 0 else 'quitaron'} {D.dinero(abs(neto))} en neto.")
        return ([html.P(f) for f in frases], F.linea_mods(mods, t), F.cambios_partida(p, t),
                F.mayores_cambios(D.mayores_cambios(filas), t))

    # Señales ------------------------------------------------------------------
    @app.callback(
        Output("filtro-senal", "data"),
        Input({"tipo": "tipo-senal", "senal": ALL}, "n_clicks"), State("filtro-senal", "data"),
        prevent_initial_call=True,
    )
    def filtrar_senal(_clics, actual):
        origen = ctx.triggered_id
        if not isinstance(origen, dict) or not ctx.triggered[0]["value"]:
            return no_update
        if origen["senal"] == "__todas__" or origen["senal"] == actual:
            return None
        return origen["senal"]

    @app.callback(
        Output("s-tipos", "children"), Output("s-partidas", "figure"), Output("s-filtro-activo", "children"),
        Output("s-tabla", "data"), Output("s-tabla", "columns"), Output("s-tabla", "active_cell"),
        Output("s-anomalias", "data"), Output("s-anomalias", "columns"),
        Input("anio", "value"), Input("programa", "value"), Input("tema-efectivo", "data"),
        Input("filtro-senal", "data"),
    )
    def senales(corte, programa, tema, filtro):
        t = F.tema(tema)
        s = D.senales_de(d, corte, programa)
        res = D.resumen_senales(s)
        por_tipo = {r.senal: r for r in res.itertuples()}
        tipos = []
        for clave, (titulo, explicacion) in D.SENALES.items():
            r = por_tipo.get(clave)
            n = int(r.cuentas) if r is not None else 0
            clase = "tipo" + (" activo" if filtro == clave else "") + (" cero" if n == 0 else "")
            tipos.append(html.Button(id={"tipo": "tipo-senal", "senal": clave}, className=clase, disabled=n == 0,
                                     children=[html.Div(str(n), className="tipo-n"),
                                               html.Div(titulo, className="tipo-titulo"),
                                               html.Div(explicacion, className="tipo-texto"),
                                               html.Div(D.dinero(r.monto) if r is not None else "",
                                                        className="tipo-monto")]))
        visibles = s[s["senal"] == filtro] if filtro and not s.empty else s
        aviso = ([f"Mostrando: {D.SENALES[filtro][0]} · ",
                  html.Button("quitar filtro", id={"tipo": "tipo-senal", "senal": "__todas__"}, className="enlace")]
                 if filtro else "Todas las señales de este informe.")
        columnas = [{"name": "Señal", "id": "senal_txt"}, {"name": "Cuenta", "id": "cuenta"},
                    {"name": "Partida", "id": "partida_nombre"},
                    {"name": "Monto", "id": "monto_txt"}, {"name": "Referencia", "id": "ref_txt"},
                    {"name": "Fuente", "id": "fuente", "presentation": "markdown"}]
        if visibles.empty:
            filas_tabla = []
        else:
            v = visibles.assign(
                senal_txt=visibles["senal"].map(lambda k: D.SENALES[k][0]),
                cuenta=[f"{n} ({c})" for n, c in zip(visibles["nombre"], visibles["codigo"])],
                monto_txt=visibles["monto"].map(D.dinero), ref_txt=visibles["referencia"].map(D.dinero),
                fuente=visibles["fuente_url"].map(lambda u: f"[documento ↗]({u})"),
                orden=visibles["monto"].abs(),
            ).sort_values("orden", ascending=False)
            filas_tabla = v[["senal_txt", "cuenta", "partida_nombre", "monto_txt", "ref_txt", "fuente",
                             "codigo"]].to_dict("records")

        cols_a = [{"name": "Año", "id": "anio"}, {"name": "Programa", "id": "programa_txt"},
                  {"name": "Cuenta", "id": "cuenta"}, {"name": "Presupuesto", "id": "pres"},
                  {"name": "Ejecutado", "id": "ejec"}, {"name": "Cambio en el año", "id": "var"}]
        an = d.anomalias
        if an.empty:
            filas_a = []
        else:
            a = an[an["atipico"]]
            if programa != "integrado":
                a = a[a["programa"] == programa]
            a = a.assign(programa_txt=a["programa"].map(D.PROGRAMAS),
                         cuenta=[f"{n} ({c})" for n, c in zip(a["nombre"], a["codigo"])],
                         pres=a["presupuesto_total"].map(D.dinero), ejec=a["ejecucion"].map(D.porcentaje),
                         var=a["variacion_relativa"].map(lambda x: ("+" if x > 0 else "") + D.porcentaje(x, 0)))
            filas_a = a[[c["id"] for c in cols_a]].to_dict("records")
        return (tipos, F.senales_por_partida(visibles, t), aviso, filas_tabla, columnas, None, filas_a, cols_a)

    # Calidad ------------------------------------------------------------------
    @app.callback(
        Output("q-reglas", "figure"), Output("q-tabla", "data"), Output("q-tabla", "columns"),
        Input("anio", "value"), Input("programa", "value"), Input("tema-efectivo", "data"),
    )
    def calidad(corte, programa, tema):
        t = F.tema(tema)
        v = d.validacion
        if not v.empty:
            v = v[(v["corte"] == corte) & ((v["programa"] == programa) | v["programa"].isna())]
        columnas = [{"name": "Tipo", "id": "regla_txt"}, {"name": "Cuenta", "id": "cuenta"},
                    {"name": "Debería ser", "id": "esperado_txt"}, {"name": "El documento dice", "id": "encontrado_txt"},
                    {"name": "Detalle", "id": "detalle"}]
        if v.empty:
            return F.calidad(v, t), [], columnas
        w = v.assign(
            regla_txt=v["regla"].map(D.REGLAS).fillna(v["regla"]),
            cuenta=[(f"{n} ({c})" if isinstance(n, str) and n else (c if isinstance(c, str) else ""))
                    for n, c in zip(v.get("nombre"), v.get("codigo"))],
            esperado_txt=v["esperado"].map(D.dinero), encontrado_txt=v["encontrado"].map(D.dinero),
            orden=v["diferencia"].abs(),
        ).sort_values("orden", ascending=False, na_position="first")
        return F.calidad(v, t), w[[c["id"] for c in columnas]].fillna("").to_dict("records"), columnas

    return app


if __name__ == "__main__":  # pragma: no cover
    crear_app().run(debug=True)
