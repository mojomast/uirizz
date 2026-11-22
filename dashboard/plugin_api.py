"""Dashboard REST router exposing stored surfaces for live card refresh."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from uirizz_plugin.api import surface_payload

try:
    from fastapi import APIRouter
except ImportError:
    APIRouter = None  # type: ignore[assignment]

if APIRouter is not None:
    router = APIRouter()

    @router.get("/surfaces/{surface_id}")
    def get_surface(surface_id: str) -> dict[str, Any]:
        return surface_payload(surface_id)

else:

    class _FallbackRouter:
        def __init__(self) -> None:
            self.routes = [SimpleNamespace(path="/surfaces/{surface_id}")]

    router = _FallbackRouter()
