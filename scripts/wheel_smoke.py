"""Run from outside checkout after wheel installation."""

import threading

import httpx

from infertrace.api import create_server
from infertrace.storage import EventStore

store = EventStore(":memory:")
server = create_server(store, port=0)
worker = threading.Thread(target=server.serve_forever, daemon=True)
worker.start()
try:
    with httpx.Client(trust_env=False) as client:
        base = f"http://127.0.0.1:{server.server_port}"
        assert "Three Waterfalls" in client.get(base).text
        assert "renderLanes" in client.get(base + "/app.js").text
        assert client.get(base + "/timeline").json()["events"] == []
    print("Installed wheel: imports, static assets and HTTP API passed")
finally:
    server.shutdown()
    server.server_close()
    worker.join()
    store.close()
