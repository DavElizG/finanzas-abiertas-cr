"""Cliente mínimo para la API REST de DSpace 6 (documentos.una.ac.cr/rest).

Solo lectura. Respeta una pausa entre solicitudes y verifica el MD5 de cada
archivo descargado contra el que publica el propio servidor.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from . import config


class BloqueoServidor(RuntimeError):
    """El servidor devolvió HTML (p. ej. "Solicitud rechazada" del firewall) en vez de datos."""


@dataclass
class Archivo:
    """Un bitstream (archivo) de un ítem DSpace."""

    serie: str
    anio: int | None
    coleccion_id: int
    coleccion: str
    item_id: int
    item_handle: str
    item_titulo: str
    item_fecha: str | None
    bitstream_id: int
    nombre: str
    mime: str
    bytes: int
    md5: str | None
    url: str

    @property
    def extension(self) -> str:
        return Path(self.nombre).suffix.lower()


@dataclass
class ClienteDSpace:
    base_rest: str = config.UNA_REST
    pausa: float = config.PAUSA_SEGUNDOS
    timeout: int = 120
    esperas_reintento: tuple[float, ...] = (5.0, 20.0, 60.0)
    sesion: requests.Session = field(default_factory=requests.Session)
    _ultima: float = 0.0

    def __post_init__(self) -> None:
        self.sesion.headers.update({"User-Agent": config.USER_AGENT, "Accept": "application/json"})

    # -- bajo nivel -------------------------------------------------------
    def _esperar(self) -> None:
        falta = self.pausa - (time.monotonic() - self._ultima)
        if falta > 0:
            time.sleep(falta)
        self._ultima = time.monotonic()

    def _get(self, url: str, **kwargs) -> requests.Response:
        """GET con reintentos ante cortes de conexión o errores 5xx (no ante bloqueos del firewall)."""
        for intento in range(len(self.esperas_reintento) + 1):
            self._esperar()
            try:
                r = self.sesion.get(url, timeout=self.timeout, **kwargs)
                if r.status_code < 500:
                    return r
                error: Exception = requests.HTTPError(f"HTTP {r.status_code}")
            except (requests.ConnectionError, requests.Timeout) as exc:
                error = exc
            if intento == len(self.esperas_reintento):
                raise error
            time.sleep(self.esperas_reintento[intento])
        raise AssertionError("inalcanzable")

    def get_json(self, ruta: str, **params):
        r = self._get(f"{self.base_rest}{ruta}", params=params or None)
        tipo = r.headers.get("Content-Type", "")
        if "json" not in tipo:
            raise BloqueoServidor(
                f"{ruta}: se esperaba JSON y llegó {tipo or 'sin tipo'} (HTTP {r.status_code}). "
                "Probablemente el firewall de la UNA bloqueó la solicitud; no intentes saltarlo."
            )
        r.raise_for_status()
        return r.json()

    # -- recorrido --------------------------------------------------------
    def colecciones(self, comunidad_id: int) -> list[dict]:
        """Colecciones de una comunidad, incluyendo subcomunidades."""
        c = self.get_json(f"/communities/{comunidad_id}", expand="collections,subCommunities")
        cols = list(c.get("collections", []))
        for sub in c.get("subcommunities", []):
            cols.extend(self.colecciones(sub["id"]))
        return cols

    def items(self, coleccion_id: int) -> list[dict]:
        salida, offset, limite = [], 0, 100
        while True:
            lote = self.get_json(
                f"/collections/{coleccion_id}/items",
                expand="metadata,bitstreams",
                limit=limite,
                offset=offset,
            )
            salida.extend(lote)
            if len(lote) < limite:
                return salida
            offset += limite

    def archivos_serie(self, serie: str, desde: int | None = None, hasta: int | None = None) -> list[Archivo]:
        info = config.SERIES_UNA[serie]
        archivos: list[Archivo] = []
        for col in self.colecciones(info["comunidad"]):
            anio = anio_de(col["name"])
            if anio is not None and ((desde and anio < desde) or (hasta and anio > hasta)):
                continue
            for it in self.items(col["id"]):
                archivos.extend(archivos_de_item(serie, anio, col, it))
        return archivos

    # -- descarga ---------------------------------------------------------
    def descargar(self, archivo: Archivo, destino: Path) -> Path:
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists() and archivo.md5 and md5_de(destino) == archivo.md5:
            return destino
        tmp = destino.with_suffix(destino.suffix + ".parcial")
        with self._get(archivo.url, stream=True, headers={"Accept": "*/*"}) as r:
            r.raise_for_status()
            if "text/html" in r.headers.get("Content-Type", "") and archivo.extension != ".html":
                raise BloqueoServidor(f"{archivo.url}: llegó HTML en vez del archivo (¿firewall?).")
            with open(tmp, "wb") as fh:
                for bloque in r.iter_content(1 << 16):
                    fh.write(bloque)
        if archivo.md5 and md5_de(tmp) != archivo.md5:
            tmp.unlink(missing_ok=True)
            raise IOError(f"MD5 no coincide para {archivo.nombre} (bitstream {archivo.bitstream_id})")
        tmp.replace(destino)
        return destino


# -- utilidades puras (probadas sin red) -----------------------------------

_ANIO = re.compile(r"(20\d{2}|19\d{2})")


def anio_de(texto: str) -> int | None:
    m = _ANIO.search(texto or "")
    return int(m.group(1)) if m else None


def archivos_de_item(serie: str, anio: int | None, coleccion: dict, item: dict) -> list[Archivo]:
    md = {m["key"]: m["value"] for m in item.get("metadata") or []}
    salida = []
    for b in item.get("bitstreams") or []:
        if b.get("bundleName") != "ORIGINAL":
            continue
        salida.append(
            Archivo(
                serie=serie,
                anio=anio,
                coleccion_id=coleccion["id"],
                coleccion=coleccion["name"],
                item_id=item["id"],
                item_handle=item.get("handle", ""),
                item_titulo=item.get("name", ""),
                item_fecha=md.get("dc.date.issued"),
                bitstream_id=b["id"],
                nombre=b["name"],
                mime=b.get("mimeType", ""),
                bytes=int(b.get("sizeBytes") or 0),
                md5=(b.get("checkSum") or {}).get("value"),
                url=f"{config.UNA_BASE_URL}/rest{b['retrieveLink']}",
            )
        )
    return salida


def md5_de(ruta: Path) -> str:
    h = hashlib.md5()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def nombre_seguro(texto: str) -> str:
    limpio = re.sub(r"[^\w.\-]+", "_", texto, flags=re.UNICODE).strip("_")
    return limpio[:120] or "archivo"
