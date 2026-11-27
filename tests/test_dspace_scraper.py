"""Cliente DSpace y manifiesto, sin red (respuestas con la forma real de la API)."""

import csv

import pytest

from finanzas_cr import config, scraper
from finanzas_cr.dspace import BloqueoServidor, ClienteDSpace, anio_de, archivos_de_item, nombre_seguro

# Recorte de la respuesta real de /rest/collections/2445/items?expand=metadata,bitstreams
ITEM = {
    "id": 16524,
    "name": "Informe de Ejecución Presupuestaria a diciembre 2024",
    "handle": "unadocs/17360",
    "metadata": [{"key": "dc.date.issued", "value": "2024-12-31"}],
    "bitstreams": [
        {"id": 47630, "name": "Informe ejecución semestral CGR diciembre 2025.pdf", "bundleName": "ORIGINAL",
         "mimeType": "application/pdf", "sizeBytes": 16879910,
         "checkSum": {"value": "83c8c2fdfe444dbce6270279b885eb44", "checkSumAlgorithm": "MD5"},
         "retrieveLink": "/bitstreams/47630/retrieve"},
        {"id": 47631, "name": "Informe de ejec semetral CGR dic 2025.xlsx", "bundleName": "ORIGINAL",
         "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "sizeBytes": 2871868,
         "checkSum": {"value": "cf69aec5b0dbc374aa923ad88deb0ec8", "checkSumAlgorithm": "MD5"},
         "retrieveLink": "/bitstreams/47631/retrieve"},
        {"id": 47632, "name": "license.txt", "bundleName": "LICENSE", "mimeType": "text/plain", "sizeBytes": 10,
         "checkSum": {"value": "x"}, "retrieveLink": "/bitstreams/47632/retrieve"},
    ],
}
COLECCION = {"id": 2445, "name": "2024"}


def test_archivos_de_item():
    archivos = archivos_de_item("ejecucion", 2024, COLECCION, ITEM)
    assert [a.bitstream_id for a in archivos] == [47630, 47631]  # se ignora el bundle LICENSE
    x = archivos[1]
    assert x.extension == ".xlsx"
    assert x.item_fecha == "2024-12-31"
    assert x.md5 == "cf69aec5b0dbc374aa923ad88deb0ec8"
    assert x.url == "https://documentos.una.ac.cr/rest/bitstreams/47631/retrieve"


def test_filtrar_formatos():
    archivos = archivos_de_item("ejecucion", 2024, COLECCION, ITEM)
    assert [a.extension for a in scraper.filtrar_formatos(archivos, ["xlsx"])] == [".xlsx"]
    assert len(scraper.filtrar_formatos(archivos, None)) == 2


@pytest.mark.parametrize("texto,anio", [("2024", 2024), ("Activos Inmuebles 2019", 2019),
                                        ("Alquileres 2016 al 2018", 2016), ("Circulares", None)])
def test_anio_de(texto, anio):
    assert anio_de(texto) == anio


def test_nombre_seguro():
    assert nombre_seguro("Informe ejecución semestral CGR Junio 2024 (1).xlsx") == \
        "Informe_ejecución_semestral_CGR_Junio_2024_1_.xlsx"


def test_manifiesto_se_combina(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.setattr(config, "RAW", tmp_path / "raw")
    archivos = archivos_de_item("ejecucion", 2024, COLECCION, ITEM)
    destino = tmp_path / "manifest" / "una_ejecucion.csv"
    scraper.escribir_manifiesto(archivos[:1], destino)
    scraper.escribir_manifiesto(archivos, destino)  # segunda corrida: no duplica
    with open(destino, encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    assert [f["bitstream_id"] for f in filas] == ["47630", "47631"]
    assert filas[1]["ruta_local"] == "raw/una/ejecucion/2024/47631_Informe_de_ejec_semetral_CGR_dic_2025.xlsx"


class RespuestaHTML:
    status_code = 200
    headers = {"Content-Type": "text/html"}

    def raise_for_status(self):
        pass


def test_reintenta_tras_corte_de_conexion(monkeypatch):
    import requests

    class RespuestaJSON:
        status_code = 200
        headers = {"Content-Type": "application/json"}

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    llamadas = []

    def get(*a, **k):
        llamadas.append(1)
        if len(llamadas) < 3:
            raise requests.ConnectionError("Remote end closed connection without response")
        return RespuestaJSON()

    cliente = ClienteDSpace(pausa=0, esperas_reintento=(0, 0, 0))
    monkeypatch.setattr(cliente.sesion, "get", get)
    assert cliente.get_json("/communities/375") == {"ok": True}
    assert len(llamadas) == 3


def test_firewall_devuelve_html(monkeypatch):
    cliente = ClienteDSpace(pausa=0)
    monkeypatch.setattr(cliente.sesion, "get", lambda *a, **k: RespuestaHTML())
    with pytest.raises(BloqueoServidor, match="firewall"):
        cliente.get_json("/communities/375")
