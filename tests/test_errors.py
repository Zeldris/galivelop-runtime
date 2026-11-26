"""Errores con código estable y parámetros.

Copiado de gvoice@8a17618 (parte de tests/test_paths.py y test_limits.py); adaptado a `GrunError`."""
import unittest

from grun import errors


class ErrorTests(unittest.TestCase):
    def test_code_and_params(self):
        err = errors.GrunError("queue.unknown", id=7)
        self.assertEqual((err.code, err.params), ("queue.unknown", {"id": 7}))
        self.assertEqual(str(err), "queue.unknown {'id': 7}")

    def test_path_error_is_a_grun_error(self):
        self.assertTrue(issubclass(errors.PathError, errors.GrunError))

    def test_message_is_translated_and_differs_by_language(self):
        err = errors.PathError("path.dotdot")
        self.assertIn("..", err.message("es"))
        self.assertNotEqual(err.message("es"), err.message("en"))

    def test_new_codes_render_with_their_params(self):
        cases = {
            "queue.invalid_transition": {"id": 3, "from": "done", "to": "running"},
            "queue.orphaned": {"id": 3},
            "net.non_local_host": {"host": "example.org"},
        }
        for code, params in cases.items():
            for lang in ("es", "en"):
                with self.subTest(code=code, lang=lang):
                    text = errors.GrunError(code, **params).message(lang)
                    self.assertNotIn("error.", text)
                    self.assertIn(str(next(iter(params.values()))), text)


if __name__ == "__main__":
    unittest.main()
