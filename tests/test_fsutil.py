"""Invariante 10 (parte de escritura): un fallo entre la escritura y el `replace` deja el archivo anterior legible.

Copiado de gvoice@8a17618 (tests/test_fsutil.py); adaptado: el fallo inyectado comprueba el motivo y los
temporales."""
import json
import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from grun import fsutil


def _bump(path, n):
    for _ in range(n):
        with fsutil.lock(path):
            data = fsutil.read_json(path, default={"n": 0})
            data["n"] += 1
            fsutil.write_json(path, data)


class FsutilTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_write_mode_honours_umask(self):
        p = self.dir / "m.json"
        old = os.umask(0o022)
        try:
            fsutil.write_json(p, {})
        finally:
            os.umask(old)
        self.assertEqual(os.stat(p).st_mode & 0o777, 0o644)

    def test_try_lock_says_false_while_another_holds_it_and_true_when_it_is_free(self):
        p = self.dir / "sub" / "x"
        with fsutil.try_lock(p) as first:
            self.assertTrue(first)
            with fsutil.try_lock(p) as second:
                self.assertFalse(second)
        with fsutil.try_lock(p) as again:
            self.assertTrue(again)
        self.assertEqual(sorted(x.name for x in p.parent.iterdir()), ["x.lock"])

    def test_try_lock_does_not_swallow_the_error_of_its_body_and_releases(self):
        p = self.dir / "y"
        with self.assertRaises(ValueError) as cm:
            with fsutil.try_lock(p):
                raise ValueError("boom")
        self.assertEqual(str(cm.exception), "boom")
        with fsutil.try_lock(p) as taken:
            self.assertTrue(taken)

    def test_write_format(self):
        p = self.dir / "sub" / "a.json"
        fsutil.write_json(p, {"b": 1, "a": [1]})
        self.assertEqual(p.read_text(), '{\n  "a": [\n    1\n  ],\n  "b": 1\n}\n')
        self.assertEqual(sorted(x.name for x in p.parent.iterdir()), ["a.json"])

    def test_failure_between_write_and_replace_keeps_the_old_file_and_no_temp(self):
        p = self.dir / "a.json"
        fsutil.write_json(p, {"v": 1})
        with mock.patch("os.replace", side_effect=OSError("corte")):
            with self.assertRaises(OSError) as cm:
                fsutil.write_json(p, {"v": 2})
        self.assertEqual(str(cm.exception), "corte")
        self.assertEqual(json.loads(p.read_text()), {"v": 1})
        self.assertEqual(sorted(x.name for x in self.dir.iterdir()), ["a.json"])

    def test_failure_after_fsync_keeps_the_old_file_and_no_temp(self):
        p = self.dir / "a.json"
        fsutil.write_json(p, {"v": 1})
        with mock.patch("os.fsync", side_effect=OSError("disco")):
            with self.assertRaises(OSError) as cm:
                fsutil.write_json(p, {"v": 2})
        self.assertEqual(str(cm.exception), "disco")
        self.assertEqual(json.loads(p.read_text()), {"v": 1})
        self.assertEqual(sorted(x.name for x in self.dir.iterdir()), ["a.json"])

    def test_unserialisable_data_keeps_the_old_file(self):
        p = self.dir / "a.json"
        fsutil.write_json(p, {"v": 1})
        with self.assertRaises(TypeError) as cm:
            fsutil.write_json(p, {"v": object()})
        self.assertIn("not JSON serializable", str(cm.exception))
        self.assertEqual(json.loads(p.read_text()), {"v": 1})
        self.assertEqual(sorted(x.name for x in self.dir.iterdir()), ["a.json"])

    def test_a_new_file_that_fails_leaves_nothing(self):
        p = self.dir / "new.json"
        with mock.patch("os.replace", side_effect=OSError("corte")):
            with self.assertRaises(OSError):
                fsutil.write_json(p, {"v": 1})
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_read_default_and_missing(self):
        p = self.dir / "none.json"
        self.assertEqual(fsutil.read_json(p, default=5), 5)
        with self.assertRaises(FileNotFoundError):
            fsutil.read_json(p)

    def test_lock_serialises_processes(self):
        p = self.dir / "c.json"
        procs = [multiprocessing.Process(target=_bump, args=(p, 25)) for _ in range(4)]
        for pr in procs:
            pr.start()
        for pr in procs:
            pr.join()
            self.assertEqual(pr.exitcode, 0)
        self.assertEqual(fsutil.read_json(p)["n"], 100)


if __name__ == "__main__":
    unittest.main()
