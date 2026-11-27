import json
import multiprocessing
import os
import stat
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
            with fsutil.try_lock(p) as second:  # another open file description: it conflicts even in this process
                self.assertFalse(second)
        with fsutil.try_lock(p) as again:
            self.assertTrue(again)
        self.assertEqual(sorted(x.name for x in p.parent.iterdir()), ["x.lock"])  # the same file `lock` uses

    def test_try_lock_does_not_swallow_the_error_of_its_body_and_releases(self):
        p = self.dir / "y"
        with self.assertRaises(ValueError):
            with fsutil.try_lock(p):
                raise ValueError("boom")
        with fsutil.try_lock(p) as taken:
            self.assertTrue(taken)

    def test_write_format(self):
        p = self.dir / "sub" / "a.json"
        fsutil.write_json(p, {"b": 1, "a": [1]})
        self.assertEqual(p.read_text(), '{\n  "a": [\n    1\n  ],\n  "b": 1\n}\n')
        self.assertEqual(sorted(x.name for x in p.parent.iterdir()), ["a.json"])

    def test_failed_write_keeps_old_and_no_temp(self):
        p = self.dir / "a.json"
        fsutil.write_json(p, {"v": 1})
        with self.assertRaises(TypeError):
            fsutil.write_json(p, {"v": object()})
        self.assertEqual(json.loads(p.read_text()), {"v": 1})
        with mock.patch("os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                fsutil.write_json(p, {"v": 2})
        self.assertEqual(json.loads(p.read_text()), {"v": 1})
        self.assertEqual(sorted(x.name for x in self.dir.iterdir()), ["a.json"])

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


def _open_fds():
    return len(os.listdir("/proc/self/fd"))


@unittest.skipUnless(os.path.isdir("/proc/self/fd"), "needs /proc/self/fd")
class HeldTests(unittest.TestCase):
    def test_only_blocking_error_is_held(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.lock"
            path.write_text("")
            with mock.patch("grun.fsutil.fcntl.flock", side_effect=OSError(37, "no locks")):
                self.assertIsNone(fsutil.held(path))
            with mock.patch("grun.fsutil.fcntl.flock", side_effect=BlockingIOError(11, "again")):
                self.assertIs(fsutil.held(path), True)
            self.assertIs(fsutil.held(path), False)


class WriteJsonFdTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_failed_fchmod_closes_the_temp_fd(self):
        before = _open_fds()
        with mock.patch.object(fsutil, "honour_umask", side_effect=OSError("fchmod boom")):
            with self.assertRaisesRegex(OSError, "fchmod boom"):
                fsutil.write_json(self.dir / "a.json", {})
        self.assertEqual(_open_fds(), before)
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_failed_fdopen_closes_the_temp_fd(self):
        before = _open_fds()
        with mock.patch("os.fdopen", side_effect=OSError("fdopen boom")):
            with self.assertRaisesRegex(OSError, "fdopen boom"):
                fsutil.write_json(self.dir / "a.json", {})
        self.assertEqual(_open_fds(), before)
        self.assertEqual(list(self.dir.iterdir()), [])


class WriteJsonDurabilityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_parent_folder_is_fsynced_after_replace(self):
        synced = []
        real = os.fsync

        def spy(fd):
            synced.append(stat.S_ISDIR(os.fstat(fd).st_mode))
            return real(fd)

        with mock.patch("os.fsync", side_effect=spy):
            fsutil.write_json(self.dir / "a.json", {"v": 1})
        self.assertEqual(synced, [False, True])

    def test_folder_that_cannot_be_opened_is_tolerated(self):
        real = os.open

        def no_dirs(path, flags, *a, **kw):
            if os.path.isdir(path):
                raise PermissionError("no folders here")
            return real(path, flags, *a, **kw)

        with mock.patch("os.open", side_effect=no_dirs):
            fsutil.write_json(self.dir / "a.json", {"v": 1})
        self.assertEqual(json.loads((self.dir / "a.json").read_text()), {"v": 1})


class UmaskTests(unittest.TestCase):
    def test_write_does_not_touch_the_process_umask(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "m.json"
        old = os.umask(0o027)
        try:
            with mock.patch("os.umask", side_effect=AssertionError("umask changed during write")):
                fsutil.write_json(p, {})
        finally:
            os.umask(old)
        if os.path.exists("/proc/self/status"):
            self.assertEqual(os.stat(p).st_mode & 0o777, 0o640)
