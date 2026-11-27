import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from grun import limits, log, machine_lock, ollama, paths, queue, worker
from grun.engine import Cancelled, EngineError, EngineTimeout
from grun.errors import GrunError
from tests.fake_ollama import FakeOllama

ROOT = Path(__file__).resolve().parent.parent
HOLD_EX = (  # another process holding a lock file exclusively (the machine lock, or worker.lock)
    "import fcntl, os, sys, time\n"
    "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
    "fcntl.flock(fd, fcntl.LOCK_EX)\n"
    "print('held', flush=True)\n"
    "time.sleep(60)\n")
HOLD_SH = (  # a probe: a shared lock for a while
    "import fcntl, os, sys, time\n"
    "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
    "fcntl.flock(fd, fcntl.LOCK_SH)\n"
    "print('held', flush=True)\n"
    "time.sleep(float(sys.argv[2]))\n")
SIGTERM_WORKER = (  # a worker whose engine sleeps; a finally block leaves a mark
    "import sys, time\n"
    "from grun import queue\n"
    "from grun.worker import Worker\n"
    "data, marker = sys.argv[1], sys.argv[2]\n"
    "class E:\n"
    "    def run(self, job, on_progress, should_cancel, pass_fds):\n"
    "        print('engine', flush=True)\n"
    "        try:\n"
    "            time.sleep(60)\n"
    "        finally:\n"
    "            open(marker, 'w').write('finally')\n"
    "Worker(queue.Queue(data), E(), app='t', load_profile=lambda: {'timeoutS': 5,\n"
    "       'engine': {'ollama': 'ignore'}}).run()\n")
PROFILE = {"timeoutS": 60, "engine": {"ollama": "ignore"}}
MEM_OK = 8 * 1024 * 1024  # kB
MEM_LOW = 100 * 1024


class FakeEngine:
    def __init__(self, fn=None):
        self.fn = fn
        self.calls = []

    def run(self, job, on_progress, should_cancel, pass_fds):
        self.calls.append((job, pass_fds))
        return self.fn(job, on_progress, should_cancel, pass_fds) if self.fn else "result"


class ThresholdEngine(FakeEngine):
    def __init__(self, minimum):
        super().__init__()
        self.minimum = minimum

    def min_free_memory_mb(self, job):
        return self.minimum


class FakeStore:
    def __init__(self, attempt=None):
        self.attempt = attempt
        self.added = []

    def attempt_for_entry(self, entry):
        return self.attempt

    def add_attempt(self, entry, result):
        self.added.append((entry["id"], result))
        return 100 + len(self.added)


class WorkerBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.data = self.tmp / "data"
        self.meminfo = self.tmp / "meminfo"
        self.set_memory(MEM_OK)
        env = mock.patch.dict(os.environ, {"GALIVELOP_STATE_HOME": str(self.tmp / "state"), "GVOICE_STATE_HOME": "",
                                           "GRUN_MEMINFO": str(self.meminfo), "GRUN_OLLAMA_URL": ""})
        env.start()
        self.addCleanup(env.stop)
        self.q = queue.Queue(self.data)
        self.log_path = self.tmp / "log.jsonl"

    def set_memory(self, kb):
        self.meminfo.write_text("MemTotal: 16777216 kB\nMemAvailable: %d kB\n" % kb, encoding="ascii")

    def add(self, n=1):
        return self.q.enqueue([{"kind": "line", "n": i} for i in range(n)])

    def make(self, engine=None, profile=None, **kw):
        profile = dict(PROFILE if profile is None else profile)
        kw.setdefault("log_path", self.log_path)
        kw.setdefault("lang", "en")
        kw.setdefault("memory_poll_s", 0.01)
        self.engine = engine if engine is not None else FakeEngine()
        return worker.Worker(self.q, self.engine, app="testapp", load_profile=lambda: dict(profile), **kw)

    def later(self, delay, fn, *args):
        timer = threading.Timer(delay, fn, args)
        timer.daemon = True
        timer.start()
        self.addCleanup(timer.cancel)

    def spawn(self, code, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        proc = subprocess.Popen([sys.executable, "-c", code, *args], stdout=subprocess.PIPE, text=True,
                                cwd=str(ROOT), env=env)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        return proc

    def hold(self, path, code=HOLD_EX, *args):
        path.parent.mkdir(parents=True, exist_ok=True)
        proc = self.spawn(code, str(path), *args)
        self.assertEqual(proc.stdout.readline().strip(), "held")
        return proc

    def entry(self, entry_id=1):
        """The entry as stored. Not `Queue.get`: a read with no worker alive recovers `running` entries."""
        data = json.loads(paths.queue_path(self.data).read_text(encoding="utf-8"))
        return [e for e in data["entries"] if e["id"] == entry_id][0]

    def code(self, entry_id=1):
        return (self.entry(entry_id)["error"] or {}).get("code")

    def events(self):
        return list(log.lines(self.log_path))

    def names(self):
        return [e["event"] for e in self.events() if "event" in e]

    def stderr(self):
        patch = mock.patch.object(sys, "stderr", io.StringIO())
        buf = patch.start()
        self.addCleanup(patch.stop)
        return buf


class CancelWhileWaitingTests(WorkerBase):  # invariant 4
    def assert_cancelled_clean(self):
        entry = self.entry()
        self.assertEqual((entry["state"], entry["error"]), ("cancelled", None))
        self.assertEqual(self.engine.calls, [])
        self.assertFalse(machine_lock.busy())

    def test_machine_lock_taken_by_another_process(self):
        holder = self.hold(paths.machine_lock_path())
        self.add()
        self.later(0.3, self.q.cancel, 1)
        w = self.make()
        self.assertTrue(w.run_once())
        self.assertIn("LockWaited", self.names())
        self.assertNotIn("LockAcquired", self.names())
        self.assertTrue(machine_lock.busy())  # the other process still holds it
        holder.kill()
        holder.wait()
        self.assert_cancelled_clean()
        with machine_lock.hold():  # free for this process
            pass

    def test_memory_below_the_threshold(self):
        self.set_memory(MEM_LOW)
        self.add()
        self.stderr()
        self.later(0.3, self.q.cancel, 1)
        self.make(profile=dict(PROFILE, minFreeMemoryMb=5000)).run_once()
        self.assert_cancelled_clean()

    def test_ollama_that_does_not_unload(self):
        self.add()
        with FakeOllama([{"name": "m", "size": 9}], unloads=False, on_ps=lambda n: self.q.cancel(1)) as fake:
            os.environ["GRUN_OLLAMA_URL"] = fake.url
            self.make(profile={"timeoutS": 60}).run_once()
        self.assert_cancelled_clean()


class AttemptAlreadyMadeTests(WorkerBase):  # invariant 9
    def test_running_entry_without_worker_is_recovered_and_not_rerun(self):
        self.add()
        self.assertEqual(self.q.claim()["id"], 1)  # `running`, and nobody is the worker
        store = FakeStore(attempt=7)
        w = self.make(order_store=store)
        self.assertEqual(w.run(), 1)
        entry = self.entry()
        self.assertEqual((entry["state"], entry["attemptId"], entry["error"]), ("done", 7, None))
        self.assertEqual(self.engine.calls, [])
        self.assertEqual(store.added, [])
        self.assertFalse(paths.machine_lock_path().exists())  # the machine lock was not even taken
        self.assertIn("OrphanRecovered", self.names())

    def test_new_attempt_is_stored_and_closes_the_entry(self):
        self.add()
        store = FakeStore()
        self.make(FakeEngine(lambda *a: {"file": "x"}), order_store=store).run_once()
        self.assertEqual(store.added, [(1, {"file": "x"})])
        self.assertEqual((self.entry()["state"], self.entry()["attemptId"]), ("done", 101))

    def test_failed_or_cancelled_runs_store_nothing(self):
        self.add(2)
        store = FakeStore()

        def fn(job, on_progress, should_cancel, fds):
            if job.entry["id"] == 1:
                raise EngineError("boom")
            self.q.cancel(2)
            return "late"

        w = self.make(FakeEngine(fn), order_store=store)
        w.run()
        self.assertEqual((self.entry(1)["state"], self.entry(2)["state"]), ("failed", "cancelled"))
        self.assertEqual(store.added, [])


class OllamaClientTests(WorkerBase):  # invariant 11
    def test_non_local_url_fails_the_entry(self):
        self.add()
        os.environ["GRUN_OLLAMA_URL"] = "http://example.com:11434"
        self.make(profile={"timeoutS": 60}).run_once()
        self.assertEqual((self.entry()["state"], self.code()), ("failed", "net.non_local_host"))
        self.assertEqual(self.engine.calls, [])

    def test_bad_scheme_fails_the_entry(self):
        self.add()
        os.environ["GRUN_OLLAMA_URL"] = "ftp://localhost"
        self.make(profile={"timeoutS": 60}).run_once()
        self.assertEqual((self.entry()["state"], self.code()), ("failed", "engine.ollama_url"))


class EvictModesTests(WorkerBase):
    def run_with(self, fake, mode):
        os.environ["GRUN_OLLAMA_URL"] = fake.url
        self.add()
        self.make(profile={"timeoutS": 60, "engine": {"ollama": mode}} if mode else {"timeoutS": 60}).run_once()

    def test_unload_is_the_default(self):
        with FakeOllama([{"name": "m", "size": 9}]) as fake:
            self.run_with(fake, None)
            self.assertEqual(fake.models, [])
        self.assertEqual(self.entry()["state"], "done")
        self.assertEqual(len(self.engine.calls), 1)
        event = [e for e in self.events() if e.get("event") == "OllamaEvicted"][0]
        self.assertEqual(event["models"], ["m"])

    def test_abort_with_models_fails(self):
        with FakeOllama([{"name": "m", "size": 9}]) as fake:
            self.run_with(fake, "abort")
            self.assertEqual(fake.paths(), [("GET", "/api/ps")])
        self.assertEqual((self.entry()["state"], self.code()), ("failed", "engine.ollama_loaded"))
        self.assertEqual(self.engine.calls, [])

    def test_ignore_does_not_call(self):
        with FakeOllama([{"name": "m", "size": 9}]) as fake:
            self.run_with(fake, "ignore")
            self.assertEqual(fake.requests, [])
        self.assertEqual(self.entry()["state"], "done")
        self.assertNotIn("OllamaEvicted", self.names())

    def test_ollama_off_goes_on(self):
        os.environ["GRUN_OLLAMA_URL"] = "http://127.0.0.1:9"  # the discard port: connection refused
        self.add()
        self.make(profile={"timeoutS": 60}).run_once()
        self.assertEqual(self.entry()["state"], "done")


class OrderInsideTheHolderTests(WorkerBase):
    def test_evict_then_memory_then_engine_with_the_lock_held(self):
        steps = []

        def seen(name):
            steps.append((name, machine_lock.busy(), bool(machine_lock.held_fds())))

        def fake_evict(machine, should_cancel=None, **kw):
            seen("evict")
            return []

        def fake_memory():
            seen("memory")
            return 99999

        self.add()
        engine = FakeEngine(lambda *a: seen("engine"))
        with mock.patch.object(ollama, "evict", fake_evict), mock.patch.object(limits, "available_memory_mb",
                                                                              fake_memory):
            self.make(engine, profile=dict(PROFILE, minFreeMemoryMb=10)).run_once()
        self.assertEqual(steps, [("evict", True, True), ("memory", True, True), ("engine", True, True)])
        self.assertFalse(machine_lock.busy())
        self.assertEqual(machine_lock.held_fds(), ())

    def test_engine_gets_the_held_descriptors(self):  # invariant 3, through the worker
        seen = {}

        def fn(job, on_progress, should_cancel, pass_fds):
            seen["fds"] = pass_fds
            seen["held"] = machine_lock.held_fds()

        self.add()
        self.make(FakeEngine(fn)).run_once()
        self.assertTrue(seen["fds"])
        self.assertEqual(seen["fds"], seen["held"])

    def test_job_carries_entry_and_profile(self):
        self.add()
        self.make(profile=dict(PROFILE, custom=5)).run_once()
        job = self.engine.calls[0][0]
        self.assertEqual((job.entry["kind"], job.entry["id"], job.machine["custom"]), ("line", 1, 5))


class MemoryTests(WorkerBase):
    def setUp(self):
        super().setUp()
        self.stderr()  # the waiting message goes to stderr: keep it out of the test output

    def test_waits_until_memory_returns_and_says_so_once(self):
        self.set_memory(MEM_LOW)
        self.add()
        err = self.stderr()
        self.later(0.3, self.set_memory, MEM_OK)
        self.make(profile=dict(PROFILE, minFreeMemoryMb=5000)).run_once()
        self.assertEqual(self.entry()["state"], "done")
        self.assertEqual(err.getvalue().count("waiting for memory"), 1)
        self.assertIn("100 MB are free", err.getvalue())
        event = [e for e in self.events() if e.get("event") == "MemoryWaited"][0]
        self.assertGreaterEqual(event["waitedMs"], 100)

    def test_enough_memory_does_not_wait(self):
        self.add()
        self.make(profile=dict(PROFILE, minFreeMemoryMb=5000)).run_once()
        self.assertEqual(self.entry()["state"], "done")
        self.assertNotIn("MemoryWaited", self.names())

    def test_unreadable_memory_passes(self):
        os.environ["GRUN_MEMINFO"] = str(self.tmp / "nothing")
        self.add()
        self.make(profile=dict(PROFILE, minFreeMemoryMb=5000)).run_once()
        self.assertEqual(self.entry()["state"], "done")

    def test_engine_threshold_wins_over_the_profile(self):
        self.set_memory(MEM_LOW)
        self.add()
        self.make(ThresholdEngine(50), profile=dict(PROFILE, minFreeMemoryMb=5000)).run_once()
        self.assertEqual(self.entry()["state"], "done")

    def test_engine_threshold_can_be_higher(self):
        self.set_memory(MEM_LOW)
        self.add()
        self.later(0.2, self.q.cancel, 1)
        self.make(ThresholdEngine(5000), profile=dict(PROFILE, minFreeMemoryMb=10)).run_once()
        self.assertEqual(self.entry()["state"], "cancelled")
        self.assertEqual(self.engine.calls, [])

    def test_engine_threshold_none_uses_the_profile(self):
        self.set_memory(MEM_LOW)
        self.add()
        self.later(0.2, self.q.cancel, 1)
        self.make(ThresholdEngine(None), profile=dict(PROFILE, minFreeMemoryMb=5000)).run_once()
        self.assertEqual(self.entry()["state"], "cancelled")
        self.assertEqual(self.engine.calls, [])


class ErrorMappingTests(WorkerBase):
    def failing(self, exc):
        self.add()

        def fn(*a):
            raise exc

        self.make(FakeEngine(fn)).run_once()
        return self.entry()

    def test_engine_error_without_code(self):
        entry = self.failing(EngineError("it broke"))
        self.assertEqual((entry["state"], entry["error"]["code"], entry["error"]["params"]),
                         ("failed", "engine.failed", {"message": "it broke"}))

    def test_engine_error_with_code(self):
        entry = self.failing(EngineError("x", code="engine.low_memory", free=1, min=2))
        self.assertEqual((entry["error"]["code"], entry["error"]["params"]), ("engine.low_memory", {"free": 1, "min": 2}))

    def test_engine_timeout(self):
        entry = self.failing(EngineTimeout("slow"))
        self.assertEqual((entry["state"], entry["error"]["code"]), ("failed", "engine.timeout"))

    def test_any_exception(self):
        entry = self.failing(ValueError("bad value"))
        self.assertEqual((entry["state"], entry["error"]["code"]), ("failed", "worker.unexpected"))
        self.assertEqual(entry["error"]["params"], {"message": "ValueError: bad value"})

    def test_grun_error_from_the_engine(self):
        entry = self.failing(GrunError("limit.memory", free=1, min=2))
        self.assertEqual((entry["error"]["code"], entry["error"]["params"]), ("limit.memory", {"free": 1, "min": 2}))

    def test_grun_error_of_the_profile_closes_the_entry_without_the_lock(self):
        self.add()
        errors = [{"path": "timeoutS", "code": "machine.field", "params": {"field": "timeoutS", "expected": "x"}}]

        def load():
            raise GrunError("machine.invalid", path="p.json", errors=errors)

        w = worker.Worker(self.q, FakeEngine(), app="a", load_profile=load, lang="en")
        w.run_once()
        entry = self.entry()
        self.assertEqual((entry["state"], entry["error"]["code"]), ("failed", "machine.invalid"))
        self.assertEqual(entry["error"]["errors"][0]["path"], "timeoutS")
        self.assertEqual(entry["error"]["params"], {"path": "p.json"})
        self.assertFalse(paths.machine_lock_path().exists())

    def test_cancelled_after_a_cancel_request(self):
        self.add()

        def fn(job, on_progress, should_cancel, fds):
            self.q.cancel(1)
            raise Cancelled()

        self.make(FakeEngine(fn)).run_once()
        self.assertEqual((self.entry()["state"], self.entry()["error"]), ("cancelled", None))

    def test_cancel_request_after_a_normal_return_is_a_cancel(self):
        self.add()
        self.make(FakeEngine(lambda *a: self.q.cancel(1))).run_once()
        self.assertEqual(self.entry()["state"], "cancelled")

    def test_cancelled_without_a_request_is_unexpected(self):
        entry = self.failing(Cancelled())
        self.assertEqual((entry["state"], entry["error"]["code"]), ("failed", "worker.unexpected"))

    def test_keyboard_interrupt_is_not_caught(self):
        self.add()

        def fn(*a):
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            self.make(FakeEngine(fn)).run_once()
        self.assertEqual(self.entry()["state"], "running")
        self.assertFalse(machine_lock.busy())

    def test_finish_failure_is_reported_and_survived(self):
        self.add(2)
        err = self.stderr()
        w = self.make()
        real = self.q.finish
        calls = []

        def finish(*a, **kw):
            calls.append(a)
            if len(calls) == 1:
                raise GrunError("queue.corrupt", path="q")
            return real(*a, **kw)

        with mock.patch.object(self.q, "finish", finish):
            self.assertEqual(w.run(), 2)
        self.assertIn("could not finish queue entry 1: queue.corrupt", err.getvalue())
        self.assertEqual(self.entry(2)["state"], "done")


class WorkerLockTests(WorkerBase):
    def lock_path(self):
        return paths.worker_lock_path(self.data)

    def test_another_worker_holds_it(self):
        self.hold(self.lock_path())
        self.add()
        w = self.make()
        with self.assertRaises(GrunError) as cm:
            w.run()
        self.assertEqual(cm.exception.code, "worker.already_running")
        self.assertEqual(cm.exception.params["path"], str(self.lock_path()))
        self.assertEqual(self.engine.calls, [])
        self.assertEqual(self.entry()["state"], "queued")

    def test_a_probe_that_lets_go_at_once(self):
        self.hold(self.lock_path(), HOLD_SH, "0.1")
        self.add()
        self.assertEqual(self.make().run(), 1)

    def test_a_probe_that_lasts_longer_than_the_short_retry(self):
        self.hold(self.lock_path(), HOLD_SH, "0.7")
        self.add()
        self.assertEqual(self.make().run(), 1)

    def test_held_during_run_and_released_after_without_deleting_the_file(self):
        seen = []
        self.add()
        self.make(FakeEngine(lambda *a: seen.append(self.q.worker_alive()))).run()
        self.assertEqual(seen, [True])
        self.assertFalse(self.q.worker_alive())
        self.assertTrue(self.lock_path().is_file())

    def test_released_when_run_fails_early(self):
        err = self.stderr()
        with mock.patch.object(self.q, "recover_orphans", side_effect=GrunError("queue.corrupt", path="q")):
            self.assertEqual(self.make().run(), 0)
        self.assertIn("unexpected worker error", err.getvalue())
        self.assertFalse(self.q.worker_alive())


class LoopTests(WorkerBase):
    def test_empty_queue_is_zero(self):
        self.assertEqual(self.make().run(), 0)
        self.assertFalse(self.make().run_once())

    def test_runs_everything_in_order(self):
        self.add(3)
        self.assertEqual(self.make().run(), 3)
        self.assertEqual([c[0].entry["n"] for c in self.engine.calls], [0, 1, 2])
        self.assertEqual([e["state"] for e in self.q.list_entries()], ["done"] * 3)

    def test_once_treats_one(self):
        self.add(3)
        self.assertEqual(self.make().run(once=True), 1)
        self.assertEqual([e["state"] for e in self.q.list_entries()], ["done", "queued", "queued"])

    def test_paused_claims_nothing(self):
        self.add()
        self.q.pause()
        self.assertEqual(self.make().run(), 0)
        self.assertEqual((self.entry()["state"], self.engine.calls), ("queued", []))

    def test_entry_that_died_twice_fails_without_running(self):
        self.add()
        self.q.claim()
        path = paths.queue_path(self.data)
        data = json.loads(path.read_text())
        data["entries"][0]["orphanCount"] = 1
        path.write_text(json.dumps(data))
        self.assertEqual(self.make().run(), 0)
        self.assertEqual((self.entry()["state"], self.code()), ("failed", "queue.orphaned"))
        self.assertEqual(self.engine.calls, [])

    def test_signal_handlers_inside_run_and_restored_after(self):
        before = signal.getsignal(signal.SIGTERM)
        seen = []
        self.add()
        self.make(FakeEngine(lambda *a: seen.append(signal.getsignal(signal.SIGTERM)))).run()
        self.assertNotEqual(seen[0], before)
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)

    def test_sigterm_during_the_engine_leaves_the_entry_running_for_the_next_run(self):
        self.add()
        marker = self.tmp / "marker"
        proc = self.spawn(SIGTERM_WORKER, str(self.data), str(marker))
        self.assertEqual(proc.stdout.readline().strip(), "engine")
        proc.send_signal(signal.SIGTERM)
        self.assertEqual(proc.wait(timeout=10), 128 + signal.SIGTERM)
        self.assertEqual(marker.read_text(), "finally")  # the finally blocks ran
        self.assertEqual(self.entry()["state"], "running")
        self.assertFalse(machine_lock.busy())
        self.assertEqual(self.make().run(), 1)  # recovers it (back to queued) and runs it
        self.assertEqual((self.entry()["state"], self.entry()["orphanCount"]), ("done", 1))


class ProgressTests(WorkerBase):
    def test_progress_and_preview_reach_the_queue_and_bad_progress_is_swallowed(self):
        seen = {}

        def fn(job, on_progress, should_cancel, fds):
            on_progress({"step": 1, "steps": 3, "etaS": 2.5, "preview": "/tmp/p.png"})
            seen["entry"] = self.entry()
            with self.assertRaises(GrunError) as cm:
                self.q.set_progress(1, {"step": 9, "steps": 3, "etaS": None})
            seen["code"] = cm.exception.code
            on_progress({"step": 9, "steps": 3, "etaS": None})
            on_progress({"step": 1})
            on_progress("junk")
            on_progress(None)
            on_progress({"step": 2, "steps": 3, "etaS": None, "preview": 5})
            seen["after"] = self.entry()
            return "ok"

        self.add()
        self.make(FakeEngine(fn)).run_once()
        self.assertEqual(seen["entry"]["progress"], {"step": 1, "steps": 3, "etaS": 2.5})
        self.assertEqual(seen["entry"]["preview"], "/tmp/p.png")
        self.assertEqual(seen["code"], "queue.bad_progress")
        self.assertEqual(seen["after"]["progress"], {"step": 2, "steps": 3, "etaS": None})
        self.assertEqual(seen["after"]["preview"], "/tmp/p.png")
        self.assertEqual((self.entry()["state"], self.entry()["error"]), ("done", None))

    def test_should_cancel_follows_the_queue(self):
        seen = []

        def fn(job, on_progress, should_cancel, fds):
            seen.append(should_cancel())
            self.q.cancel(1)
            seen.append(should_cancel())

        self.add()
        self.make(FakeEngine(fn)).run_once()
        self.assertEqual(seen, [False, True])


class EventsTests(WorkerBase):
    def test_events_and_the_run_line(self):
        self.add()
        self.make().run()
        lines = self.events()
        events = [e for e in lines if "event" in e]
        self.assertEqual([e["event"] for e in events], ["EntryClaimed", "LockAcquired", "EntryFinished"])
        for e in events:
            self.assertEqual((e["app"], e["entry"]), ("testapp", 1))
            self.assertTrue(e["at"])
        self.assertIn("waitedMs", events[1])
        self.assertEqual((events[2]["state"], events[2]["errorCode"]), ("done", None))
        summary = lines[-1]
        self.assertEqual({k: summary[k] for k in ("schema", "app", "entry", "state", "errorCode")},
                         {"schema": "grun.run/0", "app": "testapp", "entry": 1, "state": "done", "errorCode": None})
        for key in ("lockWaitMs", "memoryWaitMs", "runMs"):
            self.assertIsInstance(summary[key], int)

    def test_failed_entry_events_carry_the_code(self):
        self.add()

        def fn(*a):
            raise EngineTimeout("slow")

        self.make(FakeEngine(fn)).run()
        finished = [e for e in self.events() if e.get("event") == "EntryFinished"][0]
        self.assertEqual((finished["state"], finished["errorCode"]), ("failed", "engine.timeout"))
        self.assertEqual(self.events()[-1]["errorCode"], "engine.timeout")

    def test_orphan_recovered_event(self):
        self.add()
        self.q.claim()
        self.make().run()
        orphan = [e for e in self.events() if e.get("event") == "OrphanRecovered"]
        self.assertEqual([(e["entry"], e["state"]) for e in orphan], [(1, "queued")])

    def test_unwritable_log_does_not_stop_the_entry(self):
        self.add()
        err = self.stderr()
        self.make(log_path=self.tmp).run()  # a folder, not a file
        self.assertEqual(self.entry()["state"], "done")
        self.assertIn("could not write the log line of entry 1", err.getvalue())

    def test_no_log_path(self):
        self.add()
        self.make(log_path=None).run()
        self.assertEqual(self.entry()["state"], "done")
        self.assertFalse(self.log_path.exists())


if __name__ == "__main__":
    unittest.main()
