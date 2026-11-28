"""R5: the published protocol `grun.lock/1` (docs/protocol/grun.lock.1.md): the record `hold()` writes validates
against `schemas/grun.lock.1.json`, and a client that is not Python (flock(1)) takes part in the same lock."""
import json
import shutil
import subprocess
import time
import unittest
from pathlib import Path

from grun import machine_lock, paths
from tests import jsonschema_lite as js
from tests.test_machine_lock import LockBase

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schemas" / "grun.lock.1.json").read_text(encoding="utf-8"))
BUSY = 75  # the conflict exit code the protocol asks flock(1) for (-E 75)


def problems(value):
    return js.errors(value, SCHEMA, SCHEMA)


class RecordSchemaTests(LockBase):
    def test_the_record_hold_writes_is_valid(self):
        with machine_lock.hold(app="galivelop-voice", entry="job-1"):
            raw = json.loads(paths.machine_lock_path().read_text(encoding="utf-8"))
        self.assertEqual(problems(raw), [])
        self.assertEqual(raw["schema"], "grun.lock/1")

    def test_a_record_without_app_or_entry_is_valid(self):
        with machine_lock.hold():
            raw = json.loads(paths.machine_lock_path().read_text(encoding="utf-8"))
        self.assertEqual(problems(raw), [])

    def test_the_checker_rejects_a_bad_record(self):
        good = {"schema": "grun.lock/1", "app": "a", "pid": 1, "entry": None, "since": "2026-01-01T00:00:00Z"}
        self.assertEqual(problems(good), [])
        self.assertNotEqual(problems(dict(good, schema="grun.lock/0")), [])
        self.assertNotEqual(problems(dict(good, pid=0)), [])
        self.assertNotEqual(problems(dict(good, since="yesterday")), [])
        del good["since"]
        self.assertIn("missing since", " ".join(problems(good)))


@unittest.skipUnless(shutil.which("flock"), "flock(1) is not installed")
class FlockClientTests(LockBase):
    def flock(self, *args):
        return subprocess.run(["flock", *args], capture_output=True, text=True, timeout=30)

    def test_nonblocking_flock_sees_a_python_holder_and_then_gets_in(self):
        path = str(paths.machine_lock_path())
        with machine_lock.hold(app="a"):
            self.assertEqual(self.flock("-n", "-E", str(BUSY), path, "true").returncode, BUSY)
            self.assertEqual(self.flock("-w", "0.3", "-E", str(BUSY), path, "true").returncode, BUSY)
        self.assertEqual(self.flock("-n", "-E", str(BUSY), path, "true").returncode, 0)

    def test_hold_waits_for_a_flock_holder_and_cancel_ends_the_wait(self):
        path = paths.machine_lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        proc = self.spawn("import subprocess,sys\n"
                          "p = subprocess.Popen(['flock', sys.argv[1], 'sh', '-c', 'echo held; sleep 60'])\n"
                          "p.wait()\n", str(path))
        self.assertEqual(proc.stdout.readline().strip(), "held")
        self.assertIs(machine_lock.busy(), True)
        self.assertEqual(machine_lock.holder(), {})  # flock(1) writes no record
        deadline = time.monotonic() + 0.2
        with self.assertRaises(machine_lock.WaitCancelled):
            with machine_lock.hold(should_cancel=lambda: time.monotonic() > deadline, poll_s=0.01):
                self.fail("took the lock while flock(1) held it")

    def test_flock_does_not_create_the_state_folder(self):
        r = self.flock("-n", "-E", str(BUSY), str(paths.machine_lock_path()), "true")
        self.assertNotIn(r.returncode, (0, BUSY))  # cannot open: the client must `mkdir -p` first
        self.assertIn("No such file", r.stderr)

    def test_flock_holder_releases_when_its_command_ends(self):
        path = str(paths.machine_lock_path())
        paths.machine_lock_path().parent.mkdir(parents=True)
        self.assertEqual(self.flock(path, "true").returncode, 0)
        self.assertIs(machine_lock.busy(), False)
        with machine_lock.hold(app="a"):
            pass


if __name__ == "__main__":
    unittest.main()
