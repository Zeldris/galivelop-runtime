import fcntl
import io
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from grun import paths, queue
from grun.errors import GrunError
from grun.launcher import Launcher

COMMAND = ["python", "-m", "app", "work"]


class FakeProc:
    def __init__(self, code=None):
        self.code = code

    def poll(self):
        return self.code


class LauncherBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.q = queue.Queue(self.root / "data")
        self.log_path = self.root / "worker.log"
        self.now = 1000.0
        self.procs = []
        self.popen = mock.Mock(side_effect=self._spawn)
        self.launcher = Launcher(self.q, COMMAND, log_path=self.log_path, popen=self.popen, clock=lambda: self.now)
        self.q.enqueue([{"project": "p"}])

    def _spawn(self, *args, **kwargs):
        proc = FakeProc()
        self.procs.append(proc)
        return proc


class LaunchTests(LauncherBase):
    def test_launches_the_injected_command_detached(self):
        self.assertTrue(self.launcher.maybe_launch())
        self.popen.assert_called_once()
        args, kwargs = self.popen.call_args
        self.assertEqual(args[0], COMMAND)
        self.assertTrue(kwargs["start_new_session"])
        self.assertIsNotNone(kwargs["stdin"])
        self.assertTrue(self.log_path.exists())

    def test_two_calls_launch_one_worker(self):
        self.assertTrue(self.launcher.maybe_launch())
        self.assertFalse(self.launcher.maybe_launch())
        self.assertEqual(self.popen.call_count, 1)

    def test_threads_racing_launch_one_worker(self):
        threads = [threading.Thread(target=self.launcher.maybe_launch) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(self.popen.call_count, 1)

    def test_nothing_runnable_launches_nothing(self):
        self.q.clear()
        self.assertFalse(self.launcher.maybe_launch())
        self.popen.assert_not_called()

    def test_held_entries_are_not_runnable(self):
        q = queue.Queue(self.root / "data", held=lambda e: "waiting")
        launcher = Launcher(q, COMMAND, log_path=self.log_path, popen=self.popen)
        self.assertFalse(launcher.maybe_launch())
        self.popen.assert_not_called()

    def test_paused_queue_launches_nothing_then_resumes(self):
        self.q.pause()
        self.assertFalse(self.launcher.maybe_launch())
        self.q.resume()
        self.assertTrue(self.launcher.maybe_launch())

    def test_a_live_worker_blocks_the_launch(self):
        path = paths.worker_lock_path(self.q.data)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        self.assertFalse(self.launcher.maybe_launch())
        self.popen.assert_not_called()

    def test_unknown_lock_state_launches_nothing(self):
        with mock.patch.object(self.q, "worker_alive", return_value=None):
            self.assertFalse(self.launcher.maybe_launch())
        self.popen.assert_not_called()

    def test_relaunches_after_a_clean_exit(self):
        self.assertTrue(self.launcher.maybe_launch())
        self.procs[0].code = 0
        self.assertTrue(self.launcher.maybe_launch())
        self.assertEqual(self.popen.call_count, 2)


class FailureTests(LauncherBase):
    def test_a_failing_worker_is_not_relaunched_in_a_loop(self):
        self.assertTrue(self.launcher.maybe_launch())
        self.procs[0].code = 1
        self.assertFalse(self.launcher.maybe_launch())
        self.now += self.launcher.retry_after_s - 1
        self.assertFalse(self.launcher.maybe_launch())
        self.assertEqual(self.popen.call_count, 1)
        self.now += 2
        self.assertTrue(self.launcher.maybe_launch())
        self.assertEqual(self.popen.call_count, 2)

    def test_a_launch_error_is_reported_once_and_never_raised(self):
        self.popen.side_effect = OSError("no such program")
        err = io.StringIO()
        with redirect_stderr(err):
            for _ in range(3):
                self.assertFalse(self.launcher.maybe_launch())
        lines = [x for x in err.getvalue().splitlines() if x]
        self.assertEqual(len(lines), 1)
        self.assertIn("no such program", lines[0])

    def test_a_queue_error_is_reported_once_and_never_raised(self):
        with mock.patch.object(self.q, "list_runnable", side_effect=GrunError("queue.corrupt", path="x")):
            err = io.StringIO()
            with redirect_stderr(err):
                for _ in range(3):
                    self.assertFalse(self.launcher.maybe_launch())
        self.assertEqual(len([x for x in err.getvalue().splitlines() if x]), 1)

    def test_a_different_error_is_reported_again(self):
        err = io.StringIO()
        with redirect_stderr(err):
            self.popen.side_effect = OSError("first")
            self.launcher.maybe_launch()
            self.popen.side_effect = OSError("second")
            self.launcher.maybe_launch()
        text = err.getvalue()
        self.assertIn("first", text)
        self.assertIn("second", text)


if __name__ == "__main__":
    unittest.main()
