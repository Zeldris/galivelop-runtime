import os
import socket
import threading
import unittest
from unittest import mock

from grun import machine_lock, ollama
from grun.errors import GrunError
from tests.fake_ollama import FakeOllama

MODEL = {"name": "llama3:8b", "size": 5000}


def closed_port_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return "http://127.0.0.1:%d" % s.getsockname()[1]


class CheckLocalTests(unittest.TestCase):
    def code(self, url):
        with self.assertRaises(GrunError) as cm:
            ollama.check_local(url)
        return cm.exception

    def test_local_hosts_pass_and_lose_the_trailing_slash(self):
        for url in ("http://localhost:11434", "https://127.0.0.1:1/", "http://[::1]:11434/", "http://LOCALHOST"):
            self.assertEqual(ollama.check_local(url), url.rstrip("/"))

    def test_invariant_11_other_host(self):  # invariant 11
        err = self.code("http://example.com:11434")
        self.assertEqual((err.code, err.params["host"]), ("net.non_local_host", "example.com"))
        self.assertEqual(self.code("http://localhost.evil.com").code, "net.non_local_host")
        self.assertEqual(self.code("http://user@example.com@localhost.x").code, "net.non_local_host")

    def test_invariant_11_other_scheme(self):  # invariant 11
        for url in ("ftp://localhost", "file:///etc/passwd", "localhost:11434", "", None):
            self.assertEqual(self.code(url).code, "engine.ollama_url", url)


class LoadedTests(unittest.TestCase):
    def test_lists_models_with_size(self):
        with FakeOllama([MODEL, {"name": "idle", "size": 0}, {"name": "nosize"}]) as fake:
            self.assertEqual(ollama.loaded(fake.url), ["llama3:8b"])

    def test_errors_are_empty(self):
        self.assertEqual(ollama.loaded(closed_port_url(), timeout=1), [])
        for body in (b"not json", b"[]", b'{"models": 3}', b'{"models": [1, null]}'):
            with FakeOllama(ps_body=body) as fake:
                self.assertEqual(ollama.loaded(fake.url), [], body)

    def test_more_than_one_mib_is_empty(self):
        body = b'{"models": [{"name": "a", "size": 1}], "pad": "' + b"x" * (1024 * 1024) + b'"}'
        with FakeOllama(ps_body=body) as fake:
            self.assertEqual(ollama.loaded(fake.url), [])

    def test_does_not_use_a_proxy(self):
        with FakeOllama([MODEL]) as fake, mock.patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:9",
                                                                       "HTTP_PROXY": "http://127.0.0.1:9"}):
            self.assertEqual(ollama.loaded(fake.url), ["llama3:8b"])


class UnloadTests(unittest.TestCase):
    def test_posts_generate_and_embed(self):
        with FakeOllama([MODEL]) as fake:
            ollama.unload(fake.url, "llama3:8b")
            self.assertEqual(fake.requests, [
                ("POST", "/api/generate", {"model": "llama3:8b", "keep_alive": 0}),
                ("POST", "/api/embed", {"model": "llama3:8b", "input": "", "keep_alive": 0})])

    def test_errors_are_ignored(self):
        ollama.unload(closed_port_url(), "x", timeout=1)


class RedirectTests(unittest.TestCase):  # invariant 11
    """A 3xx is never followed: the target (another fake, standing for a non-local host) gets nothing."""

    def test_ps_redirect_is_not_followed(self):
        with FakeOllama(models=[{"name": "m", "size": 5}]) as target, FakeOllama(redirect=None) as src:
            src.redirect = target.url
            self.assertEqual(ollama.loaded(src.url), [])
            self.assertEqual(src.paths(), [("GET", "/api/ps")])
            self.assertEqual(target.requests, [])

    def test_redirect_is_an_http_error(self):
        with FakeOllama() as target, FakeOllama() as src:
            src.redirect = target.url
            with self.assertRaises(ollama.urllib.error.HTTPError) as cm:
                ollama._request(src.url, "/api/ps")
            self.assertEqual(cm.exception.code, 302)
            self.assertEqual(target.requests, [])

    def test_unload_redirect_is_not_followed(self):
        with FakeOllama(models=[{"name": "m", "size": 5}]) as target, FakeOllama() as src:
            src.redirect = target.url
            ollama.unload(src.url, "m")
            self.assertEqual(src.paths(), [("POST", "/api/generate"), ("POST", "/api/embed")])
            self.assertEqual(target.requests, [])
            self.assertEqual(target.models, [{"name": "m", "size": 5}])


class EvictTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"GRUN_OLLAMA_URL": ""})
        env.start()
        self.addCleanup(env.stop)

    def machine(self, url, mode=None):
        engine = {"ollamaUrl": url}
        if mode:
            engine["ollama"] = mode
        return {"timeoutS": 1, "engine": engine}

    def test_unload_is_the_default_and_waits(self):
        with FakeOllama([MODEL]) as fake:
            self.assertEqual(ollama.evict(self.machine(fake.url), wait_s=2, poll_s=0.01), ["llama3:8b"])
            self.assertEqual(fake.models, [])

    def test_nothing_loaded_does_not_unload(self):
        with FakeOllama([]) as fake:
            self.assertEqual(ollama.evict(self.machine(fake.url)), [])
            self.assertEqual(fake.paths(), [("GET", "/api/ps")])

    def test_unload_that_does_not_happen_is_an_error(self):
        with FakeOllama([MODEL], unloads=False) as fake:
            with self.assertRaises(GrunError) as cm:
                ollama.evict(self.machine(fake.url, "unload"), wait_s=0.1, poll_s=0.01)
        self.assertEqual(cm.exception.code, "engine.ollama_loaded")
        self.assertIn("llama3:8b", cm.exception.params["models"])

    def test_abort_with_models_does_not_unload(self):
        with FakeOllama([MODEL]) as fake:
            with self.assertRaises(GrunError) as cm:
                ollama.evict(self.machine(fake.url, "abort"))
            self.assertEqual(cm.exception.code, "engine.ollama_loaded")
            self.assertEqual(fake.paths(), [("GET", "/api/ps")])

    def test_abort_without_models_passes(self):
        with FakeOllama([]) as fake:
            self.assertEqual(ollama.evict(self.machine(fake.url, "abort")), [])

    def test_ignore_does_not_call(self):
        with FakeOllama([MODEL]) as fake:
            self.assertEqual(ollama.evict(self.machine(fake.url, "ignore")), [])
            self.assertEqual(fake.requests, [])

    def test_ollama_off_is_nothing_loaded(self):
        self.assertEqual(ollama.evict(self.machine(closed_port_url()), wait_s=0.1), [])

    def test_wait_is_cancellable_invariant_4(self):  # invariant 4
        with FakeOllama([MODEL], unloads=False) as fake:
            with self.assertRaises(machine_lock.WaitCancelled):
                ollama.evict(self.machine(fake.url), lambda: True, wait_s=30, poll_s=0.01)

    def test_wait_polls_should_cancel_each_round(self):
        calls = []

        def should_cancel():
            calls.append(1)
            return len(calls) >= 3

        with FakeOllama([MODEL], unloads=False) as fake:
            with self.assertRaises(machine_lock.WaitCancelled):
                ollama.evict(self.machine(fake.url), should_cancel, wait_s=30, poll_s=0.01)
        self.assertEqual(len(calls), 3)

    def test_url_from_environment_wins_and_is_checked_invariant_11(self):  # invariant 11
        with FakeOllama([]) as fake:
            with mock.patch.dict(os.environ, {"GRUN_OLLAMA_URL": fake.url}):
                self.assertEqual(ollama.evict(self.machine("http://example.com")), [])
        for bad, code in (("http://example.com:11434", "net.non_local_host"), ("ftp://localhost", "engine.ollama_url")):
            with mock.patch.dict(os.environ, {"GRUN_OLLAMA_URL": bad}):
                for mode in ("unload", "abort", "ignore"):
                    with self.assertRaises(GrunError) as cm:
                        ollama.evict(self.machine("http://localhost:1", mode))
                    self.assertEqual(cm.exception.code, code)

    def test_profile_url_is_checked(self):
        with self.assertRaises(GrunError) as cm:
            ollama.evict(self.machine("http://example.com"))
        self.assertEqual(cm.exception.code, "net.non_local_host")

    def test_default_url(self):
        seen = []
        with mock.patch.object(ollama, "loaded", side_effect=lambda url, *a: seen.append(url) or []):
            ollama.evict({"timeoutS": 1})
        self.assertEqual(seen, ["http://localhost:11434"])


if __name__ == "__main__":
    unittest.main()
