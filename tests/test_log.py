import json
import tempfile
import unittest
from pathlib import Path

from grun import log

MODEL = "gen_ai.request.model"


def line(duration, model="m1", **extra):
    d = {MODEL: model, "app.duration_ms": duration}
    d.update(extra)
    return d


class LogTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "sub" / "log.jsonl"

    def put(self, *records):
        for r in records:
            log.append(self.path, r)

    def test_now_format(self):
        self.assertRegex(log.now(), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_append_writes_jsonl(self):
        self.path.parent.mkdir()
        self.put({"b": 1, "a": "é"}, {"c": 2})
        self.assertEqual(self.path.read_text(encoding="utf-8"), '{"a": "é", "b": 1}\n{"c": 2}\n')

    def test_lines_missing_file_is_empty(self):
        self.assertEqual(list(log.lines(self.path)), [])

    def test_estimate_none(self):
        self.assertIsNone(log.estimate(self.path, **{MODEL: "m1"}))

    def test_estimate_median_odd_even(self):
        self.path.parent.mkdir()
        self.put(line(10), line(30), line(20))
        self.assertEqual(log.estimate(self.path, **{MODEL: "m1"}), 20)
        self.put(line(40))
        self.assertEqual(log.estimate(self.path, **{MODEL: "m1"}), 25)

    def test_estimate_filters(self):
        self.path.parent.mkdir()
        self.put(line(10), line(1000, model="m2"), line(2000, **{"app.error": "boom"}), line(5, device="cpu"))
        self.assertEqual(log.estimate(self.path, **{MODEL: "m1"}), 7.5)
        self.assertEqual(log.estimate(self.path, **{MODEL: "m1", "device": "cpu"}), 5)
        self.assertEqual(log.estimate(self.path, **{MODEL: "m2"}), 1000)

    def test_estimate_skips_malformed(self):
        self.path.parent.mkdir()
        self.put(line(10), line("x"), line(True), {MODEL: "m1"})
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write("not json\n[1]\n")
        self.assertEqual(log.estimate(self.path, **{MODEL: "m1"}), 10)
        self.assertEqual(len(list(log.lines(self.path))), 4)


if __name__ == "__main__":
    unittest.main()
