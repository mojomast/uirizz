from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from dashboard import plugin_api  # noqa: E402
from uirizz_plugin import store  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    store.set_store_dir(tmp_path / "surfaces")
    monkeypatch.setattr(plugin_api, "POLL_S", 0.02)
    app = FastAPI()
    app.include_router(plugin_api.router)
    yield TestClient(app)
    store.set_store_dir(None)


def _rec(rev):
    return {"surface_id": "card-1", "revision": rev, "fallback_text": "x", "messages": [],
            "component_count": 0, "component_ids": []}


def test_revision_push(client):
    store.put_surface(_rec(1))
    with client.websocket_connect("/surfaces/ws?surface_id=card-1") as ws:
        assert ws.receive_json() == {"type": "revision", "surface_id": "card-1", "revision": 1}
        store.put_surface(_rec(2))
        assert ws.receive_json() == {"type": "revision", "surface_id": "card-1", "revision": 2}


def test_invalid_id_closes_1008(client):
    for url in ("/surfaces/ws?surface_id=../etc", "/surfaces/ws"):
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(url):
                pass
        assert exc.value.code == 1008
