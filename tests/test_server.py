import fcntl
import http.client
import json
import os
import socket
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from grun import fsutil, paths, queue, server
from grun.errors import GrunError


class ServerBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        env = mock.patch.dict(os.environ, {"GALIVELOP_STATE_HOME": str(root / "state"), "GALIVELOP_LANG": "en"})
        env.start()
        self.addCleanup(env.stop)
        self.data = root / "data"
        self.q = queue.Queue(self.data)
        self.app = server.App(self.q, self.data, version="9.9")
        self.httpd = server.make_server(0, self.app)
        self.thread = server.start_thread(self.httpd)
        self.addCleanup(self.stop)
        self.port = self.httpd.server_address[1]

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def call(self, method, path, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            hdrs = dict(headers or {})
            data = raw
            if body is not None:
                data = json.dumps(body).encode()
            if data is not None:
                hdrs.setdefault("Content-Type", "application/json")
            conn.request(method, path, body=data, headers=hdrs)
            resp = conn.getresponse()
            payload = resp.read()
            return resp.status, resp, payload
        finally:
            conn.close()

    def json(self, method, path, body=None, **kw):
        status, resp, payload = self.call(method, path, body, **kw)
        return status, json.loads(payload.decode()), resp

    def error(self, method, path, body=None, **kw):
        status, data, _ = self.json(method, path, body, **kw)
        return status, data["error"]["code"], data

    def add(self, n=1, **kw):
        return self.q.enqueue([{"project": "p", "n": i} for i in range(n)], **kw)

    def hold_worker(self):
        path = paths.worker_lock_path(self.data)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        self.addCleanup(os.close, fd)


class SecurityTests(ServerBase):
    def test_a_foreign_host_is_403_bad_host_on_every_method(self):
        for method in ("GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"):
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            conn.putrequest(method, "/api/health", skip_host=True)
            conn.putheader("Host", "evil.example:%d" % self.port)
            conn.endheaders()
            resp = conn.getresponse()
            body = resp.read()
            conn.close()
            self.assertEqual(resp.status, 403, method)
            if method != "HEAD":
                self.assertEqual(json.loads(body)["error"]["code"], "api.bad_host", method)

    def test_the_host_needs_this_port(self):
        self.assertEqual(self.error("GET", "/api/health", headers={"Host": "127.0.0.1:1"})[:2], (403, "api.bad_host"))
        self.assertEqual(self.error("GET", "/api/health", headers={"Host": "127.0.0.1"})[:2], (403, "api.bad_host"))

    def test_localhost_with_the_port_is_accepted(self):
        status, data, _ = self.json("GET", "/api/health", headers={"Host": "localhost:%d" % self.port})
        self.assertEqual((status, data["ok"]), (200, True))

    def test_a_foreign_origin_is_403_bad_origin(self):
        for origin in ("http://evil.example", "http://127.0.0.1:1", "null"):
            self.assertEqual(self.error("GET", "/api/health", headers={"Origin": origin})[:2],
                             (403, "api.bad_origin"), origin)

    def test_the_own_origin_is_accepted(self):
        status, _, _ = self.json("GET", "/api/health", headers={"Origin": "http://127.0.0.1:%d" % self.port})
        self.assertEqual(status, 200)

    def test_sec_fetch_site(self):
        for site in ("cross-site", "same-site"):
            self.assertEqual(self.error("GET", "/api/health", headers={"Sec-Fetch-Site": site})[:2],
                             (403, "api.bad_origin"), site)
        for site in ("same-origin", "none"):
            self.assertEqual(self.json("GET", "/api/health", headers={"Sec-Fetch-Site": site})[0], 200, site)

    def test_the_check_comes_before_the_route_and_the_body(self):
        status, code, _ = self.error("POST", "/api/nothing/here", raw=b"not json", headers={"Host": "x:1"})
        self.assertEqual((status, code), (403, "api.bad_host"))

    def test_the_message_is_rendered_in_the_asked_language(self):
        _, _, data = self.error("GET", "/api/health", headers={"Host": "x:1", "Accept-Language": "es"})
        self.assertEqual(data["error"]["message"], "la cabecera Host no es la de este servidor local")
        _, _, data = self.error("GET", "/api/health?lang=en", headers={"Host": "x:1"})
        self.assertIn("Host header", data["error"]["message"])


class RequestErrorTests(ServerBase):
    def test_unknown_path_and_wrong_method(self):
        self.assertEqual(self.error("GET", "/api/nothing")[:2], (404, "api.not_found"))
        self.assertEqual(self.error("GET", "/")[:2], (404, "api.not_found"))
        self.assertEqual(self.error("GET", "/api/queue/pause")[:2], (405, "api.method_not_allowed"))
        self.assertEqual(self.error("DELETE", "/api/health")[:2], (405, "api.method_not_allowed"))

    def test_bodies(self):
        self.assertEqual(self.error("POST", "/api/queue/pause", raw=b"{}", headers={"Content-Type": "text/plain"})[:2],
                         (415, "api.content_type"))
        self.assertEqual(self.error("POST", "/api/queue/pause", raw=b"[]")[:2], (400, "api.bad_json"))
        self.assertEqual(self.error("POST", "/api/queue/pause", raw=b"{")[:2], (400, "api.bad_json"))
        self.assertEqual(self.error("POST", "/api/queue/pause", body={"x": 1})[:2], (400, "api.bad_param"))
        with mock.patch.object(server, "MAX_BODY", 4):
            self.assertEqual(self.error("POST", "/api/queue/pause", raw=b"{ }  ")[:2], (413, "api.body_too_large"))

    def test_an_unexpected_exception_is_500_api_unexpected(self):
        def boom(req):
            raise RuntimeError("boom")
        self.httpd.add_route("GET", "/api/boom", boom)
        status, code, data = self.error("GET", "/api/boom")
        self.assertEqual((status, code), (500, "api.unexpected"))
        self.assertIn("RuntimeError: boom", data["error"]["params"]["message"])

    def test_the_error_body_has_code_params_and_message(self):
        _, _, data = self.error("POST", "/api/queue/9/cancel", body={})
        self.assertEqual(data["error"]["code"], "queue.unknown")
        self.assertEqual(data["error"]["params"], {"id": "9"})
        self.assertIn("9", data["error"]["message"])


class AddRouteTests(ServerBase):
    def test_application_routes_and_their_errors_with_the_application_table(self):
        self.app.errors = {"exact": {422: ("img.blocked",)}}
        seen = {}

        def mine(req):
            seen["params"], seen["lang"], seen["app"] = req.params, req.lang, req.app
            return {"p": req.params["p"]}

        def blocked(req):
            raise GrunError("img.blocked", why="x")
        self.httpd.add_route("GET", "/api/projects/{p}", mine)
        self.httpd.add_route("POST", "/api/blocked", blocked)
        self.assertEqual(self.json("GET", "/api/projects/zed")[:2], (200, {"p": "zed"}))
        self.assertIs(seen["app"], self.app)
        self.assertEqual(self.error("POST", "/api/blocked", body={})[:2], (422, "img.blocked"))

    def test_a_segment_matches_only_one_segment(self):
        self.httpd.add_route("GET", "/api/x/{p}", lambda req: {})
        self.assertEqual(self.error("GET", "/api/x/a%2Fb")[:2], (404, "api.not_found"))
        self.assertEqual(self.error("GET", "/api/x/a/b")[:2], (404, "api.not_found"))
        self.assertEqual(self.json("GET", "/api/x/a")[0], 200)


class StatusTableTests(unittest.TestCase):
    def test_exact(self):
        for code, status in (("api.bad_host", 403), ("api.bad_origin", 403), ("queue.unknown", 404),
                             ("queue.batch_not_found", 404), ("api.not_found", 404), ("api.method_not_allowed", 405),
                             ("api.length_required", 411), ("api.body_too_large", 413), ("api.content_type", 415),
                             ("serve.already_running", 409), ("serve.port_busy", 409), ("queue.not_cancellable", 409),
                             ("queue.not_movable", 409), ("queue.not_running", 409), ("queue.bad_state", 409),
                             ("queue.bad_move", 400), ("api.bad_param", 400), ("api.bad_json", 400)):
            self.assertEqual(server.status_for(code), status, code)

    def test_server_faults_come_before_the_bad_pattern(self):
        self.assertEqual(server.status_for("queue.bad_progress"), 500)
        self.assertEqual(server.status_for("x.bad_thing"), 400)

    def test_exact_comes_before_bad(self):
        self.assertEqual(server.status_for("api.bad_host"), 403)
        self.assertEqual(server.status_for("queue.bad_state"), 409)

    def test_prefix_comes_before_bad_and_suffix(self):
        self.assertEqual(server.status_for("path.outside"), 400)
        self.assertEqual(server.status_for("net.non_local_host"), 400)
        self.assertEqual(server.status_for("x.y", {"prefix": (("x.", 422),)}), 422)
        self.assertEqual(server.status_for("x.bad_y", {"prefix": (("x.", 422),)}), 422)

    def test_bad_comes_before_suffix(self):
        self.assertEqual(server.status_for("a.bad_unknown"), 400)
        self.assertEqual(server.status_for("a.bad_x", {"suffix": ((".bad_x", 418),)}), 400)

    def test_suffix_then_default_500(self):
        self.assertEqual(server.status_for("a.invalid"), 400)
        self.assertEqual(server.status_for("a.b_invalid"), 400)
        self.assertEqual(server.status_for("a.unknown"), 400)
        self.assertEqual(server.status_for("a.thing", {"suffix": ((".thing", 418),)}), 418)
        self.assertEqual(server.status_for("whatever.else"), 500)
        self.assertEqual(server.status_for("queue.corrupt"), 500)

    def test_the_application_table_comes_first_at_each_step(self):
        extra = {"faults": ("img.bad_pixel",), "exact": {422: ("img.blocked", "queue.unknown")}}
        self.assertEqual(server.status_for("img.bad_pixel", extra), 500)
        self.assertEqual(server.status_for("img.bad_pixel"), 400)
        self.assertEqual(server.status_for("img.blocked", extra), 422)
        self.assertEqual(server.status_for("queue.unknown", extra), 422)
        self.assertEqual(server.status_for("queue.unknown"), 404)

    def test_a_fault_of_the_application_beats_its_own_exact(self):
        extra = {"faults": ("a.b",), "exact": {422: ("a.b",)}}
        self.assertEqual(server.status_for("a.b", extra), 500)


class MakeServerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name).resolve() / "data"
        self.app = server.App(queue.Queue(self.data), self.data)

    def code(self, fn, *args, **kw):
        with self.assertRaises(GrunError) as ctx:
            fn(*args, **kw)
        return ctx.exception.code, ctx.exception.params

    def test_binds_only_to_loopback_and_port_zero_is_free(self):
        httpd = server.make_server(0, self.app)
        self.addCleanup(httpd.server_close)
        host, port = httpd.server_address
        self.assertEqual(host, "127.0.0.1")
        self.assertGreater(port, 0)

    def test_non_local_host_is_net_non_local_host(self):
        for host in ("0.0.0.0", "example.com", "192.168.1.5", "::"):
            self.assertEqual(self.code(server.make_server, 0, self.app, host=host),
                             ("net.non_local_host", {"host": host}), host)

    def test_ipv6_loopback_is_refused_with_the_same_code(self):
        self.assertEqual(self.code(server.make_server, 0, self.app, host="::1")[0], "net.non_local_host")

    def test_localhost_binds_to_the_loopback_address(self):
        httpd = server.make_server(0, self.app, host="localhost")
        self.addCleanup(httpd.server_close)
        self.assertEqual(httpd.server_address[0], "127.0.0.1")

    def test_a_busy_port_is_serve_port_busy(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen()
            port = sock.getsockname()[1]
            self.assertEqual(self.code(server.make_server, port, self.app), ("serve.port_busy", {"port": port}))

    def test_texts_exist_in_every_language(self):
        for lang in ("en", "es"):
            for code in ("serve.port_busy", "serve.already_running", "api.bad_host", "api.bad_origin"):
                text = GrunError(code, port=1, url="u").message(lang)
                self.assertNotEqual(text, "error." + code, (lang, code))


class HealthTests(ServerBase):
    def test_health(self):
        status, data, _ = self.json("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(data, {"ok": True, "api": 1, "version": "9.9", "pid": os.getpid(), "port": self.port,
                                "paused": False, "worker": False})

    def test_health_sees_the_pause_and_the_worker(self):
        self.q.pause()
        self.hold_worker()
        data = self.json("GET", "/api/health")[1]
        self.assertEqual((data["paused"], data["worker"]), (True, True))


class QueueRouteTests(ServerBase):
    def test_list_with_state_filter_and_pause_header(self):
        self.add(2)
        self.hold_worker()
        self.q.claim()
        status, data, resp = self.json("GET", "/api/queue")
        self.assertEqual((status, [e["state"] for e in data], resp.getheader("X-Queue-Paused")),
                         (200, ["running", "queued"], "0"))
        self.assertEqual([e["id"] for e in self.json("GET", "/api/queue?state=queued")[1]], [2])
        self.q.pause()
        self.assertEqual(self.json("GET", "/api/queue")[2].getheader("X-Queue-Paused"), "1")

    def test_list_rejects_an_unknown_state_and_hides_the_preview_path(self):
        self.assertEqual(self.error("GET", "/api/queue?state=bogus")[:2], (400, "api.bad_param"))
        self.add()
        self.hold_worker()
        self.q.claim()
        self.q.set_preview(1, str(self.data / "p.png"))
        self.assertNotIn("preview", self.json("GET", "/api/queue")[1][0])

    def test_preview(self):
        self.add(2)
        self.hold_worker()
        self.q.claim()
        (self.data / "p.png").write_bytes(b"\x89PNG-bytes")
        self.q.set_preview(1, str(self.data / "p.png"))
        status, resp, payload = self.call("GET", "/api/queue/1/preview")
        self.assertEqual((status, resp.getheader("Content-Type"), payload), (200, "image/png", b"\x89PNG-bytes"))
        self.assertEqual(self.error("GET", "/api/queue/2/preview")[:2], (404, "api.not_found"))
        self.assertEqual(self.error("GET", "/api/queue/9/preview")[:2], (404, "queue.unknown"))
        self.assertEqual(self.error("GET", "/api/queue/x/preview")[:2], (400, "api.bad_param"))

    def test_preview_outside_the_data_folder_or_missing_is_not_found(self):
        self.add(2)
        self.hold_worker()
        self.q.claim()
        outside = self.data.parent / "secret.png"
        outside.write_bytes(b"secret")
        self.q.set_preview(1, str(outside))
        self.assertEqual(self.error("GET", "/api/queue/1/preview")[:2], (404, "api.not_found"))
        self.q.finish(1, "done")
        self.q.claim()
        self.q.set_preview(2, str(self.data / "gone.png"))
        self.assertEqual(self.error("GET", "/api/queue/2/preview")[:2], (404, "api.not_found"))

    def test_cancel(self):
        self.add(2)
        status, data, _ = self.json("POST", "/api/queue/1/cancel", {})
        self.assertEqual((status, data["state"]), (200, "cancelled"))
        self.assertEqual(self.error("POST", "/api/queue/1/cancel", {})[:2], (409, "queue.not_cancellable"))
        self.assertEqual(self.error("POST", "/api/queue/7/cancel", {})[:2], (404, "queue.unknown"))

    def test_move(self):
        self.add(3)
        status, data, _ = self.json("POST", "/api/queue/3/move", {"to": "top"})
        self.assertEqual((status, data["id"]), (200, 3))
        self.assertEqual([e["id"] for e in self.q.list_entries(["queued"])][0:1], [1])
        self.assertEqual(self.q.next_queued()["id"], 3)
        self.assertEqual(self.error("POST", "/api/queue/3/move", {"to": "sideways"})[:2], (400, "queue.bad_move"))
        self.assertEqual(self.error("POST", "/api/queue/3/move", {"to": 1})[:2], (400, "api.bad_param"))
        self.assertEqual(self.error("POST", "/api/queue/3/move", {})[:2], (400, "api.bad_param"))
        self.q.cancel(3)
        self.assertEqual(self.error("POST", "/api/queue/3/move", {"to": "up"})[:2], (409, "queue.not_movable"))

    def test_batch_cancel_and_move(self):
        self.add(2)
        first = self.add(2)
        batch = first[0]["batch"]["id"]
        status, data, _ = self.json("POST", "/api/queue/batches/%d/move" % batch, {"to": "top"})
        self.assertEqual(status, 200)
        self.assertEqual([e["id"] for e in data["entries"]], [e["id"] for e in first])
        self.assertEqual(self.q.next_queued()["id"], first[0]["id"])
        status, data, _ = self.json("POST", "/api/queue/batches/%d/cancel" % batch, {})
        self.assertEqual((status, [e["state"] for e in data["entries"]]), (200, ["cancelled", "cancelled"]))
        self.assertEqual(self.error("POST", "/api/queue/batches/%d/cancel" % batch, {})[:2],
                         (409, "queue.not_cancellable"))
        self.assertEqual(self.error("POST", "/api/queue/batches/%d/move" % batch, {"to": "up"})[:2],
                         (409, "queue.not_movable"))
        self.assertEqual(self.error("POST", "/api/queue/batches/99/cancel", {})[:2], (404, "queue.batch_not_found"))
        self.assertEqual(self.error("POST", "/api/queue/batches/99/move", {"to": "up"})[:2],
                         (404, "queue.batch_not_found"))

    def test_pause_resume(self):
        self.assertEqual(self.json("POST", "/api/queue/pause", {})[1], {"paused": True, "changed": True})
        self.assertTrue(self.q.is_paused())
        self.assertEqual(self.json("POST", "/api/queue/pause", {})[1], {"paused": True, "changed": False})
        self.assertEqual(self.json("POST", "/api/queue/resume", {})[1], {"paused": False, "changed": True})
        self.assertFalse(self.q.is_paused())
        self.assertEqual(self.json("POST", "/api/queue/resume", {})[1], {"paused": False, "changed": False})

    def test_clear_all_or_by_field(self):
        self.q.enqueue([{"project": "a"}, {"project": "b"}, {"project": "a"}])
        data = self.json("POST", "/api/queue/clear", {"project": "a"})[1]
        self.assertEqual([e["id"] for e in data], [1, 3])
        self.assertEqual([e["id"] for e in self.q.list_entries(["queued"])], [2])
        self.assertEqual([e["id"] for e in self.json("POST", "/api/queue/clear", {})[1]], [2])
        self.assertEqual(self.error("POST", "/api/queue/clear", {"project": ["a"]})[:2], (400, "api.bad_param"))
        self.assertEqual(self.error("POST", "/api/queue/clear", {"self": 1})[:2], (400, "api.bad_param"))

    def test_clear_does_not_touch_a_running_entry(self):
        self.add(2)
        self.hold_worker()
        self.q.claim()
        self.assertEqual([e["id"] for e in self.json("POST", "/api/queue/clear", {})[1]], [2])
        self.assertEqual(self.q.get(1)["state"], "running")

    def test_a_running_entry_is_cancel_requested(self):
        self.add()
        self.hold_worker()
        self.q.claim()
        data = self.json("POST", "/api/queue/1/cancel", {})[1]
        self.assertTrue(data["cancelRequested"])


class SingleInstanceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name).resolve() / "data"

    def test_a_second_holder_is_serve_already_running_with_the_url(self):
        with server.single_instance(self.data):
            self.assertTrue(server.lock_held(self.data))
            fsutil.write_json(server.state_path(self.data),
                              {"pid": 1, "port": 5, "url": "http://127.0.0.1:5", "version": "x", "startedAt": "t"})
            with self.assertRaises(GrunError) as ctx:
                with server.single_instance(self.data, retry_s=0.05):
                    self.fail("the second instance must not start")
            self.assertEqual(ctx.exception.code, "serve.already_running")
            self.assertEqual(ctx.exception.params, {"url": "http://127.0.0.1:5"})
            self.assertEqual(server.status_for(ctx.exception.code), 409)

    def test_without_state_the_url_is_a_question_mark(self):
        with server.single_instance(self.data):
            with self.assertRaises(GrunError) as ctx:
                with server.single_instance(self.data, retry_s=0.0):
                    pass
            self.assertEqual(ctx.exception.params, {"url": "?"})

    def test_the_lock_is_released_and_never_deleted(self):
        with server.single_instance(self.data):
            pass
        self.assertTrue(server.lock_path(self.data).exists())
        self.assertFalse(server.lock_held(self.data))
        with server.single_instance(self.data):
            pass

    def test_lock_held_creates_nothing(self):
        self.assertFalse(server.lock_held(self.data))
        self.assertFalse(self.data.exists())

    def test_serve_json_is_0600_and_complete(self):
        app = server.App(queue.Queue(self.data), self.data, version="1.2")
        httpd = server.make_server(0, app)
        self.addCleanup(httpd.server_close)
        state = server.write_state(httpd)
        port = httpd.server_address[1]
        self.assertEqual(set(state), {"pid", "port", "url", "version", "startedAt"})
        self.assertEqual((state["pid"], state["port"], state["url"], state["version"]),
                         (os.getpid(), port, "http://127.0.0.1:%d" % port, "1.2"))
        path = server.state_path(self.data)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(server.read_state(self.data), state)

    def test_read_state_ignores_an_invalid_file(self):
        self.assertIsNone(server.read_state(self.data))
        self.data.mkdir(parents=True)
        for text in ("not json", "[]", '{"pid": "x", "port": 1, "url": "u"}'):
            server.state_path(self.data).write_text(text)
            self.assertIsNone(server.read_state(self.data), text)


if __name__ == "__main__":
    unittest.main()
