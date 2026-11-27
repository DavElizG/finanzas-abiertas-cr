"""Línea de comandos: finanzas listar | descargar | procesar | dashboard."""

from __future__ import annotations

import argparse
import sys

from . import config


def _args_serie(p: argparse.ArgumentParser) -> None:
    p.add_argument("--serie", required=True, choices=sorted(config.SERIES_UNA))
    p.add_argument("--formatos", nargs="*", default=None, help="xlsx, pdf, zip (por defecto todos)")
    p.add_argument("--desde", type=int, default=None, help="año inicial")
    p.add_argument("--hasta", type=int, default=None, help="año final")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="finanzas", description="Datos financieros públicos de la UNA")
    sub = p.add_subparsers(dest="comando", required=True)
    _args_serie(sub.add_parser("listar", help="lista los archivos disponibles de una serie"))
    _args_serie(sub.add_parser("descargar", help="descarga una serie y actualiza el manifiesto"))
    pr = sub.add_parser("procesar", help="procesa los Excel de ejecución descargados")
    pr.add_argument("--sin-anomalias", action="store_true")
    d = sub.add_parser("dashboard", help="levanta el dashboard local")
    d.add_argument("--puerto", type=int, default=8050)
    d.add_argument("--debug", action="store_true")
    a = p.parse_args(argv)

    if a.comando == "listar":
        from .scraper import listar

        archivos = listar(a.serie, a.formatos, a.desde, a.hasta)
        for x in archivos:
            print(f"{x.anio}\t{x.item_fecha or '':10}\t{x.bytes/1e6:6.1f} MB\t{x.item_titulo}\t{x.nombre}")
        print(f"\n{len(archivos)} archivos, {sum(x.bytes for x in archivos)/1e6:.1f} MB")
    elif a.comando == "descargar":
        from .scraper import descargar

        rutas = descargar(a.serie, a.formatos, a.desde, a.hasta)
        print(f"\n{len(rutas)} archivos en {config.RAW / 'una' / a.serie}")
    elif a.comando == "procesar":
        from .pipeline import procesar_ejecucion

        procesar_ejecucion(con_anomalias=not a.sin_anomalias)
    elif a.comando == "dashboard":
        from .dashboard.app import crear_app

        crear_app().run(port=a.puerto, debug=a.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
