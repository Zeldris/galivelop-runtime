import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from grun import fsutil, paths, queue
from grun.errors import GrunError

ROOT = Path(__file__).resolve().parent.parent
HOLD_WORKER = (  # another process that is the worker: holds worker.lock exclusively
    "import fcntl, os, sys, time\n"
    "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
    "fcntl.flock(fd, fcntl.LOCK_EX)\n"
    "print('held', flush=True)\n"
    "time.sleep(60)\n")


class QueueBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name).resolve() / "data"
        self.q = queue.Queue(self.data)

    def add(self, n=1, **kw):
        return self.q.enqueue([{"project": "p", "n": i} for i in range(n)], **kw)

    def ids(self, states=None):
        return [e["id"] for e in self.q.list_entries(states)]

    def run_one(self):
        """Claim the first queued entry (the worker lock is held by this test's fake worker)."""
        return self.q.claim()

    def raw(self):
        return json.loads(paths.queue_path(self.data).read_text(encoding="utf-8"))

    def write_raw(self, data):
        paths.queue_path(self.data).parent.mkdir(parents=True, exist_ok=True)
        fsutil.write_json(paths.queue_path(self.data), data)

    def code(self, call, *args, **kw):
        with self.assertRaises(GrunError) as cm:
            call(*args, **kw)
        return cm.exception.code

    def fake_worker(self):
        """A live worker: a process holding worker.lock; killed on cleanup."""
        path = paths.worker_lock_path(self.data)
        path.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen([sys.executable, "-c", HOLD_WORKER, str(path)], stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        self.assertEqual(proc.stdout.readline().strip(), "held")
        return proc


class OrderTests(QueueBase):  # invariant 7
    def test_enqueue_fields(self):
        entry = self.add()[0]
        self.assertEqual((entry["id"], entry["position"], entry["state"]), (1, 1, "queued"))
        self.assertEqual((entry["orphanCount"], entry["cancelRequested"], entry["project"]), (0, False, "p"))
        for key in ("pid", "startedAt", "finishedAt", "error", "attemptId"):
            self.assertIsNone(entry[key])
        self.assertTrue(entry["enqueuedAt"])

    def test_claim_follows_position_then_id(self):
        self.add(3)
        self.q.move(3, "top")
        self.assertEqual([self.q.claim()["id"] for _ in range(3)], [3, 1, 2])

    def test_equal_positions_go_by_id(self):
        self.add(3)
        data = self.raw()
        for e in data["entries"]:
            e["position"] = 5
        self.write_raw(data)
        self.assertEqual(self.q.next_queued()["id"], 1)

    def test_missing_or_invalid_position_is_the_id(self):
        self.add(3)
        data = self.raw()
        del data["entries"][0]["position"]
        data["entries"][1]["position"] = "x"
        data["entries"][2]["position"] = True
        self.write_raw(data)
        self.assertEqual([self.q.claim()["id"] for _ in range(3)], [1, 2, 3])

    def test_position_beats_id(self):
        self.add(2)
        data = self.raw()
        data["entries"][0]["position"] = 10
        self.write_raw(data)
        self.assertEqual(self.q.claim()["id"], 2)

    def test_later_enqueue_goes_last_after_move(self):
        self.add(2)
        self.q.move(2, "top")
        self.add()
        self.assertEqual([self.q.claim()["id"] for _ in range(3)], [2, 1, 3])


class TransitionTests(QueueBase):  # invariant 8
    def test_table_is_the_only_way(self):
        # every (from, to) pair outside the table is refused by _transition with its code
        allowed = {("queued", "running"), ("queued", "cancelled"), ("running", "done"), ("running", "failed"),
                   ("running", "cancelled"), ("running", "queued")}
        for a in queue.STATES:
            for b in queue.STATES:
                if (a, b) in allowed:
                    continue
                entry = {"id": 1, "state": a}
                for via in queue.VIAS:
                    with self.assertRaises(GrunError) as cm:
                        queue._transition(entry, b, via=via)
                    self.assertEqual(cm.exception.code, "queue.invalid_transition")
                    self.assertEqual(entry["state"], a)

    def test_pair_with_the_wrong_route_is_refused(self):
        entry = {"id": 1, "state": "queued"}
        with self.assertRaises(GrunError) as cm:
            queue._transition(entry, "done", via="finish")
        self.assertEqual(cm.exception.code, "queue.invalid_transition")
        entry = {"id": 1, "state": "queued"}
        with self.assertRaises(GrunError) as cm:
            queue._transition(entry, "running", via="recovery")
        self.assertEqual(cm.exception.code, "queue.invalid_transition")

    def test_every_public_change_of_state_goes_through_transition(self):
        calls = []
        real = queue._transition

        def spy(entry, to, *, via):
            calls.append((entry["id"], to, via))
            return real(entry, to, via=via)

        with mock.patch.object(queue, "_transition", spy):
            self.add(4, batch=False)
            self.q.cancel(4)
            self.q.clear(n=2)
            e = self.q.claim()
            self.q.finish(e["id"], "done")
            self.q.claim()
            self.q.cancel(2)
            self.q.finish(2, "cancelled")
        self.assertEqual([c[1:] for c in calls], [("cancelled", "cancel"), ("cancelled", "clear"),
                                                  ("running", "claim"), ("done", "finish"), ("running", "claim"),
                                                  ("cancelled", "finish")])

    def test_finish_of_a_queued_entry_is_not_running(self):
        self.add()
        self.assertEqual(self.code(self.q.finish, 1, "done"), "queue.not_running")

    def test_finish_cancelled_needs_the_request(self):
        self.add()
        self.q.claim()
        self.assertEqual(self.code(self.q.finish, 1, "cancelled"), "queue.invalid_transition")
        self.q.cancel(1)
        self.assertEqual(self.q.finish(1, "cancelled")["state"], "cancelled")

    def test_finish_bad_state(self):
        self.add()
        self.q.claim()
        self.assertEqual(self.code(self.q.finish, 1, "queued"), "queue.bad_state")

    def test_finish_failed_stores_error_and_attempt(self):
        self.add()
        self.q.claim()
        entry = self.q.finish(1, "failed", queue.make_error("engine.failed", message="x"), attempt_id="a1")
        self.assertEqual((entry["state"], entry["attemptId"], entry["pid"]), ("failed", "a1", None))
        self.assertEqual(entry["error"], {"code": "engine.failed", "params": {"message": "x"}})
        self.assertTrue(entry["finishedAt"])

    def test_cancel_of_a_finished_entry(self):
        self.add()
        self.q.claim()
        self.q.finish(1, "done")
        self.assertEqual(self.code(self.q.cancel, 1), "queue.not_cancellable")

    def test_cancel_running_only_requests(self):
        self.add()
        self.q.claim()
        entry = self.q.cancel(1)
        self.assertEqual((entry["state"], entry["cancelRequested"]), ("running", True))
        self.assertTrue(self.q.is_cancel_requested(1))

    def test_unknown_entry(self):
        self.assertEqual(self.code(self.q.get, 9), "queue.unknown")
        self.assertEqual(self.code(self.q.cancel, "1"), "queue.unknown")

    def test_claim_sets_running_fields(self):
        self.add()
        entry = self.q.claim()
        self.assertEqual((entry["state"], entry["pid"]), ("running", os.getpid()))
        self.assertTrue(entry["startedAt"])
        self.assertIsNone(self.q.claim())


class OrphanTests(QueueBase):  # invariant 9 (states)
    def test_first_orphaning_goes_back_to_queued(self):
        self.add()
        self.q.claim()
        self.q.set_progress(1, {"step": 1, "steps": 2, "etaS": None})
        self.q.set_preview(1, "/x.png")
        self.assertEqual(self.q.list_entries(["queued"])[0]["orphanCount"], 1)
        entry = self.q.get(1)
        self.assertEqual((entry["state"], entry["orphanCount"]), ("queued", 1))
        for key in ("pid", "startedAt"):
            self.assertIsNone(entry[key])
        self.assertNotIn("progress", entry)
        self.assertNotIn("preview", entry)

    def test_second_orphaning_fails_with_a_code(self):
        self.add()
        for _ in range(2):
            self.q.claim()
            self.q.recover_orphans()
        entry = self.q.get(1)
        self.assertEqual(entry["state"], "failed")
        self.assertEqual(entry["orphanCount"], 2)
        self.assertEqual(entry["error"]["code"], "queue.orphaned")
        self.assertEqual(entry["error"]["params"]["id"], 1)
        self.assertIn("1", self.q.entry_view(entry, "en")["errorText"])
        self.assertTrue(entry["finishedAt"])
        self.assertIsNone(self.q.next_queued())

    def test_cancel_requested_wins(self):
        self.add()
        self.q.claim()
        self.q.cancel(1)
        self.q.recover_orphans()
        entry = self.q.get(1)
        self.assertEqual((entry["state"], entry["orphanCount"]), ("cancelled", 0))

    def test_old_entry_without_count_counts_zero(self):
        self.add()
        self.q.claim()
        data = self.raw()
        del data["entries"][0]["orphanCount"]
        self.write_raw(data)
        self.q.recover_orphans()
        entry = self.q.get(1)
        self.assertEqual((entry["state"], entry["orphanCount"]), ("queued", 1))

    def test_reading_recovers_when_no_worker(self):
        self.add()
        self.q.claim()
        self.assertEqual(self.ids(["queued"]), [1])  # list_entries recovered it

    def test_reading_leaves_running_alone_with_a_live_worker(self):
        self.add()
        self.q.claim()
        self.fake_worker()
        self.assertEqual(self.q.get(1)["state"], "running")
        self.assertEqual(self.ids(["running"]), [1])
        self.add()  # enqueue tries recovery too
        self.assertEqual(self.q.get(1)["state"], "running")
        self.assertEqual(self.q.get(1)["orphanCount"], 0)

    def test_hook_runs_per_entry_and_its_errors_are_swallowed(self):
        seen = []

        def clean(entry):
            seen.append(entry["id"])
            raise RuntimeError("boom")

        self.q = queue.Queue(self.data, clean_pending=clean)
        self.add(2, batch=False)
        self.q.claim()
        self.q.claim()
        self.q.recover_orphans()
        self.assertEqual(sorted(seen), [1, 2])
        self.assertEqual(self.ids(["queued"]), [1, 2])

    def test_claim_and_finish_never_recover(self):
        self.add(2, batch=False)
        self.q.claim()
        # a second claim does not recover the first running entry (no recovery in claim)
        self.assertEqual(self.q.claim()["id"], 2)
        self.assertEqual(self.raw()["entries"][0]["state"], "running")


class AtomicTests(QueueBase):  # invariant 10
    def test_failed_replace_keeps_the_previous_queue(self):
        self.add(2, batch=False)
        before = self.raw()
        with mock.patch("grun.fsutil.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.add()
            with self.assertRaises(OSError):
                self.q.cancel(1)
        self.assertEqual(self.raw(), before)
        self.assertEqual(self.ids(), [1, 2])
        self.assertEqual(self.q.get(1)["state"], "queued")
        leftovers = [p.name for p in self.data.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_failed_write_in_claim_leaves_it_queued(self):
        self.add()
        with mock.patch("grun.fsutil.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.q.claim()
        self.assertEqual(self.q.get(1)["state"], "queued")

    def test_corrupt_file(self):
        paths.queue_path(self.data).parent.mkdir(parents=True)
        paths.queue_path(self.data).write_text("{nope", encoding="utf-8")
        self.assertEqual(self.code(self.q.list_entries), "queue.corrupt")
        paths.queue_path(self.data).write_text('{"nextId": 1, "entries": [{"id": 1, "state": "weird"}]}',
                                               encoding="utf-8")
        self.assertEqual(self.code(self.q.list_entries), "queue.corrupt")


class BatchTests(QueueBase):
    def test_default_batches_when_more_than_one(self):
        self.assertNotIn("batch", self.add(1)[0])
        entries = self.add(3)
        self.assertEqual([e["batch"] for e in entries], [{"id": 2, "index": i, "size": 3} for i in range(3)])

    def test_explicit_batch(self):
        self.assertEqual(self.add(1, batch=True)[0]["batch"], {"id": 1, "index": 0, "size": 1})
        self.assertTrue(all("batch" not in e for e in self.add(2, batch=False)))

    def test_items_are_deep_copied(self):
        item = {"params": {"a": [1]}}
        entry = self.q.enqueue([item])[0]
        item["params"]["a"].append(2)
        self.assertEqual(self.q.get(entry["id"])["params"], {"a": [1]})

    def test_core_key_is_refused_and_nothing_queued(self):
        for key in ("id", "state", "position", "orphanCount", "cancelRequested", "pid", "batch"):
            self.assertEqual(self.code(self.q.enqueue, [{"a": 1}, {key: 1}]), "queue.bad_item", key)
        self.assertEqual(self.code(self.q.enqueue, ["x"]), "queue.bad_item")
        self.assertEqual(self.q.list_entries(), [])

    def test_empty_enqueue(self):
        self.assertEqual(self.q.enqueue([]), [])

    def test_cancel_batch(self):
        self.fake_worker()  # reading must not recover the running entry
        self.add(3)
        self.q.claim()
        done = self.add(1)[0]  # separate entry
        mine = self.q.cancel_batch(1)
        self.assertEqual([e["state"] for e in mine], ["running", "cancelled", "cancelled"])
        self.assertTrue(self.q.is_cancel_requested(1))
        self.assertEqual(self.q.get(done["id"])["state"], "queued")
        self.assertEqual(self.code(self.q.cancel_batch, 77), "queue.batch_not_found")

    def test_cancel_batch_finished(self):
        self.add(2)
        self.q.cancel_batch(1)
        self.assertEqual(self.code(self.q.cancel_batch, 1), "queue.not_cancellable")

    def test_stop_batch(self):
        self.fake_worker()  # reading must not recover the running entry
        self.add(3)
        self.q.claim()
        stopped = self.q.stop_batch(1, "att-1")
        self.assertEqual([e["id"] for e in stopped], [2, 3])
        self.assertTrue(all(e["state"] == "cancelled" and e["stoppedBy"] == "att-1" for e in stopped))
        self.assertEqual(self.q.get(1)["state"], "running")
        self.assertEqual(self.q.stop_batch(99, "x"), [])

    def test_clear(self):
        self.fake_worker()  # reading must not recover the running entry
        self.q.enqueue([{"project": "a"}, {"project": "b"}, {"project": "a"}], batch=False)
        self.q.claim()
        cleared = self.q.clear(project="a")
        self.assertEqual([e["id"] for e in cleared], [3])
        self.assertEqual(self.ids(["queued"]), [2])
        self.assertEqual([e["id"] for e in self.q.clear()], [2])
        self.assertEqual(self.q.get(1)["state"], "running")


class MoveTests(QueueBase):
    def test_up_down_top(self):
        self.add(4, batch=False)
        self.q.move(3, "up")
        self.assertEqual(self.order(), [1, 3, 2, 4])
        self.q.move(1, "down")
        self.assertEqual(self.order(), [3, 1, 2, 4])
        self.q.move(4, "top")
        self.assertEqual(self.order(), [4, 3, 1, 2])
        self.q.move(4, "up")  # at the edge: nothing changes
        self.q.move(2, "down")
        self.assertEqual(self.order(), [4, 3, 1, 2])

    def order(self):
        return [e["id"] for e in sorted(self.q.list_entries(["queued"]), key=queue._pos)]

    def test_errors(self):
        self.add(2, batch=False)
        self.q.claim()
        self.assertEqual(self.code(self.q.move, 1, "up"), "queue.not_movable")
        self.assertEqual(self.code(self.q.move, 2, "sideways"), "queue.bad_move")
        self.assertEqual(self.code(self.q.move, 9, "up"), "queue.unknown")
        self.assertEqual(self.code(self.q.move_batch, 9, "up"), "queue.batch_not_found")
        self.assertEqual(self.code(self.q.move_batch, 1, "x"), "queue.bad_move")

    def test_move_batch(self):
        self.add(2)  # batch 1: ids 1,2
        self.add(1, batch=False)  # 3
        self.add(2)  # batch 4: ids 4,5
        self.q.move_batch(4, "up")
        self.assertEqual(self.order(), [1, 2, 4, 5, 3])
        self.q.move_batch(4, "up")
        self.assertEqual(self.order(), [4, 5, 1, 2, 3])
        self.q.move_batch(1, "down")
        self.assertEqual(self.order(), [4, 5, 3, 1, 2])
        self.q.move_batch(1, "top")
        self.assertEqual(self.order(), [1, 2, 4, 5, 3])

    def test_move_batch_with_legacy_batch_field(self):
        self.add(2)  # batch 1: ids 1,2
        self.add(3, batch=False)  # 3,4,5
        data = self.raw()
        data["entries"][2]["batch"] = "legacy"
        self.write_raw(data)
        self.q.move_batch(1, "down")
        self.assertEqual(self.order(), [3, 1, 2, 4, 5])

    def set_positions(self, pos):
        data = self.raw()
        for entry in data["entries"]:
            entry["position"] = pos
        self.write_raw(data)

    def claims(self, n):
        out = []
        for _ in range(n):
            entry = self.q.claim()
            out.append(entry["id"])
        return out

    def test_move_with_repeated_positions(self):
        self.add(3, batch=False)
        self.set_positions(5)
        self.q.move(3, "top")
        self.assertEqual(self.claims(3), [3, 1, 2])

    def test_move_batch_with_repeated_positions(self):
        self.add(1, batch=False)  # 1
        self.add(2)  # batch 2: ids 2,3
        self.set_positions(5)
        self.q.move_batch(2, "top")
        self.assertEqual(self.claims(3), [2, 3, 1])

    def test_move_batch_with_nothing_queued(self):
        self.add(2)
        self.q.cancel_batch(1)
        self.assertEqual(self.code(self.q.move_batch, 1, "top"), "queue.not_movable")


class PauseTests(QueueBase):
    def test_pause_blocks_claim(self):
        self.add()
        self.assertFalse(self.q.is_paused())
        self.assertTrue(self.q.pause())
        self.assertFalse(self.q.pause())
        self.assertTrue(self.q.is_paused())
        self.assertTrue(paths.pause_path(self.data).exists())
        self.assertIsNone(self.q.claim())
        self.assertEqual(self.q.get(1)["state"], "queued")
        self.assertTrue(self.q.resume())
        self.assertFalse(self.q.resume())
        self.assertEqual(self.q.claim()["id"], 1)

    def test_pause_does_not_touch_enqueue(self):
        self.q.pause()
        self.assertEqual(len(self.add()), 1)


class ProgressTests(QueueBase):
    def setUp(self):
        super().setUp()
        self.add()
        self.q.claim()

    def test_valid(self):
        entry = self.q.set_progress(1, {"step": 2, "steps": 10, "etaS": 1.5})
        self.assertEqual(entry["progress"], {"step": 2, "steps": 10, "etaS": 1.5})
        self.q.set_progress(1, {"step": 0, "steps": 1, "etaS": None})
        self.assertEqual(self.q.set_preview(1, "/p.png")["preview"], "/p.png")

    def test_same_value_does_not_rewrite(self):
        self.q.set_progress(1, {"step": 1, "steps": 2, "etaS": None})
        with mock.patch("grun.fsutil.write_json") as write:
            self.q.set_progress(1, {"step": 1, "steps": 2, "etaS": None})
        write.assert_not_called()

    def test_invalid(self):
        bad = [None, {}, {"step": 1, "steps": 2}, {"step": 3, "steps": 2, "etaS": None},
               {"step": -1, "steps": 2, "etaS": None}, {"step": 0, "steps": 0, "etaS": None},
               {"step": True, "steps": 2, "etaS": None}, {"step": 1.0, "steps": 2, "etaS": None},
               {"step": 1, "steps": 2, "etaS": -1}, {"step": 1, "steps": 2, "etaS": "x"},
               {"step": 1, "steps": 2, "etaS": None, "extra": 1}]
        for progress in bad:
            self.assertEqual(self.code(self.q.set_progress, 1, progress), "queue.bad_progress", progress)
        for path in (None, "", "a\nb", "a\x00b", 3):
            self.assertEqual(self.code(self.q.set_preview, 1, path), "queue.bad_progress", path)

    def test_needs_a_running_entry(self):
        self.q.finish(1, "done")
        self.assertEqual(self.code(self.q.set_progress, 1, {"step": 1, "steps": 2, "etaS": None}),
                         "queue.not_running")

    def test_finish_removes_progress(self):
        self.q.set_progress(1, {"step": 1, "steps": 2, "etaS": None})
        self.q.set_preview(1, "/p.png")
        entry = self.q.finish(1, "done")
        self.assertNotIn("progress", entry)
        self.assertNotIn("preview", entry)


class HeldTests(QueueBase):
    def setUp(self):
        super().setUp()
        self.q = queue.Queue(self.data, held=lambda e: "troubleshooting" if e.get("n") == 0 else None)

    def test_held_is_not_claimed_or_runnable(self):
        self.add(2, batch=False)
        self.assertEqual([e["id"] for e in self.q.list_runnable()], [2])
        self.assertEqual(self.q.next_queued()["id"], 2)
        self.assertEqual(self.q.claim()["id"], 2)
        self.assertIsNone(self.q.claim())
        self.assertEqual(self.q.get(1)["state"], "queued")

    def test_entry_view(self):
        self.add(2, batch=False)
        views = [self.q.entry_view(e) for e in self.q.list_entries()]
        self.assertEqual(views[0]["held"], "troubleshooting")
        self.assertNotIn("held", views[1])
        self.assertNotIn("errorText", views[1])

    def test_without_hook_nothing_is_held(self):
        q = queue.Queue(self.data)
        self.add(1)
        self.assertEqual(len(q.list_runnable()), 1)


class PruneTests(QueueBase):
    def test_keeps_the_last_terminal(self):
        self.q = queue.Queue(self.data, keep_terminal=2)
        self.add(5, batch=False)
        for _ in range(4):
            entry = self.q.claim()
            self.q.finish(entry["id"], "done")
        self.assertEqual(self.ids(), [3, 4, 5])  # 1 and 2 pruned on the next transaction; 5 still queued
        self.assertEqual(self.raw()["nextId"], 6)


class WorkerAliveTests(QueueBase):
    def test_pure_read_creates_nothing(self):
        self.assertIs(self.q.worker_alive(), False)
        self.assertFalse(self.data.exists())
        self.data.mkdir()
        self.assertIs(self.q.worker_alive(), False)
        self.assertEqual(list(self.data.iterdir()), [])

    def test_alive_with_another_process(self):
        self.fake_worker()
        self.assertIs(self.q.worker_alive(), True)
        self.assertIs(self.q.worker_alive(), True)

    def test_probes_do_not_see_each_other(self):
        paths.worker_lock_path(self.data).parent.mkdir(parents=True)
        paths.worker_lock_path(self.data).touch()
        fd = os.open(str(paths.worker_lock_path(self.data)), os.O_RDWR)
        self.addCleanup(os.close, fd)
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_SH)
        self.assertIs(self.q.worker_alive(), False)

    def test_unknown_when_it_cannot_be_opened(self):
        paths.worker_lock_path(self.data).parent.mkdir(parents=True)
        paths.worker_lock_path(self.data).touch()
        with mock.patch("grun.fsutil.os.open", side_effect=PermissionError):
            self.assertIsNone(self.q.worker_alive())


class OldFileTests(QueueBase):
    def test_gimg_and_gvoice_files_load(self):
        old = {"nextId": 4, "entries": [
            {"id": 1, "project": "p", "key": "k", "profile": "pr", "state": "done", "extra": {"x": 1}},
            {"id": 2, "kind": "voice", "state": "queued", "text": "hi"},
            {"id": 3, "state": "queued", "position": 1, "batch": {"id": 3, "index": 0, "size": 1}}]}
        self.write_raw(old)
        entries = self.q.list_entries()
        self.assertEqual([e["id"] for e in entries], [1, 2, 3])
        self.assertEqual(entries[0]["extra"], {"x": 1})
        self.assertEqual(self.q.claim()["id"], 3)  # position 1 beats id 2's implicit position 2
        self.assertEqual(self.q.claim()["id"], 2)
        self.assertEqual(self.add()[0]["id"], 4)
        self.assertEqual(self.q.get(1)["extra"], {"x": 1})

    def test_error_text_of_old_shapes(self):
        self.assertEqual(queue.error_text(None), "")
        self.assertEqual(queue.error_text("plain"), "plain")
        self.assertEqual(queue.error_text({"state": "failed", "error": "old text"}), "old text")
        self.assertEqual(queue.error_text({"code": "no.such.code"}, "en"), "no.such.code")


class ErrorTextTests(unittest.TestCase):
    def test_make_error_and_text(self):
        error = queue.make_error("queue.not_running", id=3, state="done", obj=Path("/x"))
        self.assertEqual(error["params"]["obj"], "/x")
        self.assertEqual(queue.error_text(error, "en"), "entry 3 is not running (state: done)")
        self.assertIn("no está en marcha", queue.error_text(error, "es"))

    def test_schema_lines(self):
        class E:
            path, code, params = "a.b", "path.empty", {}

        error = queue.make_error("queue.corrupt", [E, {"path": "c", "code": "path.nul", "params": {}}], path="q")
        self.assertEqual(error["errors"][0], {"path": "a.b", "code": "path.empty", "params": {}})
        self.assertEqual(queue.error_text(error, "en").split("\n"),
                         ["the queue q is corrupt", "- a.b: the path is empty",
                          "- c: the path contains a NUL character"])

    def test_odd_stored_errors_are_skipped(self):
        error = {"code": "queue.corrupt", "params": {"path": "q"}, "errors": [3, {"path": "x"}]}
        self.assertEqual(queue.error_text(error, "en"), "the queue q is corrupt")


class SourceTests(unittest.TestCase):
    def test_queue_imports_only_grun_and_stdlib(self):
        import ast
        tree = ast.parse((ROOT / "grun" / "queue.py").read_text(encoding="utf-8"))
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods.add((node.module or "").split(".")[0])
        self.assertEqual(mods - set(sys.stdlib_module_names), set())


if __name__ == "__main__":
    unittest.main()
