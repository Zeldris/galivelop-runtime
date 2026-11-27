import unittest

from grun.engine import Cancelled, Engine, EngineError, EngineTimeout, Job


class EngineTests(unittest.TestCase):
    def test_job_holds_entry_and_machine(self):
        job = Job(entry={"id": 1, "kind": "line"}, machine={"timeoutS": 5})
        self.assertEqual((job.entry["kind"], job.machine["timeoutS"]), ("line", 5))

    def test_engine_error_message_code_and_params(self):
        plain = EngineError("boom")
        self.assertEqual((plain.message, plain.code, plain.params, str(plain)), ("boom", None, {}, "boom"))
        coded = EngineError("x", code="engine.low_memory", free=10, min=20)
        self.assertEqual((coded.code, coded.params), ("engine.low_memory", {"free": 10, "min": 20}))

    def test_hierarchy(self):
        self.assertTrue(issubclass(EngineTimeout, EngineError))
        self.assertFalse(issubclass(Cancelled, EngineError))
        self.assertTrue(issubclass(Cancelled, Exception))

    def test_engine_protocol_has_run(self):
        self.assertTrue(callable(Engine.run))


if __name__ == "__main__":
    unittest.main()
