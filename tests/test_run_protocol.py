"""R6.2: the published protocol `grun.run/1` (docs/protocol/grun.run.1.md): the summary line the worker writes
validates against `schemas/grun.run.1.json` for every final state."""
import json
import unittest
from pathlib import Path

from grun.engine import EngineTimeout
from tests import jsonschema_lite as js
from tests.test_worker import FakeEngine, WorkerBase

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schemas" / "grun.run.1.json").read_text(encoding="utf-8"))


def problems(value):
    return js.errors(value, SCHEMA, SCHEMA)


class RunSummaryTests(WorkerBase):
    def summaries(self):
        return [line for line in self.events() if "schema" in line]

    def test_done_summary_is_valid(self):
        self.add()
        self.make().run()
        (summary,) = self.summaries()
        self.assertEqual(problems(summary), [])
        self.assertEqual(summary["schema"], "grun.run/1")

    def test_failed_summary_is_valid_and_carries_the_code(self):
        self.add()

        def fn(*a):
            raise EngineTimeout("slow")

        self.make(FakeEngine(fn)).run()
        (summary,) = self.summaries()
        self.assertEqual(problems(summary), [])
        self.assertEqual((summary["state"], summary["errorCode"]), ("failed", "engine.timeout"))

    def test_event_lines_are_not_summaries(self):
        self.add()
        self.make().run()
        self.assertTrue(all("schema" not in e for e in self.events() if "event" in e))

    def test_the_checker_rejects_a_bad_summary(self):
        good = {"schema": "grun.run/1", "app": "a", "entry": 1, "state": "done", "errorCode": None,
                "lockWaitMs": 0, "memoryWaitMs": 0, "runMs": 5}
        self.assertEqual(problems(good), [])
        self.assertNotEqual(problems(dict(good, schema="grun.run/0")), [])
        self.assertNotEqual(problems(dict(good, state="running")), [])
        self.assertNotEqual(problems(dict(good, runMs=-1)), [])
        self.assertNotEqual(problems(dict(good, runMs=1.5)), [])
        del good["runMs"]
        self.assertIn("missing runMs", " ".join(problems(good)))


if __name__ == "__main__":
    unittest.main()
