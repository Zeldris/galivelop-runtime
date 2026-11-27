"""Local HTTP API base (D-2): bind, security checks, JSON errors, router, queue routes, ``serve.lock``/``serve.json``.

Adapted from gimg@HEAD gimg/server.py (table, ``_check_origin``, ``health``, queue routes) and gimg/service.py
(``_single_instance``, ``serve.json``), without the image routes, the static files or the service life cycle (those
belong to each application). Stdlib and ``grun`` only.

The application is an `App`; its own routes go in with `Server.add_route(method, pattern, handler)`. A handler takes a
`Request` and returns a dict/list (sent as JSON, 200) or a `Reply`; it raises `GrunError` for user errors.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import stat as _stat
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote

from . import __version__, fsutil, i18n, ollama, paths
from .errors import GrunError
from .queue import STATES, make_error

API_VERSION = 1
MAX_BODY = 1024 * 1024
READ_TIMEOUT = 30
BIND_HOST = "127.0.0.1"
LOCK_RETRY_S = 0.3  # a momentary probe of the lock (`fsutil.held`) must not make a fresh server give up
BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin", "Cross-Origin-Opener-Policy": "same-origin",
}

# --- error code -> HTTP status; first match wins, no match = 500 -------------------------------------------------
_EXACT = {
    403: ("api.bad_host", "api.bad_origin"),
    404: ("api.not_found", "queue.unknown", "queue.batch_not_found"),
    405: ("api.method_not_allowed",), 411: ("api.length_required",), 413: ("api.body_too_large",),
    415: ("api.content_type",),
    409: ("serve.already_running", "serve.port_busy", "queue.not_cancellable", "queue.not_movable",
          "queue.not_running", "queue.bad_state"),
    400: ("api.bad_request", "api.bad_json", "api.bad_param", "queue.bad_move"),
}
# server-side faults whose names match the 400 patterns below: checked first
_SERVER_FAULTS = ("queue.bad_progress",)
_PREFIX = (("path.", 400), ("net.", 400))
_SUFFIX = ((".invalid", 400), ("_invalid", 400), (".unknown", 400))
_BAD = ".bad_"


def status_for(code: str, extra=None) -> int:
    """HTTP status of a `GrunError` code: server faults (500), exact, prefix, ``.bad_``, suffix, else 500.

    `extra` is the application's own table, a dict with any of ``faults`` (codes, 500), ``exact`` (``{status:
    codes}``), ``prefix`` and ``suffix`` (tuples of ``(text, status)``); at each step its entries are tried before the
    generic ones, so an application can refine or override a generic code."""
    extra = extra or {}
    if code in tuple(extra.get("faults", ())) + _SERVER_FAULTS:
        return 500
    for table in (extra.get("exact", {}), _EXACT):
        for status, codes in table.items():
            if code in codes:
                return status
    for prefix, status in tuple(extra.get("prefix", ())) + _PREFIX:
        if code.startswith(prefix):
            return status
    if _BAD in code:
        return 400
    for suffix, status in tuple(extra.get("suffix", ())) + _SUFFIX:
        if code.endswith(suffix):
            return status
    return 500


# --- application, requests, router -------------------------------------------------------------------------------
@dataclass
class App:
    """What the server needs of an application: its data folder, its `Queue` and its table of errors."""
    queue: object
    data: Path
    version: str = __version__
    errors: dict | None = None  # the application's table for `status_for`

    def __post_init__(self):
        self.data = Path(self.data)


@dataclass
class Reply:
    status: int = 200
    body: object = b""          # bytes, or any JSON value when json=True
    content_type: str = "application/octet-stream"
    headers: dict = field(default_factory=dict)
    json: bool = False


@dataclass
class Request:
    method: str
    params: dict
    query: dict
    body: dict | None
    lang: str
    server: object
    headers: object

    @property
    def app(self):
        return self.server.app


@dataclass
class Route:
    method: str
    parts: tuple
    handler: object


def _match(parts: tuple, segments: list):
    if len(parts) != len(segments):
        return None
    params = {}
    for part, seg in zip(parts, segments):
        if part.startswith("{") and part.endswith("}"):
            if "/" in seg:
                return None
            params[part[1:-1]] = seg
        elif part != seg:
            return None
    return params


def _bad_segment(seg: str) -> bool:
    return seg == "" or "\x00" in seg or "\\" in seg or ".." in seg.split("/") or "" in seg.split("/")


def split_path(raw: str):
    """Raw path (no query) -> decoded segments, or None if any segment is unacceptable (404)."""
    if not raw.startswith("/"):
        return None
    if raw == "/":
        return []
    segments = []
    for piece in raw[1:].split("/"):
        try:
            seg = unquote(piece, errors="strict")
        except UnicodeDecodeError:
            return None
        if _bad_segment(seg):
            return None
        segments.append(seg)
    return segments


def pick_lang(query: dict, accept: str | None) -> str:
    langs = i18n.available()
    asked = (query.get("lang") or [""])[0]
    if asked in langs:
        return asked
    ranked = []
    for index, item in enumerate((accept or "").split(",")):
        tag, _, rest = item.strip().partition(";")
        q = 1.0
        if rest.strip().startswith("q="):
            try:
                q = float(rest.strip()[2:])
            except ValueError:
                q = 0.0
        primary = tag.strip().lower().split("-")[0]
        if primary in langs and q > 0:
            ranked.append((-q, index, primary))
    if ranked:
        return min(ranked)[2]
    return i18n.default_lang()


def error_body(exc: GrunError, lang: str) -> dict:
    body = make_error(exc.code, (), **exc.params)
    body["message"] = exc.message(lang)
    return {"error": body}


def safe_error_body(exc: GrunError, lang: str) -> dict:
    """`error_body`, or a minimal body (message = code) if rendering the error itself fails."""
    try:
        return error_body(exc, lang)
    except Exception:  # noqa: BLE001 - a missing param must not kill the response
        return {"error": {"code": exc.code, "params": {}, "message": exc.code}}


# --- handler -----------------------------------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "grun"
    sys_version = ""
    timeout = READ_TIMEOUT

    def log_message(self, fmt, *args):  # quiet: the application has its own log
        if os.environ.get("GRUN_DEBUG") == "1":
            super().log_message(fmt, *args)

    def send_error(self, code, message=None, explain=None):  # malformed request line etc.
        lang = i18n.default_lang()
        if code == 501:
            exc, status = GrunError("api.method_not_allowed", method=self.command or "?"), 405
        elif code == 404:
            exc, status = GrunError("api.not_found", path=""), 404
        else:
            exc, status = GrunError("api.bad_request"), code if 400 <= code < 500 else 400
        self._write(Reply(status, safe_error_body(exc, lang), json=True))

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionError, TimeoutError):
            self.close_connection = True

    def do_GET(self):
        self._dispatch()

    do_POST = do_PUT = do_GET
    do_HEAD = do_DELETE = do_OPTIONS = do_PATCH = do_GET

    def _write(self, reply: Reply):
        if reply.json:
            data = json.dumps(reply.body, ensure_ascii=False).encode("utf-8")
            ctype = "application/json; charset=utf-8"
        else:
            data = reply.body if isinstance(reply.body, bytes) else str(reply.body).encode("utf-8")
            ctype = reply.content_type
        self.send_response(reply.status)
        for name, value in BASE_HEADERS.items():
            self.send_header(name, value)
        if reply.status != 304:
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
        if "Cache-Control" not in reply.headers:
            self.send_header("Cache-Control", "no-store")
        for name, value in reply.headers.items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD" and reply.status != 304:
            self.wfile.write(data)
        self.close_connection = True

    def _fail(self, exc: GrunError, lang: str):
        extra = getattr(self.server.app, "errors", None)
        self._write(Reply(status_for(exc.code, extra), safe_error_body(exc, lang), json=True))

    def _check_origin(self):
        """Before any route and method: ``Host``, ``Origin`` and ``Sec-Fetch-Site`` must be this server's own."""
        port = self.server.server_address[1]
        hosts = {"127.0.0.1:%d" % port, "localhost:%d" % port}
        host = self.headers.get("Host")
        if host is None or host.lower() not in hosts:
            raise GrunError("api.bad_host")
        origin = self.headers.get("Origin")
        if origin is not None and origin.lower() not in {"http://" + h for h in hosts}:
            raise GrunError("api.bad_origin")
        site = self.headers.get("Sec-Fetch-Site")
        if site is not None and site.lower() not in ("same-origin", "none"):
            raise GrunError("api.bad_origin")

    def _read_body(self):
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            raise GrunError("api.content_type")
        length = self.headers.get("Content-Length")
        if self.headers.get("Transfer-Encoding") or length is None or not length.isascii() or not length.isdigit():
            raise GrunError("api.length_required")
        if len(length) > 8 or int(length) > MAX_BODY:
            raise GrunError("api.body_too_large", limit=MAX_BODY)
        try:
            raw = self.rfile.read(int(length))
        except (TimeoutError, OSError):
            raise GrunError("api.bad_json")
        if len(raw) != int(length):
            raise GrunError("api.bad_json")
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise GrunError("api.bad_json")
        if not isinstance(body, dict):
            raise GrunError("api.bad_json")
        return body

    def _dispatch(self):
        self.server.begin_request()
        try:
            self._dispatch_one()
        finally:
            self.server.end_request()

    def _dispatch_one(self):
        raw, _, qs = self.path.partition("?")
        query = parse_qs(qs, keep_blank_values=True)
        lang = pick_lang(query, self.headers.get("Accept-Language"))
        try:
            self._check_origin()
            if self.command not in ("GET", "POST", "PUT"):
                raise GrunError("api.method_not_allowed", method=self.command)
            body = self._read_body() if self.command in ("POST", "PUT") else None
            segments = split_path(raw)
            reply = self._route(segments, query, body, lang) if segments is not None else None
            if reply is None:
                raise GrunError("api.not_found", path=raw[:200])
            self._write(reply)
        except GrunError as exc:
            self._fail(exc, lang)
        except Exception as exc:  # noqa: BLE001 - nothing but the type and text leaves the process
            self._fail(GrunError("api.unexpected", message="%s: %s" % (type(exc).__name__, exc)), lang)

    def _route(self, segments, query, body, lang):
        wrong_method = False
        for entry in list(self.server.routes):
            params = _match(entry.parts, segments)
            if params is None:
                continue
            if entry.method != self.command:
                wrong_method = True
                continue
            result = entry.handler(Request(self.command, params, query, body, lang, self.server, self.headers))
            return result if isinstance(result, Reply) else Reply(200, result, json=True)
        if wrong_method:
            raise GrunError("api.method_not_allowed", method=self.command)
        return None


# --- generic routes: health and the queue -----------------------------------------------------------------------
def _int_param(name: str, value: str) -> int:
    if not value.isascii() or not value.isdigit() or len(value) > 9:
        raise GrunError("api.bad_param", name=name)
    return int(value)


def _fields(body: dict, allowed: tuple) -> dict:
    for name in body:
        if name not in allowed:
            raise GrunError("api.bad_param", name=name)
    return body


def _move_target(req) -> str:
    to = _fields(req.body, ("to",)).get("to")
    if not isinstance(to, str):
        raise GrunError("api.bad_param", name="to")
    return to


def health(req):
    app = req.app
    return {"ok": True, "api": API_VERSION, "version": app.version, "pid": os.getpid(),
            "port": req.server.server_address[1], "paused": app.queue.is_paused(),
            "worker": app.queue.worker_alive() is True}


def queue_list(req):
    state = (req.query.get("state") or [None])[0]
    if state is not None and state not in STATES:
        raise GrunError("api.bad_param", name="state")
    q = req.app.queue
    entries = q.list_entries(None if state is None else [state])
    out = []
    for entry in entries:
        item = q.entry_view(entry, req.lang)
        item.pop("preview", None)
        out.append(item)
    return Reply(200, out, json=True, headers={"X-Queue-Paused": "1" if q.is_paused() else "0"})


def queue_preview(req):
    entry = req.app.queue.get(_int_param("id", req.params["id"]))
    shown = entry.get("preview")
    if not isinstance(shown, str):
        raise GrunError("api.not_found", path="preview")
    data = req.app.data.resolve()
    try:
        rel = os.path.relpath(Path(shown).resolve(), data)
        path = paths.inside(data, rel)
        with open(path, "rb") as fh:
            if not _stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
                raise GrunError("api.not_found", path="preview")
            body = fh.read()
    except (GrunError, OSError, ValueError, RuntimeError):  # a path that fails the guard is simply not found
        raise GrunError("api.not_found", path="preview") from None
    return Reply(200, body, "image/png", {"Cache-Control": "no-store"})


def queue_cancel(req):
    _fields(req.body, ())
    q = req.app.queue
    return q.entry_view(q.cancel(_int_param("id", req.params["id"])), req.lang)


def queue_move(req):
    to = _move_target(req)
    q = req.app.queue
    return q.entry_view(q.move(_int_param("id", req.params["id"]), to), req.lang)


def queue_batch_cancel(req):
    _fields(req.body, ())
    q = req.app.queue
    return {"entries": [q.entry_view(e, req.lang) for e in q.cancel_batch(_int_param("id", req.params["id"]))]}


def queue_batch_move(req):
    to = _move_target(req)
    q = req.app.queue
    return {"entries": [q.entry_view(e, req.lang) for e in q.move_batch(_int_param("id", req.params["id"]), to)]}


def queue_pause(req):
    _fields(req.body, ())
    return {"paused": True, "changed": req.app.queue.pause()}


def queue_resume(req):
    _fields(req.body, ())
    return {"paused": False, "changed": req.app.queue.resume()}


def queue_clear(req):
    """Cancel the queued entries whose fields equal the body's (``{}`` = all of them)."""
    for name, value in req.body.items():
        if name == "self" or isinstance(value, (dict, list)):
            raise GrunError("api.bad_param", name=name)
    q = req.app.queue
    return [q.entry_view(e, req.lang) for e in q.clear(**req.body)]


DEFAULT_ROUTES = (
    ("GET", "/api/health", health),
    ("GET", "/api/queue", queue_list),
    ("GET", "/api/queue/{id}/preview", queue_preview),
    ("POST", "/api/queue/{id}/cancel", queue_cancel),
    ("POST", "/api/queue/{id}/move", queue_move),
    ("POST", "/api/queue/batches/{id}/cancel", queue_batch_cancel),
    ("POST", "/api/queue/batches/{id}/move", queue_batch_move),
    ("POST", "/api/queue/pause", queue_pause),
    ("POST", "/api/queue/resume", queue_resume),
    ("POST", "/api/queue/clear", queue_clear),
)


# --- server ------------------------------------------------------------------------------------------------------
class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, app):
        super().__init__(address, handler)
        self.app = app
        self.routes: list = []
        self._clock = threading.Lock()
        self.last_activity = time.monotonic()
        self.inflight = 0
        for method, pattern, fn in DEFAULT_ROUTES:
            self.add_route(method, pattern, fn)

    def add_route(self, method: str, pattern: str, handler) -> None:
        """Add a route of the application: ``add_route("GET", "/api/x/{p}", handler)``. A ``{name}`` matches one
        segment. Routes are tried in order, so the generic ones win over a later one with the same shape."""
        self.routes.append(Route(method, tuple(pattern.strip("/").split("/")), handler))

    def begin_request(self) -> None:
        with self._clock:
            self.inflight += 1
            self.last_activity = time.monotonic()

    def end_request(self) -> None:
        with self._clock:
            self.inflight -= 1
            self.last_activity = time.monotonic()

    def activity(self) -> tuple:
        """``(seconds since the last request began or ended, requests in progress)``."""
        with self._clock:
            return time.monotonic() - self.last_activity, self.inflight

    @property
    def port(self) -> int:
        return self.server_address[1]


def make_server(port: int, app, host: str = BIND_HOST) -> Server:
    """Bind ``127.0.0.1:<port>`` (0 = any free port) without serving yet; see `start_thread`.

    Only this host is ever bound: any other `host` is ``net.non_local_host`` (the rule of `grun.ollama`; ``::1`` is a
    local host but this server is IPv4 only, so it is refused too). A port that cannot be bound is
    ``serve.port_busy``."""
    ollama.check_local("http://%s" % (host if ":" not in host else "[%s]" % host))
    if host not in (BIND_HOST, "localhost"):
        raise GrunError("net.non_local_host", host=host)
    try:
        return Server((BIND_HOST, port), Handler, app)
    except OSError:
        raise GrunError("serve.port_busy", port=port) from None


def start_thread(server: Server) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    return thread


# --- one server per application: serve.lock and serve.json ------------------------------------------------------
def lock_path(data) -> Path:
    """``<data>/serve.lock``: held by the running server. Never deleted (invariant 5)."""
    return Path(data) / "serve.lock"


def state_path(data) -> Path:
    """``<data>/serve.json``: pid, port, url, version and start time of the running server."""
    return Path(data) / "serve.json"


def read_state(data):
    """The content of ``serve.json`` if it is a valid state object, else ``None``."""
    try:
        state = fsutil.read_json(state_path(data), None)
    except (OSError, ValueError, RecursionError):
        return None
    if (isinstance(state, dict) and isinstance(state.get("pid"), int) and isinstance(state.get("port"), int)
            and isinstance(state.get("url"), str)):
        return state
    return None


def lock_held(data) -> bool:
    """Is ``serve.lock`` taken by a live process? A pure read: it creates nothing."""
    return fsutil.held(lock_path(data)) is True


@contextlib.contextmanager
def single_instance(data, retry_s: float = LOCK_RETRY_S):
    """Hold ``<data>/serve.lock`` (non-blocking flock) while the server lives; another holder, after `retry_s`, is
    ``serve.already_running``. The lock file is never deleted."""
    path = lock_path(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + retry_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    state = read_state(data)
                    raise GrunError("serve.already_running", url=state["url"] if state else "?") from None
                time.sleep(0.02)
        yield
    finally:
        os.close(fd)  # closing releases the lock


def write_state(server: Server) -> dict:
    """Write ``serve.json`` (0600) for `server` and return it."""
    port = server.server_address[1]
    state = {"pid": os.getpid(), "port": port, "url": "http://127.0.0.1:%d" % port, "version": server.app.version,
             "startedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    path = state_path(server.app.data)
    fsutil.write_json(path, state)
    os.chmod(path, 0o600)
    return state
