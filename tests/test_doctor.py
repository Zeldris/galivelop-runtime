import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from grun import doctor, machine_lock, paths

ROOT = Path(__file__).resolve().parent.parent
HOLD_EX = (  # another process holding a lock file exclusively
    "import fcntl, os, sys, time\n"
    "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
    "fcntl.flock(fd, fcntl.LOCK_EX)\n"
    "print('held', flush=True)\n"
    "time.sleep(60)\n")
HOLD_MACHINE = (  # takes the machine lock through grun
    "from grun import machine_lock\n"
    "with machine_lock.hold(app='gimg', entry='7'):\n"
    "    print('held', flush=True)\n"
    "    import time; time.sleep(60)\n")


def tree(root: Path) -> list:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")) if root.exists() else []


class DoctorBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.state = self.tmp / "state"
        self.data = self.tmp / "data"
        env = mock.patch.dict(os.environ, {"GALIVELOP_STATE_HOME": str(self.state), "GVOICE_STATE_HOME": ""})
        env.start()
        self.addCleanup(env.stop)

    def spawn(self, code, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        proc = subprocess.Popen([sys.executable, "-c", code, *args], stdout=subprocess.PIPE, text=True,
                                cwd=str(ROOT), env=env)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        self.assertEqual(proc.stdout.readline().strip(), "held")
        return proc

    def hold(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        return self.spawn(HOLD_EX, str(path))

    def write_queue(self, entries, next_id=10):
        self.data.mkdir(parents=True, exist_ok=True)
        text = json.dumps({"nextId": next_id, "entries": entries})
        paths.queue_path(self.data).write_text(text, encoding="utf-8")
        return text.encode("utf-8")

    @staticmethod
    def entry(i, state, **extra):
        return dict({"id": i, "position": i, "state": state}, **extra)

    def codes(self, report):
        return [p["code"] for p in report["problems"]]


class DiagnoseTests(DoctorBase):
    def test_unsearchable_folder_does_not_raise(self):
        real = Path.exists

        def denied(path):
            if str(path).startswith(str(self.data)):
                raise PermissionError(13, "denied")
            return real(path)

        with mock.patch.object(Path, "exists", denied):
            report = doctor.diagnose(self.data)
        self.assertIs(report["queue"]["paused"], False)
        self.assertTrue(all(lock["exists"] is False for lock in report["locks"]))
    def test_nothing_created_nothing_written(self):
        self.tmp.joinpath("data").mkdir()
        before = tree(self.tmp)
        report = doctor.diagnose(self.data)
        self.assertEqual(tree(self.tmp), before)
        self.assertFalse(self.state.exists())
        self.assertEqual(report["problems"], [])
        self.assertFalse(report["machine"]["busy"])
        self.assertIsNone(report["machine"]["holder"])
        self.assertFalse(report["queue"]["exists"])
        self.assertTrue(report["queue"]["readable"])
        self.assertEqual(report["orphans"], [])
        self.assertEqual([l["name"] for l in report["locks"]], ["worker.lock", "queue.json.lock", "serve.lock"])
        self.assertTrue(all(l["held"] is False and l["exists"] is False for l in report["locks"]))

    def test_missing_data_folder_creates_nothing(self):
        report = doctor.diagnose(self.data)
        self.assertFalse(self.data.exists())
        self.assertEqual(report["problems"], [])

    def test_machine_lock_held_elsewhere(self):
        self.spawn(HOLD_MACHINE)
        report = doctor.diagnose(self.data)
        self.assertTrue(report["machine"]["busy"])
        self.assertEqual(report["machine"]["holder"]["app"], "gimg")
        self.assertEqual(report["machine"]["holder"]["entry"], "7")
        self.assertEqual(report["machine"]["path"], str(paths.machine_lock_path()))
        self.assertEqual(report["problems"], [])

    def test_machine_holder_without_record(self):
        self.hold(paths.machine_lock_path())
        report = doctor.diagnose(self.data)
        self.assertTrue(report["machine"]["busy"])
        self.assertEqual(report["machine"]["holder"], {})
        self.assertIn("doctor.machine_holder_unknown", self.codes(report))

    def test_queue_counts_order_and_pause(self):
        self.write_queue([
            self.entry(1, "done"), self.entry(2, "failed"), self.entry(3, "cancelled"),
            self.entry(4, "queued", position=9), self.entry(5, "queued", position=2), self.entry(6, "running")])
        self.hold(paths.worker_lock_path(self.data))
        paths.pause_path(self.data).write_text("x\n")
        report = doctor.diagnose(self.data)
        q = report["queue"]
        self.assertTrue(q["exists"] and q["readable"] and q["paused"])
        self.assertEqual(q["counts"], {"queued": 2, "running": 1, "done": 1, "failed": 1, "cancelled": 1})
        self.assertEqual(q["queued"], [5, 4])
        self.assertEqual(q["running"], [6])
        self.assertIsNone(q["error"])
        self.assertEqual(report["orphans"], [])

    def test_not_paused(self):
        self.write_queue([])
        self.assertFalse(doctor.diagnose(self.data)["queue"]["paused"])

    def test_orphan_reported_and_queue_untouched(self):
        raw = self.write_queue([self.entry(1, "running"), self.entry(2, "queued")])
        before = tree(self.tmp)
        report = doctor.diagnose(self.data)
        self.assertEqual(report["orphans"], [1])
        problem = [p for p in report["problems"] if p["code"] == "doctor.orphans"]
        self.assertEqual(len(problem), 1)
        self.assertEqual(paths.queue_path(self.data).read_bytes(), raw)
        self.assertEqual(tree(self.tmp), before)  # not even a lock file

    def test_live_worker_means_no_orphans(self):
        self.write_queue([self.entry(1, "running")])
        self.hold(paths.worker_lock_path(self.data))
        report = doctor.diagnose(self.data)
        self.assertEqual(report["orphans"], [])
        self.assertNotIn("doctor.orphans", self.codes(report))
        worker = [l for l in report["locks"] if l["name"] == "worker.lock"][0]
        self.assertTrue(worker["held"] and worker["exists"])

    def test_unknown_worker_state_declares_no_orphans(self):
        self.write_queue([self.entry(1, "running")])
        with mock.patch("grun.fsutil.held", return_value=None):
            report = doctor.diagnose(self.data)
        self.assertEqual(report["orphans"], [])
        self.assertIn("doctor.lock_unknown", self.codes(report))

    def test_app_lock_held(self):
        self.hold(self.data / "serve.lock")
        report = doctor.diagnose(self.data, app="gimg")
        serve = [l for l in report["locks"] if l["name"] == "serve.lock"][0]
        self.assertTrue(serve["held"])

    def test_corrupt_queue_does_not_raise(self):
        self.data.mkdir()
        paths.queue_path(self.data).write_text("{not json", encoding="utf-8")
        report = doctor.diagnose(self.data)
        self.assertFalse(report["queue"]["readable"])
        self.assertEqual(report["queue"]["error"], "queue.corrupt")
        self.assertIn("doctor.queue_unreadable", self.codes(report))
        self.assertEqual(report["orphans"], [])

    def test_wrong_shape_queue_is_corrupt(self):
        self.data.mkdir()
        paths.queue_path(self.data).write_text(json.dumps({"nextId": 1, "entries": [{"id": 1, "state": "bogus"}]}))
        report = doctor.diagnose(self.data)
        self.assertEqual(report["queue"]["error"], "queue.corrupt")

    def test_no_descriptor_left_and_no_lock_taken(self):
        self.write_queue([self.entry(1, "queued")])
        self.hold(paths.worker_lock_path(self.data))
        before = len(os.listdir("/proc/self/fd"))
        doctor.diagnose(self.data)
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)
        self.assertFalse(machine_lock.busy())

    def test_report_is_json(self):
        self.write_queue([self.entry(1, "running")])
        report = doctor.diagnose(self.data)
        self.assertEqual(json.loads(json.dumps(report)), report)


class MainTests(DoctorBase):
    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = doctor.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_exit_0_without_problems(self):
        code, out, _ = self.run_main("doctor", "--data", str(self.data), "--lang", "en")
        self.assertEqual(code, 0)
        self.assertIn("No problems", out)

    def test_exit_1_with_orphans_and_texts_in_both_languages(self):
        self.write_queue([self.entry(1, "running")])
        code, out_en, _ = self.run_main("doctor", "--data", str(self.data), "--lang", "en")
        self.assertEqual(code, 1)
        self.assertIn("orphan", out_en.lower())
        code, out_es, _ = self.run_main("doctor", "--data", str(self.data), "--lang", "es")
        self.assertEqual(code, 1)
        self.assertIn("huérfana", out_es.lower())
        self.assertNotIn("doctor.", out_es)

    def test_grun_error_becomes_a_problem_not_a_traceback(self):
        from grun.errors import GrunError
        boom = GrunError("queue.corrupt", path="/x/queue.json")
        with mock.patch.object(doctor, "diagnose", side_effect=boom):
            code, out, _ = self.run_main("doctor", "--data", str(self.data), "--lang", "en")
            self.assertEqual(code, 1)
            self.assertIn("the queue /x/queue.json is corrupt", out)
            code, out, _ = self.run_main("doctor", "--data", str(self.data), "--json")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["problems"][0]["code"], "doctor.error")

    def test_exit_2_on_bad_usage(self):
        for argv in ([], ["doctor"], ["other", "--data", "x"], ["doctor", "--data", "x", "--bogus"]):
            code, _, err = self.run_main(*argv)
            self.assertEqual(code, 2, argv)
            self.assertTrue(err.strip(), argv)

    def test_json_output(self):
        self.write_queue([self.entry(1, "running")])
        code, out, _ = self.run_main("doctor", "--data", str(self.data), "--json")
        self.assertEqual(code, 1)
        report = json.loads(out)
        self.assertEqual(report["orphans"], [1])
        self.assertEqual(out.strip(), json.dumps(report, indent=2, sort_keys=True))

    def test_corrupt_queue_is_a_problem_not_a_traceback(self):
        self.data.mkdir()
        paths.queue_path(self.data).write_text("[", encoding="utf-8")
        code, out, err = self.run_main("doctor", "--data", str(self.data), "--lang", "en")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        self.assertIn("queue.json", out)

    def test_a_too_deep_queue_is_a_problem_not_a_traceback(self):
        self.data.mkdir()
        paths.queue_path(self.data).write_text("[" * 100000, encoding="utf-8")
        code, out, err = self.run_main("doctor", "--data", str(self.data), "--json")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["queue"]["error"], "queue.corrupt")

    def test_python_dash_m(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        proc = subprocess.run([sys.executable, "-m", "grun", "doctor", "--data", str(self.data), "--json"],
                              capture_output=True, text=True, cwd=str(ROOT), env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["problems"], [])


if __name__ == "__main__":
    unittest.main()
