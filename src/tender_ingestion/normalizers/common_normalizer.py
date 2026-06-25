"""Utilidades de normalización compartidas entre fuentes."""

from __future__ import annotations

import re
from datetime import date, datetime


def to_float(value) -> float | None:
    """Convierte un importe (str con símbolos/miles, o número) a float."""
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    # quitar símbolo de moneda y espacios; normalizar separadores
    s = re.sub(r"[^\d,.\-]", "", s)
    if "," in s and "." in s:
        # formato europeo "1.234.567,89" → quitar puntos de miles, coma decimal a punto
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def to_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    # fecha sola → medianoche
    d = to_date(s)
    return datetime(d.year, d.month, d.day) if d else None


def to_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    s = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def clean_cpv(values: list[str]) -> list[str]:
    """Deja solo códigos CPV plausibles (dígitos), deduplicados preservando orden."""
    out: list[str] = []
    for v in values or []:
        digits = re.sub(r"\D", "", str(v))
        if digits and digits not in out:
            out.append(digits)
    return out
