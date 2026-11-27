import json
import unittest
from pathlib import Path

from grun import errors, i18n

LOCALES = Path(__file__).resolve().parent.parent / "grun" / "locales"
NEW_CODES = ("queue.invalid_transition", "queue.orphaned", "net.non_local_host")  # D-14


def load(lang):
    with open(LOCALES / (lang + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


class ErrorTests(unittest.TestCase):
    def test_code_params_and_str(self):
        err = errors.GrunError("limit.memory", free=1, min=2)
        self.assertEqual((err.code, err.params), ("limit.memory", {"free": 1, "min": 2}))
        self.assertEqual(str(err), "limit.memory {'free': 1, 'min': 2}")

    def test_path_error_is_a_grun_error(self):
        self.assertIsInstance(errors.PathError("path.dotdot"), errors.GrunError)

    def test_message_translated(self):
        err = errors.PathError("path.dotdot")
        self.assertIn("..", err.message("es"))
        self.assertNotEqual(err.message("es"), err.message("en"))

    def test_d14_new_codes_have_text_in_en_and_es(self):
        params = {"id": 7, "from_state": "done", "to_state": "running", "count": 2, "host": "example.com"}
        for lang in ("en", "es"):
            data = load(lang)
            for code in NEW_CODES:
                with self.subTest(lang=lang, code=code):
                    self.assertIn("error." + code, data)
                    text = errors.GrunError(code, **params).message(lang)
                    self.assertNotIn("error.", text)
        self.assertIn("example.com", errors.GrunError("net.non_local_host", host="example.com").message("en"))
        self.assertIn("7", errors.GrunError("queue.orphaned", id=7, count=2).message("es"))

    def test_kept_gvoice_codes_have_text(self):
        kept = ("path.type", "path.empty", "path.nul", "path.control", "path.backslash", "path.absolute",
                "path.tilde", "path.dotdot", "path.outside", "path.unresolvable", "limit.memory",
                "engine.failed", "engine.low_memory", "engine.timeout", "queue.corrupt", "queue.unknown",
                "queue.not_cancellable", "queue.not_running", "queue.bad_state", "worker.already_running",
                "worker.unexpected", "machine_lock.unavailable")
        for lang in ("en", "es"):
            for code in kept:
                self.assertIn("error." + code, load(lang), (lang, code))

    def test_missing_code_renders_the_key(self):
        self.assertEqual(errors.GrunError("no.such").message("en"), "error.no.such")


if __name__ == "__main__":
    unittest.main()
