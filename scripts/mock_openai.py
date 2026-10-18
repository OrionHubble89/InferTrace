"""Synthetic OpenAI-compatible service. Never use this as an inference engine."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/v1/models":
            body = json.dumps({"data": [{"id": "mock-model"}]}).encode()
        elif self.path == "/metrics":
            body = b"# TYPE vllm:num_requests_running gauge\nvllm:num_requests_running 1\n"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path not in ("/v1/completions", "/v1/chat/completions"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length < 100000:
            self.send_error(413)
            return
        self.rfile.read(length)
        body = b'data: {"choices":[{"text":"Synthetic ","delta":{"content":"Synthetic "}}]}\n\n'
        body += b'data: {"choices":[{"text":"response.","delta":{"content":"response."}}]}\n\n'
        body += b"data: [DONE]\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8000"))), Handler).serve_forever()
