"""Conector ATOM genérico para portales extra (autonómicos/sectoriales) configurables.

Parsea entradas ATOM estándar (title/summary/link/id/updated). Sin CODICE: CPV/importe se
dejan vacíos y los filtros Keedio (keywords) deciden la relevancia. La fuente se etiqueta con
`source` para que el normalizador genérico la conserve.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from .base_connector import BaseConnector

_ATOM = "{http://www.w3.org/2005/Atom}"


def _sid(atom_id: str, url: str | None) -> str:
    candidate = atom_id or url or ""
    parts = [p for p in candidate.replace("\\", "/").split("/") if p]
    return parts[-1] if parts else candidate


class GenericAtomConnector(BaseConnector):
    def __init__(self, url: str, source: str, *, timeout: float = 30.0) -> None:
        super().__init__(url, timeout=timeout)
        self.name = source

    def parse(self, raw: str) -> list[dict]:
        if "<feed" not in raw[:2000].lower():
            raise ValueError(f"{self.name}: la respuesta no es un feed ATOM.")
        root = ET.fromstring(raw)
        entries = root.findall(f"{_ATOM}entry") or root.findall(".//" + f"{_ATOM}entry")
        results: list[dict] = []
        for entry in entries:
            atom_id = entry.findtext(f"{_ATOM}id") or ""
            link_el = entry.find(f"{_ATOM}link")
            url = link_el.get("href") if link_el is not None else None
            results.append(
                {
                    "source": self.name,
                    "source_id": _sid(atom_id, url),
                    "title": (entry.findtext(f"{_ATOM}title") or "").strip(),
                    "summary": (entry.findtext(f"{_ATOM}summary") or "").strip() or None,
                    "url": url,
                    "updated": (entry.findtext(f"{_ATOM}updated") or "").strip() or None,
                }
            )
        return results
