"""Lee el perfil Keedio editable desde tender-api (/api/profile). Fallback a env si falla."""

from __future__ import annotations

import httpx

from tender_ingestion.config import settings


def fetch_profile() -> dict:
    if not settings.api_url:
        return {}
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{settings.api_url.rstrip('/')}/api/profile")
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError:
        return {}
