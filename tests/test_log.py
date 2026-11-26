"""Registro JSONL de operaciones y estimación de duración.

Copiado de gvoice@8a17618 (tests/test_log.py); adaptado: nombre de aplicación como parámetro, campos sin el
prefijo `app.voice.`, sin operaciones ni campos propios de voz."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from grun import log
from grun.errors import GrunError

APP = "galivelop-test"
SPEC = {"seed": 5, "model": "0.6b-base", "device": "Vulkan0"}
MACHINE = {"name": "steam-deck"}


def line(duration, op="run", model="0.6b-base", device="Vulkan0", provider="fake", **extra):
    d = {"gen_ai.provider.name": provider, "gen_ai.operation.name": op, "gen_ai.request.model": model,
         "app.device": device, "app.duration_ms": duration}
    d.update(extra)
    return d


class LogTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        env = mock.patch.dict(os.environ, {"GALIVELOP_TEST_DATA_HOME": str(self.tmp / "d")})
        env.start()
        self.addCleanup(env.stop)

    def put(self, *records):
        for r in records:
            log.append(APP, "proj", r)

    def test_env_reaches_the_data_dir(self):
        app = "galivelop-voice"
        rec = line(100)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"GVOICE_DATA_HOME": tmp}):
                log.append(app, "p", rec, env="GVOICE_DATA_HOME")
                self.assertTrue((Path(tmp) / "projects" / "p" / "log.jsonl").is_file())
                self.assertEqual(log.log_path(app, "p", env="GVOICE_DATA_HOME"),
                                 Path(tmp).resolve() / "projects" / "p" / "log.jsonl")
                self.assertEqual(log.estimate(app, "p", "fake", "run", "0.6b-base", "Vulkan0",
                                              env="GVOICE_DATA_HOME"), 100)

    def est(self, op="run", model="0.6b-base", device="Vulkan0"):
        return log.estimate(APP, "proj", "fake", op, model, device)

    def test_record_carries_min_free_and_peak_rss_when_known(self):
        res = SimpleNamespace(duration_ms=1, min_free_mb=3100, peak_rss_mb=2048)
        rec = log.record_for("k", "t", SPEC, MACHINE, "fake", "run", result=res)
        self.assertEqual((rec["app.min_free_mb"], rec["app.peak_rss_mb"]), (3100, 2048))
        rec = log.record_for("k", "t", SPEC, MACHINE, "fake", "run", result=SimpleNamespace(duration_ms=1))
        self.assertNotIn("app.peak_rss_mb", rec)
        self.assertNotIn("app.min_free_mb", rec)

    def test_failed_run_stats_are_used_and_the_result_wins(self):
        rec = log.record_for("k", "t", SPEC, MACHINE, "fake", "run", error="boom",
                             stats={"min_free_mb": 10, "peak_rss_mb": 20})
        self.assertEqual((rec["app.min_free_mb"], rec["app.peak_rss_mb"]), (10, 20))
        res = SimpleNamespace(min_free_mb=11)
        rec = log.record_for("k", "t", SPEC, MACHINE, "fake", "run", result=res, stats={"min_free_mb": 10})
        self.assertEqual(rec["app.min_free_mb"], 11)

    def test_record_success_fields(self):
        res = SimpleNamespace(duration_ms=120, engine_version="fake-1", device="Vulkan0", seed=5,
                              engine_commit="abc123", model="0.6b-base", load_ms=0, backend="fake")
        rec = log.record_for("k/1", "line", SPEC, MACHINE, "fake", "run", result=res, ts="2026-01-01T00:00:00Z")
        self.assertEqual(rec, {
            "ts": "2026-01-01T00:00:00Z", "gen_ai.operation.name": "run", "gen_ai.provider.name": "fake",
            "gen_ai.request.model": "0.6b-base", "app.task": "line", "app.machine_profile": "steam-deck",
            "app.duration_ms": 120, "app.load_ms": 0, "app.key": "k/1", "app.seed": 5, "app.device": "Vulkan0",
            "app.engine_commit": "abc123", "app.engine_version": "fake-1", "app.backend": "fake"})

    def test_result_wins_over_spec(self):
        res = SimpleNamespace(device="cpu", seed=9, model="1.7b-base")
        rec = log.record_for("k", "t", SPEC, MACHINE, "fake", "run", result=res)
        self.assertEqual((rec["app.device"], rec["app.seed"], rec["gen_ai.request.model"]),
                         ("cpu", 9, "1.7b-base"))

    def test_record_error_and_no_nulls(self):
        rec = log.record_for("k", "t", {"seed": 0}, MACHINE, "fake", "design", error="boom")
        self.assertEqual(rec["app.error"], "boom")
        self.assertEqual(rec["gen_ai.operation.name"], "design")
        self.assertNotIn("app.duration_ms", rec)
        self.assertEqual(rec["app.seed"], 0)
        self.assertNotIn(None, rec.values())
        self.assertRegex(rec["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_append_writes_jsonl_under_the_app_data_dir(self):
        self.put({"a": 1}, {"b": "é"})
        path = self.tmp / "d" / "projects" / "proj" / "log.jsonl"
        self.assertEqual([json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()],
                         [{"a": 1}, {"b": "é"}])
        self.assertEqual(log.log_path(APP, "proj"), path)

    def test_bad_project_names(self):
        for bad in ("../x", "a/b", "", "/etc", ".", "..", "A", "-x", "a\n", "a b"):
            with self.assertRaises(GrunError) as cm:
                log.log_path(APP, bad)
            self.assertEqual(cm.exception.code, "log.bad_project", bad)
            self.assertEqual(cm.exception.params, {"project": bad})
            self.assertIn(bad, cm.exception.message("en"))

    def test_estimate_none(self):
        self.assertIsNone(self.est())

    def test_estimate_median_odd_even(self):
        self.put(line(100), line(300), line(200))
        self.assertEqual(self.est(), 200)
        self.put(line(1000))
        self.assertEqual(self.est(), 250)

    def test_estimate_filters(self):
        self.put(line(100), line(900, op="design"), line(900, model="1.7b-base"), line(900, device="cpu"),
                 line(900, provider="qwen"), line(900, **{"app.error": "x"}), line(True))
        self.assertEqual(self.est(), 100)
        self.assertEqual(self.est(op="design"), 900)
        self.assertEqual(self.est(model="1.7b-base"), 900)
        self.assertEqual(self.est(device="cpu"), 900)
        self.assertIsNone(self.est(op="other"))

    def test_estimate_skips_malformed(self):
        self.put(line(100))
        path = self.tmp / "d" / "projects" / "proj" / "log.jsonl"
        with open(path, "a") as fh:
            fh.write("{not json\n[1]\n\n" + json.dumps(line("x")) + "\n")
        self.put(line(300))
        self.assertEqual(self.est(), 200)


if __name__ == "__main__":
    unittest.main()
