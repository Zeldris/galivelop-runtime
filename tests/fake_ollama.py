"""A fake Ollama on 127.0.0.1 (a thread with `http.server`) for the tests of `grun.ollama` and the worker."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class FakeOllama:
    """`models`: what `/api/ps` lists (dicts with name and size). `unloads`: whether a ``keep_alive: 0`` request
    drops the model. `redirect`: answer every request with a 302 to it. `on_ps`: called with the count of `/api/ps` requests. `ps_body`: raw bytes to answer instead."""

    def __init__(self, models=(), unloads=True, on_ps=None, ps_body=None, redirect=None):
        self.redirect = redirect  # URL base: every request answers 302 to it + path
        self.models = [dict(m) for m in models]
        self.unloads = unloads
        self.on_ps = on_ps
        self.ps_body = ps_body
        self.requests = []  # (method, path, body)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, payload):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _redirect(self):
                self.send_response(302)
                self.send_header("Location", outer.redirect + self.path)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                outer.requests.append(("GET", self.path, None))
                if outer.redirect is not None:
                    return self._redirect()
                if self.path == "/api/ps":
                    count = sum(1 for r in outer.requests if r[1] == "/api/ps")
                    if outer.on_ps is not None:
                        outer.on_ps(count)
                    self._send(outer.ps_body if outer.ps_body is not None
                               else json.dumps({"models": outer.models}).encode())
                else:
                    self._send(b"{}")

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                outer.requests.append(("POST", self.path, body))
                if outer.redirect is not None:
                    return self._redirect()
                if outer.unloads and body.get("keep_alive") == 0:
                    outer.models = [m for m in outer.models if m["name"] != body.get("model")]
                self._send(b"{}")

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def paths(self):
        return [(m, p) for m, p, _ in self.requests]
