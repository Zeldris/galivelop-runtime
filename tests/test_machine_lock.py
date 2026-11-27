import ast
import fcntl
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from grun import machine_lock, paths
from grun.errors import GrunError

ROOT = Path(__file__).resolve().parent.parent
HOLDER = (  # takes the lock without writing a holder record (like flock(1))
    "import fcntl, os, sys, time\n"
    "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
    "fcntl.flock(fd, fcntl.LOCK_EX)\n"
    "print('held', flush=True)\n"
    "time.sleep(60)\n")
HOLD_AND_SLEEP = (  # takes it through grun
    "from grun import machine_lock\n"
    "with machine_lock.hold(app='a', entry='e'):\n"
    "    print('held', flush=True)\n"
    "    import time; time.sleep(60)\n")
HOLD_STAMPS = (  # invariant 1: records when it held the lock
    "import sys, time\n"
    "from grun import machine_lock\n"
    "with machine_lock.hold(poll_s=0.01):\n"
    "    t0 = time.monotonic(); time.sleep(0.15); t1 = time.monotonic()\n"
    "print(t0, t1)\n")
HOLD_SPAWN_CHILD = (  # invariant 3: the child inherits the lock, the parent dies
    "import subprocess, sys\n"
    "from grun import machine_lock\n"
    "with machine_lock.hold():\n"
    "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],\n"
    "                             pass_fds=machine_lock.held_fds(), start_new_session=True)\n"
    "    print(child.pid, flush=True)\n"
    "    import time; time.sleep(60)\n")


class LockBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        env = mock.patch.dict(os.environ, {"GALIVELOP_STATE_HOME": str(self.tmp / "state"), "GVOICE_STATE_HOME": ""})
        env.start()
        self.addCleanup(env.stop)

    def spawn(self, code, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        proc = subprocess.Popen([sys.executable, "-c", code, *args], stdout=subprocess.PIPE, text=True,
                                cwd=str(ROOT), env=env)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        return proc

    def holder(self):
        """Another process holding the machine lock (without a record); killed on cleanup."""
        path = paths.machine_lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        proc = self.spawn(HOLDER, str(path))
        self.assertEqual(proc.stdout.readline().strip(), "held")
        return proc


class PathTests(LockBase):
    def test_variable_wins(self):
        self.assertEqual(paths.machine_lock_path(), self.tmp / "state" / "gpu.lock")

    def test_environment_table(self):
        # Invariant 6: the path depends only on the environment, by the gvoice rule (written by hand).
        sandbox = "/h/.var/app/com.x/.local/state"
        table = [
            ({}, "/h/.local/state/galivelop/gpu.lock"),
            ({"XDG_STATE_HOME": "/xdg"}, "/xdg/galivelop/gpu.lock"),
            ({"XDG_STATE_HOME": "relative/dir"}, "/h/.local/state/galivelop/gpu.lock"),
            ({"XDG_STATE_HOME": sandbox}, sandbox + "/galivelop/gpu.lock"),  # outside Flatpak it is kept
            ({"FLATPAK_ID": "com.x", "XDG_STATE_HOME": sandbox}, "/h/.local/state/galivelop/gpu.lock"),
            ({"FLATPAK_ID": "com.x", "XDG_STATE_HOME": "/xdg"}, "/xdg/galivelop/gpu.lock"),
            ({"FLATPAK_ID": "com.x"}, "/h/.local/state/galivelop/gpu.lock"),
            ({"GALIVELOP_STATE_HOME": "/g", "XDG_STATE_HOME": "/xdg"}, "/g/gpu.lock"),
            ({"GVOICE_STATE_HOME": "/v", "XDG_STATE_HOME": "/xdg"}, "/xdg/galivelop/gpu.lock"),
            ({"GALIVELOP_STATE_HOME": "/g", "GVOICE_STATE_HOME": "/v"}, "/g/gpu.lock"),
            ({"GALIVELOP_STATE_HOME": "rel", "GVOICE_STATE_HOME": "/v"}, "/h/.local/state/galivelop/gpu.lock"),
            ({"FLATPAK_ID": "com.x", "GVOICE_STATE_HOME": "/v", "XDG_STATE_HOME": sandbox}, "/h/.local/state/galivelop/gpu.lock"),
        ]
        for extra, expected in table:
            base = {"GALIVELOP_STATE_HOME": "", "GVOICE_STATE_HOME": "", "XDG_STATE_HOME": "", "FLATPAK_ID": "",
                    "HOME": "/h"}
            base.update(extra)
            with self.subTest(env=extra), mock.patch.dict(os.environ, base):
                self.assertEqual(str(paths.machine_lock_path()), expected)


class HoldTests(LockBase):
    def test_creates_the_missing_state_folder(self):
        # Invariant 5: hold() creates the file when missing, and never deletes it.
        self.assertFalse((self.tmp / "state").exists())
        with machine_lock.hold():
            self.assertTrue(paths.machine_lock_path().is_file())
            self.assertTrue(machine_lock.busy())
        self.assertFalse(machine_lock.busy())
        self.assertTrue(paths.machine_lock_path().is_file())

    def test_busy_is_a_pure_read(self):
        self.assertFalse(machine_lock.busy())
        self.assertIsNone(machine_lock.holder())
        self.assertFalse((self.tmp / "state").exists())

    def test_released_on_error(self):
        with self.assertRaises(RuntimeError):
            with machine_lock.hold():
                raise RuntimeError("boom")
        self.assertFalse(machine_lock.busy())
        self.assertEqual(machine_lock.held_fds(), ())

    def test_unwritable_state_folder(self):
        blocker = self.tmp / "file"
        blocker.write_text("x")
        with mock.patch.dict(os.environ, {"GALIVELOP_STATE_HOME": str(blocker / "sub")}):
            with self.assertRaises(GrunError) as cm:
                with machine_lock.hold():
                    self.fail("must not get the lock")
        self.assertEqual(cm.exception.code, "machine_lock.unavailable")
        self.assertEqual(cm.exception.params["path"], str(blocker / "sub" / "gpu.lock"))
        self.assertTrue(cm.exception.params["reason"])

    def test_busy_lock_waits_then_proceeds(self):
        proc = self.holder()
        self.assertTrue(machine_lock.busy())
        waited = []
        got = threading.Event()

        def take():
            with machine_lock.hold(on_wait=lambda: waited.append(1), poll_s=0.01):
                got.set()

        thread = threading.Thread(target=take)
        thread.start()
        time.sleep(0.2)
        self.assertFalse(got.is_set())  # still waiting: it did not fail
        self.assertEqual(waited, [1])  # told once
        proc.kill()
        proc.wait()
        thread.join(5)
        self.assertTrue(got.is_set())

    def test_wait_is_cancellable(self):
        # Invariant 4 (lock part): cancelled while waiting, nothing taken, on_wait called.
        self.holder()
        cancel = threading.Event()
        waited = []
        threading.Timer(0.15, cancel.set).start()
        start = time.monotonic()
        with self.assertRaises(machine_lock.WaitCancelled):
            with machine_lock.hold(cancel.is_set, lambda: waited.append(1), poll_s=0.01):
                self.fail("must not get the lock")
        self.assertLess(time.monotonic() - start, 3)
        self.assertEqual(waited, [1])
        self.assertEqual(machine_lock.held_fds(), ())

    def test_process_dying_with_the_lock_frees_it(self):
        # Invariant 2: SIGKILL of the holder releases the lock.
        proc = self.spawn(HOLD_AND_SLEEP)
        self.assertEqual(proc.stdout.readline().strip(), "held")
        self.assertTrue(machine_lock.busy())
        proc.send_signal(signal.SIGKILL)
        proc.wait()
        self.assertFalse(machine_lock.busy())
        with machine_lock.hold():
            pass

    def test_two_processes_never_overlap(self):
        # Invariant 1: two subprocesses holding the same path have disjoint intervals.
        procs = [self.spawn(HOLD_STAMPS) for _ in range(2)]
        spans = []
        for proc in procs:
            out = proc.stdout.read().split()
            self.assertEqual(len(out), 2)
            spans.append(tuple(float(x) for x in out))
        first, second = sorted(spans)
        self.assertLessEqual(first[1], second[0])

    def test_orphaned_child_keeps_the_lock(self):
        # Invariant 3: the child inherits the descriptor; the lock outlives the killed parent, until the child ends.
        proc = self.spawn(HOLD_SPAWN_CHILD)
        child_pid = int(proc.stdout.readline())
        self.addCleanup(self._kill_quietly, child_pid)
        proc.send_signal(signal.SIGKILL)
        proc.wait()
        self.assertTrue(machine_lock.busy())
        os.kill(child_pid, signal.SIGKILL)
        deadline = time.monotonic() + 5
        while machine_lock.busy() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(machine_lock.busy())

    @staticmethod
    def _kill_quietly(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    def test_lock_is_exclusive_between_two_holds_in_one_process(self):
        with machine_lock.hold():
            fd = os.open(str(paths.machine_lock_path()), os.O_RDWR)
            self.addCleanup(os.close, fd)
            with self.assertRaises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_held_fds(self):
        self.assertEqual(machine_lock.held_fds(), ())
        with machine_lock.hold():
            fds = machine_lock.held_fds()
            self.assertIsInstance(fds, tuple)
            self.assertEqual(len(fds), 1)
        self.assertEqual(machine_lock.held_fds(), ())


class HolderTests(LockBase):
    def test_record_while_held(self):
        with machine_lock.hold(app="galivelop-voice", entry="job-1"):
            rec = machine_lock.holder()
            self.assertEqual(rec["schema"], "grun.lock/0")
            self.assertEqual(rec["app"], "galivelop-voice")
            self.assertEqual(rec["entry"], "job-1")
            self.assertEqual(rec["pid"], os.getpid())
            self.assertRegex(rec["since"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
            self.assertEqual(set(rec), {"schema", "app", "pid", "entry", "since"})

    def test_record_keeps_the_inode(self):
        paths.machine_lock_path().parent.mkdir(parents=True)
        paths.machine_lock_path().write_text("")
        before = paths.machine_lock_path().stat().st_ino
        with machine_lock.hold(app="a"):
            self.assertEqual(paths.machine_lock_path().stat().st_ino, before)
            self.assertIsNone(machine_lock.holder()["entry"])
        self.assertEqual(paths.machine_lock_path().stat().st_ino, before)

    def test_free_is_none(self):
        self.assertIsNone(machine_lock.holder())
        with machine_lock.hold():
            pass
        self.assertIsNone(machine_lock.holder())

    def test_taken_but_empty_is_an_empty_dict(self):
        self.holder()  # takes it and writes nothing
        self.assertEqual(machine_lock.holder(), {})

    def test_taken_with_garbage_is_an_empty_dict(self):
        path = paths.machine_lock_path()
        path.parent.mkdir(parents=True)
        path.write_text("not json")
        fd = os.open(str(path), os.O_RDWR)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        self.assertEqual(machine_lock.holder(), {})
        os.ftruncate(fd, 0)
        os.write(fd, b"[1]")
        self.assertEqual(machine_lock.holder(), {})

    def test_other_process_record(self):
        proc = self.spawn(HOLD_AND_SLEEP)
        self.assertEqual(proc.stdout.readline().strip(), "held")
        rec = machine_lock.holder()
        self.assertEqual((rec["app"], rec["entry"], rec["pid"]), ("a", "e", proc.pid))

    def test_released_leaves_an_empty_existing_file(self):
        with machine_lock.hold(app="a"):
            self.assertGreater(paths.machine_lock_path().stat().st_size, 0)
        self.assertTrue(paths.machine_lock_path().is_file())
        self.assertEqual(paths.machine_lock_path().stat().st_size, 0)


def lock_deletions(source: str, filename: str = "<src>") -> list:
    """Calls to unlink/remove/rmtree/replace/rename on something whose name or expression mentions ``lock``."""
    found = []
    for node in ast.walk(ast.parse(source, filename)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name not in ("unlink", "remove", "rmtree", "replace", "rename"):
            continue
        parts = [ast.unparse(node.func)] + [ast.unparse(a) for a in node.args]
        if any("lock" in p.lower() for p in parts):
            found.append((filename, node.lineno, ast.unparse(node)))
    return found


class NeverDeletedTests(unittest.TestCase):
    def test_the_scan_detects_a_deletion(self):
        # The guard must be able to fail: it finds these.
        self.assertTrue(lock_deletions("import os\nos.unlink(lock_path)\n"))
        self.assertTrue(lock_deletions("lock_path.unlink()\n"))
        self.assertTrue(lock_deletions("import os\nos.replace(tmp, paths.machine_lock_path())\n"))
        self.assertTrue(lock_deletions("shutil.rmtree(self.lock_dir)\n"))
        self.assertFalse(lock_deletions("import os\nos.unlink(tmp_path)\n"))

    def test_no_module_deletes_a_lock(self):
        # Invariant 5: no module of grun deletes or replaces a lock file.
        found = []
        for py in sorted((ROOT / "grun").glob("*.py")):
            found += lock_deletions(py.read_text(encoding="utf-8"), py.name)
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
