"""Surface records in the plugin data directory, keyed by surface_id."""

from __future__ import annotations

import json
import re
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from uirizz_plugin.catalog import LIMITS

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_lock = threading.Lock()
_test_dir: Path | None = None


class StoreError(ValueError):
    def __init__(self, code: str, error: str, fix: str) -> None:
        super().__init__(error)
        self.code = code
        self.error = error
        self.fix = fix


def set_store_dir(path: Path | None) -> None:
    """Tests inject a temporary directory. Production uses plugin data APIs."""
    global _test_dir
    _test_dir = path


def _plugin_data_dir() -> Path:
    if _test_dir is not None:
        return _test_dir
    try:
        from plugins.plugin_storage import plugin_data_dir as storage_dir  # type: ignore

        path = Path(storage_dir("uirizz"))
        path.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:
        pass
    try:
        from hermes_constants import get_hermes_home  # type: ignore

        path = Path(get_hermes_home()) / "plugin-data" / "uirizz"
        path.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:
        path = Path(tempfile.gettempdir()) / "uirizz-plugin-data"
        path.mkdir(parents=True, exist_ok=True)
        return path


def _surfaces_dir() -> Path:
    path = _plugin_data_dir() / "surfaces"
    path.mkdir(parents=True, exist_ok=True)
    return path


def mint_surface_id() -> str:
    return "surf-" + uuid.uuid4().hex


def normalize_surface_id(surface_id: str | None, *, required: bool) -> str:
    if surface_id is None or surface_id == "":
        if required:
            raise StoreError(
                "missing_surface_id",
                "surface_id is required.",
                "Pass the surface_id returned by present, or call describe.",
            )
        return mint_surface_id()
    if not isinstance(surface_id, str) or not _ID_RE.match(surface_id):
        raise StoreError(
            "invalid_payload",
            "surface_id must be a short token of letters, digits, dot, underscore, or dash.",
            "Use the id returned by present, or omit it on present to mint one.",
        )
    return surface_id


def _path_for(surface_id: str) -> Path:
    return _surfaces_dir() / f"{surface_id}.json"


def get_surface(surface_id: str) -> dict[str, Any] | None:
    path = _path_for(surface_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def put_surface(record: dict[str, Any]) -> dict[str, Any]:
    surface_id = record["surface_id"]
    path = _path_for(surface_id)
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(record, ensure_ascii=False, indent=2)
    if len(payload.encode("utf-8")) > LIMITS["max_payload_bytes"] * 2:
        raise StoreError(
            "oversize",
            "Stored surface exceeded the size cap.",
            "Shrink the surface and try present or update again.",
        )
    with _lock:
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
    return record


def delete_surface(surface_id: str) -> bool:
    path = _path_for(surface_id)
    with _lock:
        if not path.is_file():
            return False
        path.unlink()
        return True
