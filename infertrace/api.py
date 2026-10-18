"""Local-only MVP HTTP ingestion/query server. Not an authenticated public service."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from infertrace.correlation import reconstruct
from infertrace.events import Event
from infertrace.storage import EventStore


def create_server(
    store: EventStore, host: str = "127.0.0.1", port: int = 8080
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def respond(self, status: int, data: object) -> None:
            payload = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/app.js"):
                filename = "index.html" if parsed.path == "/" else "app.js"
                payload = (Path(__file__).parent / "static" / filename).read_bytes()
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "text/html" if filename.endswith("html") else "application/javascript",
                )
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(payload)
                return
            if parsed.path == "/health":
                self.respond(200, {"status": "ok"})
                return
            if parsed.path not in ("/events", "/timeline"):
                self.respond(404, {"error": "not found"})
                return
            q = parse_qs(parsed.query)
            if set(q) - {"trace_id", "session_id", "request_id", "limit", "offset"}:
                self.respond(400, {"error": "unknown query"})
                return
            try:
                events = store.query(
                    trace_id=q.get("trace_id", [None])[0],
                    session_id=q.get("session_id", [None])[0],
                    request_id=q.get("request_id", [None])[0],
                    limit=int(q.get("limit", ["1000"])[0]),
                    offset=int(q.get("offset", ["0"])[0]),
                )
            except ValueError:
                self.respond(400, {"error": "invalid pagination"})
                return
            self.respond(
                200,
                reconstruct(events)
                if parsed.path == "/timeline"
                else [e.model_dump(mode="json") for e in events],
            )

        def do_POST(self) -> None:
            if self.path != "/events":
                self.respond(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 1_048_576:
                    self.respond(413, {"error": "batch size limit"})
                    return
                self.connection.settimeout(5)
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, list) or len(data) > 1000:
                    raise ValueError("expected bounded list")
                events = [Event.from_json(json.dumps(e)) for e in data]
                store.export(events)
            except (ValueError, ValidationError, TimeoutError):
                self.respond(400, {"error": "invalid event batch"})
                return
            self.respond(202, {"accepted": len(events)})

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default="infertrace.db")
    args = parser.parse_args()
    store = EventStore(args.db)
    server = create_server(store, args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        store.close()


if __name__ == "__main__":
    main()
