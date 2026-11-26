"""Textos es/en: mismas claves que los códigos de `errors.py`.

Copiado de gvoice@8a17618 (tests/test_i18n.py); adaptado: `GALIVELOP_LANG`, sin textos del validador de esquemas,
y la comparación de claves con `errors.CODES`."""
import json
import os
import re
import string
import unittest
from pathlib import Path
from unittest import mock

from grun import errors, i18n

PACKAGE = Path(__file__).resolve().parent.parent / "grun"
LOCALES = PACKAGE / "locales"
NEW_CODES = ("queue.invalid_transition", "queue.orphaned", "net.non_local_host")  # D-14


def load(lang):
    with open(LOCALES / (lang + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def placeholders(text):
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


class LocaleTests(unittest.TestCase):
    def test_same_keys_and_placeholders(self):
        es, en = load("es"), load("en")
        self.assertEqual(set(es), set(en))
        for key in es:
            self.assertEqual(placeholders(es[key]), placeholders(en[key]), key)

    def test_locale_keys_are_exactly_the_error_codes(self):
        expected = {"error." + code for code in errors.CODES}
        for lang in ("es", "en"):
            self.assertEqual(set(load(lang)), expected, lang)

    def test_the_new_codes_are_declared_with_text(self):
        for code in NEW_CODES:
            self.assertIn(code, errors.CODES)
            for lang in ("es", "en"):
                self.assertTrue(load(lang)["error." + code].strip(), (lang, code))

    def test_the_gvoice_codes_are_kept_with_their_name(self):
        kept = {"path.type", "path.empty", "path.nul", "path.control", "path.backslash", "path.absolute",
                "path.tilde", "path.dotdot", "path.outside", "path.unresolvable", "limit.memory", "limit.model",
                "machine_lock.unavailable", "log.bad_project", "project.bad_name", "queue.corrupt",
                "queue.unknown", "queue.not_cancellable", "queue.not_running", "queue.bad_state",
                "worker.already_running", "worker.unexpected"}
        self.assertLessEqual(kept, set(errors.CODES))

    def test_no_voice_codes(self):
        for code in errors.CODES:
            self.assertFalse(code.startswith(("engine.", "order.", "sheet.", "models.", "cli.", "api.")), code)

    def test_codes_have_no_duplicates(self):
        self.assertEqual(len(errors.CODES), len(set(errors.CODES)))

    def test_every_code_used_in_the_source_is_declared(self):
        used = set()
        for path in PACKAGE.glob("*.py"):
            used |= set(re.findall(r"""(?:Error|project_data_dir\([^)]*,)\(?\s*["']([a-z_]+\.[a-z_]+)["']""",
                                   path.read_text(encoding="utf-8")))
        self.assertTrue(used)
        self.assertLessEqual(used, set(errors.CODES))

    def test_all_messages_render_in_both_languages(self):
        params = {k: "X" for k in ("path", "reason", "free", "min", "model", "use", "allowed", "id", "state",
                                   "states", "message", "project", "host", "from", "to")}
        for lang in ("es", "en"):
            for code in errors.CODES:
                self.assertNotIn("{", i18n.t("error." + code, lang, **params), (lang, code))


class FallbackTests(unittest.TestCase):
    def test_language_texts(self):
        self.assertIn("vacía", i18n.t("error.path.empty", "es"))
        self.assertIn("empty", i18n.t("error.path.empty", "en"))

    def test_unknown_language_falls_back_to_en(self):
        self.assertIn("empty", i18n.t("error.path.empty", "xx"))

    def test_unknown_key_returns_key(self):
        self.assertEqual(i18n.t("no.such.key", "es"), "no.such.key")

    def test_key_missing_in_lang_falls_back_to_en(self):
        with mock.patch.dict(i18n._cache, {"es": {}, "en": {"k": "english {a}"}}):
            self.assertEqual(i18n.t("k", "es", a=1), "english 1")


class DefaultLangTests(unittest.TestCase):
    def check(self, env, expected):
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(i18n.default_lang(), expected)

    def test_explicit_wins(self):
        self.check({"GALIVELOP_LANG": "en", "LANG": "es_ES.UTF-8"}, "en")
        self.check({"GALIVELOP_LANG": "es", "LANG": "en_US.UTF-8"}, "es")

    def test_from_lang(self):
        self.check({"LANG": "es_ES.UTF-8"}, "es")
        self.check({"LANG": "en_US.UTF-8"}, "en")

    def test_full_precedence_order(self):
        env = {"GALIVELOP_LANG": "en", "LC_ALL": "es", "LC_MESSAGES": "es", "LANG": "es"}
        self.check(env, "en")
        del env["GALIVELOP_LANG"]
        self.check(env, "es")
        self.check({"LC_ALL": "en_US", "LC_MESSAGES": "es_ES", "LANG": "es_ES"}, "en")
        self.check({"LC_MESSAGES": "es_ES", "LANG": "en_US"}, "es")
        self.check({"LC_ALL": "", "LC_MESSAGES": "", "LANG": "es_ES"}, "es")

    def test_explicit_is_normalised_like_lang(self):
        self.check({"GALIVELOP_LANG": "es_ES.UTF-8"}, "es")
        self.check({"GALIVELOP_LANG": "EN_us"}, "en")
        self.check({"GALIVELOP_LANG": "es@euro", "LANG": "en_US"}, "es")

    def test_explicit_only_accepts_existing_locales(self):
        for bad in ("../..", "../locales/es", "xx", "fr_FR.UTF-8", "/etc/passwd", "es/../en"):
            self.check({"GALIVELOP_LANG": bad, "LANG": "es_ES.UTF-8"}, i18n.FALLBACK)

    def test_lang_without_locale_falls_back(self):
        self.check({"LANG": "fr_FR.UTF-8"}, i18n.FALLBACK)
        self.check({"LANG": "C"}, i18n.FALLBACK)

    def test_t_never_reads_outside_locales(self):
        i18n.t("no.such.key", "es")
        i18n.t("no.such.key", "en")
        with mock.patch("builtins.open", side_effect=AssertionError("opened a file")):
            self.assertEqual(i18n.t("no.such.key", "../../etc/passwd"), "no.such.key")
        self.assertNotIn("../../etc/passwd", i18n._cache)

    def test_default_en(self):
        self.check({}, "en")


if __name__ == "__main__":
    unittest.main()
