"""Servidor HTTP falso da Messages API (stdlib). Grava cada requisição recebida, para os
testes provarem o que foi (ou NÃO foi) enviado, sem gastar nada."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def ok(text="42", in_tok=10, out_tok=5, stop="end_turn", content=None):
    return {"status": 200, "body": {
        "content": content if content is not None else [{"type": "text", "text": text}],
        "usage": {"input_tokens": in_tok, "output_tokens": out_tok}, "stop_reason": stop}}


def err(status, headers=None):
    return {"status": status, "headers": headers or {}, "body": {"error": {"type": "x", "message": "boom"}}}


class FakeAnthropic:
    """`script`: lista de respostas, uma por requisição; a última se repete."""

    def __init__(self, *script):
        self.script = list(script) or [ok()]
        self.requests: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("content-length", 0))
                outer.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()},
                                       "body": json.loads(self.rfile.read(n))})
                i = min(len(outer.requests) - 1, len(outer.script) - 1)
                r = outer.script[i]
                time.sleep(r.get("delay", 0))
                raw = r["body"] if isinstance(r["body"], bytes) else json.dumps(r["body"]).encode()
                try:
                    self.send_response(r["status"])
                    for k, v in r.get("headers", {}).items():
                        self.send_header(k, v)
                    self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # cliente já desistiu (teste de timeout)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self._t = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self._t.join()
