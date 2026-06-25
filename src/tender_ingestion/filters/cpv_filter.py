"""Filtro por CPV (prefijos preferidos/excluidos)."""

from __future__ import annotations

from tender_ingestion.types import TenderPayload


def _matches_any_prefix(cpvs: list[str], prefixes: list[str]) -> bool:
    return any(c.startswith(p) for c in cpvs for p in prefixes)


def passes(payload: TenderPayload, preferred: list[str], excluded: list[str]) -> bool:
    """True si la licitación pasa el filtro CPV.

    - Si algún CPV está en los excluidos → rechaza.
    - Si hay preferidos y la licitación tiene CPV → exige al menos una coincidencia.
    - Si la licitación no trae CPV → neutral (lo decide el filtro de keywords).
    """
    cpvs = payload.cpv or []
    if excluded and _matches_any_prefix(cpvs, excluded):
        return False
    if preferred and cpvs:
        return _matches_any_prefix(cpvs, preferred)
    return True
