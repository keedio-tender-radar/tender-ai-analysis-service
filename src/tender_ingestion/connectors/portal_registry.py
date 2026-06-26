"""Registro de portales extra configurables (autonómicos/sectoriales) sin tocar el core.

Lee `EXTRA_PORTAL_FEEDS_JSON` (lista JSON de portales) y construye Sources con el conector
ATOM genérico. Cada portal: {source, name, connector_type, feed_url, enabled}.
"""

from __future__ import annotations

import json
import logging

from tender_ingestion.connectors.generic_atom_connector import GenericAtomConnector
from tender_ingestion.jobs.daily_ingestion_job import Source
from tender_ingestion.normalizers import generic_normalizer

logger = logging.getLogger("tender_ingestion")


def extra_portal_sources(raw_json: str) -> list[Source]:
    """Devuelve Sources para los portales extra habilitados. Ignora entradas malformadas."""
    if not raw_json or not raw_json.strip():
        return []
    try:
        portals = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        logger.warning("EXTRA_PORTAL_FEEDS_JSON inválido: %s", exc)
        return []
    sources: list[Source] = []
    for p in portals if isinstance(portals, list) else []:
        if not p.get("enabled", True) or not p.get("feed_url"):
            continue
        ctype = p.get("connector_type", "generic_atom")
        if ctype != "generic_atom":
            logger.warning("Portal %s: connector_type '%s' no soportado.", p.get("source"), ctype)
            continue
        name = p.get("source") or p.get("name") or "portal"
        sources.append(
            Source(GenericAtomConnector(p["feed_url"], name), generic_normalizer.normalize)
        )
    return sources
