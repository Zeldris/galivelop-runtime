"""Invariant 13: the shape of /api/queue and of the entry that the interfaces of gimg and gvoice read does not lose
fields or change meaning. The responses are fixed as examples (`tests/examples/api/`) and validated against
`schemas/grun.queue/0`; the live server must give every field the examples have."""
import json
import unittest
from pathlib import Path

from grun import queue
from tests import jsonschema_lite as js
from tests.test_server import ServerBase

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schemas" / "grun.queue.0.json").read_text(encoding="utf-8"))
EXAMPLES = ROOT / "tests" / "examples" / "api"
SHAPES = {"list.json": "list", "entry.json": "view", "entries.json": "entries", "pause.json": "pause",
          "health.json": "health", "error.json": "apiError"}


def example(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def check(value, shape):
    return js.errors(value, {"$ref": "#/$defs/" + shape}, SCHEMA)


def fields(value):
    """The set of field names of an object, or of every object of a list (one level)."""
    rows = value if isinstance(value, list) else [value]
    return {k for row in rows for k in row}


class SchemaTests(unittest.TestCase):
    def test_every_example_is_valid(self):
        for name, shape in SHAPES.items():
            self.assertEqual(check(example(name), shape), [], name)

    def test_the_checker_is_not_a_yes_machine(self):
        bad = example("entry.json")
        bad["state"] = "paused"
        self.assertIn("is not one of", " ".join(check(bad, "view")))
        del bad["enqueuedAt"]
        self.assertIn("missing enqueuedAt", " ".join(check(bad, "view")))
        self.assertIn("is not of type", " ".join(check(dict(example("entry.json"), orphanCount="0"), "view")))
        self.assertIn("unknown keyword", " ".join(js.errors(1, {"format": "x"}, {})))

    def test_an_old_entry_without_the_new_fields_is_valid(self):
        old = {"id": 1, "position": 1, "state": "queued", "enqueuedAt": "2026-01-01T00:00:00Z", "project": "p"}
        self.assertEqual(check(old, "entry"), [])

    def test_the_examples_cover_every_core_field(self):
        seen = fields(example("list.json")) | fields(example("entries.json")["entries"])
        self.assertLessEqual(set(queue.CORE_KEYS) - {"preview"}, seen)


class LiveTests(ServerBase):
    """What the server really sends has to be valid and has to have every field of the examples."""

    def setUp(self):
        super().setUp()
        self.q._held = lambda e: "needs the model" if e["id"] == 2 else None
        self.q._estimate = lambda e: 52000
        self.add(2, batch=True)
        self.add(1)
        self.hold_worker()
        self.q.claim()
        self.q.set_progress(1, {"step": 3, "steps": 20, "etaS": 41.5})
        self.q.finish(1, "failed", error=queue.make_error("engine.failed", reason="boom"), attempt_id="att-1")
        self.q.claim()
        self.q.set_progress(3, {"step": 1, "steps": 2, "etaS": None})

    def test_the_list_is_valid_and_keeps_every_field(self):
        status, data, resp = self.json("GET", "/api/queue")
        self.assertEqual(status, 200)
        self.assertEqual(check(data, "list"), [])
        self.assertLessEqual(fields(example("list.json")) - {"stoppedBy"}, fields(data))
        self.assertEqual(resp.getheader("X-Queue-Paused"), "0")

    def test_stopped_batch_entries_carry_stopped_by(self):
        self.q.stop_batch(1, "att-9")
        data = self.json("GET", "/api/queue?state=cancelled")[1]
        self.assertEqual(check(data, "list"), [])
        self.assertIn("stoppedBy", fields(data))

    def test_cancel_and_move_give_a_valid_entry(self):
        status, data, _ = self.json("POST", "/api/queue/2/cancel", {})
        self.assertEqual((status, check(data, "view")), (200, []))
        self.assertLessEqual(fields(example("entry.json")), fields(data))

    def test_batch_replies_are_valid(self):
        self.add(2, batch=True)
        data = self.json("POST", "/api/queue/batches/4/move", {"to": "top"})[1]
        self.assertEqual(check(data, "entries"), [])
        self.assertLessEqual(fields(example("entries.json")["entries"]), fields(data["entries"]))
        data = self.json("POST", "/api/queue/batches/4/cancel", {})[1]
        self.assertEqual(check(data, "entries"), [])

    def test_pause_resume_clear_and_health(self):
        for path in ("pause", "resume"):
            data = self.json("POST", "/api/queue/" + path, {})[1]
            self.assertEqual(check(data, "pause"), [])
            self.assertEqual(set(data), set(example("pause.json")))
        data = self.json("POST", "/api/queue/clear", {})[1]
        self.assertEqual(check(data, "list"), [])
        health = self.json("GET", "/api/health")[1]
        self.assertEqual(check(health, "health"), [])
        self.assertEqual(set(health), set(example("health.json")))

    def test_an_error_body_is_valid_and_has_the_example_fields(self):
        status, data, _ = self.json("POST", "/api/queue/99/cancel", {})
        self.assertEqual((status, check(data, "apiError")), (404, []))
        self.assertEqual(set(data["error"]), set(example("error.json")["error"]))

    def test_the_queue_file_itself_is_valid_against_the_schema(self):
        data = json.loads((self.data / "queue.json").read_text(encoding="utf-8"))
        self.assertEqual(js.errors(data, SCHEMA, SCHEMA), [])


if __name__ == "__main__":
    unittest.main()
