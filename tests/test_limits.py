"""Límites de memoria y modelos de un perfil de máquina.

Copiado de gvoice@8a17618 (tests/test_limits.py); adaptado: sin la carga de perfiles (`load_machine`),
variables `GALIVELOP_MEMINFO` y `GALIVELOP_PROC_STATUS`."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from grun import limits
from grun.errors import GrunError

STEAM = {"name": "steam-deck", "minFreeMemoryMb": 4096, "watchMemoryMb": 1536, "timeoutS": 900,
         "models": {"design": "1.7b-voicedesign", "produce": ["0.6b-base", "1.7b-base"]}}
MIN = {"name": "tiny", "minFreeMemoryMb": 1, "watchMemoryMb": 1, "timeoutS": 9,
       "models": {"design": "1.7b-voicedesign", "produce": ["0.6b-base"]}}


class CheckTests(unittest.TestCase):
    def test_timeout(self):
        self.assertEqual(limits.timeout_s(STEAM), 900)

    def test_memory_start_limit(self):
        limits.check_memory(4096, STEAM)
        with self.assertRaises(limits.LimitError) as cm:
            limits.check_memory(4095, STEAM)
        self.assertIsInstance(cm.exception, GrunError)
        self.assertEqual((cm.exception.code, cm.exception.params), ("limit.memory", {"free": 4095, "min": 4096}))
        limits.check_memory(None, STEAM)
        limits.check_memory(1, {})

    def test_abort_below_watch_memory(self):
        self.assertFalse(limits.must_abort(1536, STEAM))
        self.assertTrue(limits.must_abort(1535, STEAM))
        self.assertFalse(limits.must_abort(None, STEAM))
        self.assertFalse(limits.must_abort(1, {}))

    def test_models_by_use(self):
        limits.check_model("design", "1.7b-voicedesign", STEAM)
        limits.check_model("produce", "1.7b-base", STEAM)
        with self.assertRaises(limits.LimitError) as cm:
            limits.check_model("produce", "1.7b-base", MIN)
        self.assertEqual(cm.exception.code, "limit.model")
        self.assertEqual(cm.exception.params, {"model": "1.7b-base", "use": "produce", "allowed": "0.6b-base"})
        with self.assertRaises(limits.LimitError) as cm:
            limits.check_model("design", "0.6b-base", STEAM)
        self.assertEqual(cm.exception.params["allowed"], "1.7b-voicedesign")
        limits.check_model("produce", "anything", {})

    def test_messages_translated(self):
        for lang in ("es", "en"):
            with self.assertRaises(limits.LimitError) as cm:
                limits.check_memory(1, STEAM)
            self.assertIn("4096", cm.exception.message(lang))
            self.assertNotIn("error.", cm.exception.message(lang))


class MemoryReadTests(unittest.TestCase):
    def test_env_names(self):
        self.assertEqual((limits.MEMINFO_ENV, limits.PROC_STATUS_ENV), ("GALIVELOP_MEMINFO", "GALIVELOP_PROC_STATUS"))

    def test_meminfo_and_proc_status_paths_come_from_the_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            info, status = Path(tmp) / "m", Path(tmp) / "s{pid}"
            info.write_text("MemAvailable: 3145728 kB\n")
            Path(tmp, "s42").write_text("VmHWM:\t 1048576 kB\n")
            with mock.patch.dict(os.environ, {limits.MEMINFO_ENV: str(info), limits.PROC_STATUS_ENV: str(status)}):
                self.assertEqual(limits.available_memory_mb(), 3072)
                self.assertEqual(limits.peak_rss_mb(42), 1024)
                self.assertIsNone(limits.peak_rss_mb(43))

    def test_available_and_total_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = Path(tmp) / "meminfo"
            info.write_text("MemTotal: 16777216 kB\nMemAvailable: 2097152 kB\n")
            self.assertEqual(limits.available_memory_mb(str(info)), 2048)
            self.assertEqual(limits.total_memory_mb(str(info)), 16384)
            self.assertIsNone(limits.available_memory_mb(str(Path(tmp) / "nope")))
            info.write_text("MemAvailable: x kB\n")
            self.assertIsNone(limits.available_memory_mb(str(info)))
            info.write_text("Other: 1 kB\n")
            self.assertIsNone(limits.available_memory_mb(str(info)))


if __name__ == "__main__":
    unittest.main()
