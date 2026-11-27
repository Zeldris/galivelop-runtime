import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from grun import limits
from grun.errors import GrunError

PROFILE = {"timeoutS": 600, "minFreeMemoryMb": 4096, "watchMemoryMb": 1536}


class CheckTests(unittest.TestCase):
    def test_timeout(self):
        self.assertEqual(limits.timeout_s(PROFILE), 600)

    def test_memory_start_limit(self):
        limits.check_memory(4096, PROFILE)
        with self.assertRaises(limits.LimitError) as cm:
            limits.check_memory(4095, PROFILE)
        self.assertIsInstance(cm.exception, GrunError)
        self.assertEqual((cm.exception.code, cm.exception.params), ("limit.memory", {"free": 4095, "min": 4096}))
        limits.check_memory(None, PROFILE)  # unknown passes
        limits.check_memory(1, {})  # no limit in the profile

    def test_abort_below_watch_memory(self):
        self.assertFalse(limits.must_abort(1536, PROFILE))
        self.assertTrue(limits.must_abort(1535, PROFILE))
        self.assertFalse(limits.must_abort(None, PROFILE))
        self.assertFalse(limits.must_abort(1, {}))

    def test_meminfo_and_proc_status_paths_come_from_the_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            info, status = Path(tmp) / "m", Path(tmp) / "s{pid}"
            info.write_text("MemAvailable: 3145728 kB\n")
            Path(tmp, "s42").write_text("VmHWM:\t 1048576 kB\n")
            with mock.patch.dict(os.environ, {limits.MEMINFO_ENV: str(info), limits.PROC_STATUS_ENV: str(status)}):
                self.assertEqual(limits.available_memory_mb(), 3072)
                self.assertEqual(limits.peak_rss_mb(42), 1024)
                self.assertIsNone(limits.peak_rss_mb(43))

    def test_available_memory(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "meminfo"
            p.write_text("MemTotal: 999 kB\nMemAvailable:    2097152 kB\n")
            self.assertEqual(limits.available_memory_mb(str(p)), 2048)
            p.write_text("MemTotal: 999 kB\n")
            self.assertIsNone(limits.available_memory_mb(str(p)))
            p.write_text("MemAvailable: lots kB\n")
            self.assertIsNone(limits.available_memory_mb(str(p)))
            self.assertIsNone(limits.available_memory_mb(str(Path(d) / "nope")))

    def test_total_memory(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "meminfo"
            p.write_text("MemTotal:  16384000 kB\nMemAvailable: 1024 kB\n")
            with mock.patch.dict(os.environ, {limits.MEMINFO_ENV: str(p)}):
                self.assertEqual(limits.total_memory_mb(), 16000)
            p.write_text("MemAvailable: 1024 kB\n")
            self.assertIsNone(limits.total_memory_mb(str(p)))

    def test_messages(self):
        for lang in ("es", "en"):
            text = limits.LimitError("limit.memory", free=1, min=2).message(lang)
            self.assertNotIn("error.", text)
            self.assertIn("2", text)


if __name__ == "__main__":
    unittest.main()
