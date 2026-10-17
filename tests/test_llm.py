"""Checks the real OllamaClient against a tiny fake Ollama server (no model needed)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.llm import LLMError, OllamaClient


def serve(handler_body: dict | str, tags=None):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            payload = {"message": {"content": handler_body if isinstance(handler_body, str) else json.dumps(handler_body)}}
            self._send(payload)

        def do_GET(self):
            self._send({"models": [{"name": n} for n in (tags or [])]})

        def _send(self, payload):
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


def test_chat_json_parses_model_reply():
    srv, host = serve({"subject": "s", "body": "b"})
    try:
        assert OllamaClient(host=host, model="m").chat_json("sys", "user") == {"subject": "s", "body": "b"}
    finally:
        srv.shutdown()


def test_bad_json_raises_llm_error():
    srv, host = serve("this is not json")
    try:
        with pytest.raises(LLMError):
            OllamaClient(host=host, model="m").chat_json("sys", "user")
    finally:
        srv.shutdown()


def test_health_checks_model_is_pulled():
    srv, host = serve({}, tags=["qwen2.5:7b", "llama3.1:latest"])
    try:
        assert OllamaClient(host=host, model="qwen2.5:7b").health()[0] is True
        assert OllamaClient(host=host, model="llama3.1").health()[0] is True
        ok, msg = OllamaClient(host=host, model="missing:1b").health()
        assert not ok and "ollama pull missing:1b" in msg
    finally:
        srv.shutdown()
