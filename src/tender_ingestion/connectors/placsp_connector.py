"""Conector PLACSP (Plataforma de Contratación del Sector Público).

PLACSP publica feeds ATOM con CODICE embebido. Este parser extrae los campos ATOM estándar
y, de forma *best-effort* y defensiva, CPV / importe / plazo / órgano de la CODICE (ignorando
namespaces por nombre local de etiqueta). Lo que no encuentra, lo deja en None.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from .base_connector import BaseConnector

_ATOM = "{http://www.w3.org/2005/Atom}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first_text(entry: ET.Element, localnames: set[str]) -> str | None:
    for el in entry.iter():
        if _local(el.tag) in localnames and el.text and el.text.strip():
            return el.text.strip()
    return None


def _all_texts(entry: ET.Element, localnames: set[str]) -> list[str]:
    out = []
    for el in entry.iter():
        if _local(el.tag) in localnames and el.text and el.text.strip():
            out.append(el.text.strip())
    return out


class PlacspAccessError(RuntimeError):
    """La respuesta de PLACSP no es un feed ATOM (p. ej. página de error/redirección)."""


class PlacspConnector(BaseConnector):
    name = "placsp"

    def parse(self, raw: str) -> list[dict]:
        snippet = raw.lstrip()[:400].lower()
        if "<feed" not in raw[:2000].lower():
            # PLACSP devuelve HTML cuando el acceso no está autorizado o la URL no es válida.
            reason = "respuesta no ATOM"
            if "certificado" in snippet or "error de acceso" in snippet:
                reason = "acceso no autorizado (PLACSP exige certificado/acceso autorizado)"
            elif "redireccion" in snippet or "<html" in snippet:
                reason = "PLACSP devolvió una página HTML (¿URL de feed incorrecta?)"
            raise PlacspAccessError(
                f"El feed PLACSP no es ATOM: {reason}. Revisa PLACSP_FEED_URL / acceso."
            )
        root = ET.fromstring(raw)
        entries = root.findall(f"{_ATOM}entry") or root.findall(".//" + f"{_ATOM}entry")
        results: list[dict] = []
        for entry in entries:
            atom_id = entry.findtext(f"{_ATOM}id") or ""
            title = (entry.findtext(f"{_ATOM}title") or "").strip()
            summary = (entry.findtext(f"{_ATOM}summary") or "").strip() or None
            updated = (entry.findtext(f"{_ATOM}updated") or "").strip() or None

            link_el = entry.find(f"{_ATOM}link")
            url = link_el.get("href") if link_el is not None else None

            amount = _first_text(
                entry, {"TotalAmount", "EstimatedOverallContractAmount", "TaxExclusiveAmount"}
            )
            results.append(
                {
                    "source_id": _source_id(atom_id, url),
                    "title": title,
                    "summary": summary,
                    "url": url,
                    "updated": updated,
                    "cpv": _all_texts(entry, {"ItemClassificationCode"}),
                    "budget_amount": amount,
                    "deadline": _first_text(entry, {"EndDate", "DeadlineDate"}),
                    "buyer": _first_text(entry, {"Name", "PartyName"}),
                }
            )
        return results


def _source_id(atom_id: str, url: str | None) -> str:
    """Deriva un identificador estable del expediente."""
    candidate = atom_id or url or ""
    # los id ATOM suelen ser URIs; quedarse con el último segmento no vacío
    parts = [p for p in candidate.replace("\\", "/").split("/") if p]
    return parts[-1] if parts else candidate
