import json
import os
import string
import unittest
from pathlib import Path
from unittest import mock

from grun import i18n

LOCALES = Path(__file__).resolve().parent.parent / "grun" / "locales"


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

    def test_no_application_specific_text(self):
        for lang in ("es", "en"):
            for key, text in load(lang).items():
                self.assertNotIn("gvoice", text.lower(), key)


class FallbackTests(unittest.TestCase):
    def test_language_texts(self):
        self.assertIn("absolute", i18n.t("error.path.absolute", "en"))
        self.assertIn("absoluta", i18n.t("error.path.absolute", "es"))

    def test_unknown_language_falls_back_to_en(self):
        self.assertIn("absolute", i18n.t("error.path.absolute", "xx"))

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

    def test_new_variable_beats_alias(self):
        self.check({"GALIVELOP_LANG": "es", "GVOICE_LANG": "en"}, "es")
        self.check({"GVOICE_LANG": "es", "LANG": "en_US"}, "es")

    def test_from_lang_and_lc(self):
        self.check({"LANG": "es_ES.UTF-8"}, "es")
        self.check({"LC_ALL": "es_ES.UTF-8", "LANG": "en_US.UTF-8"}, "es")
        self.check({"LC_ALL": "en_US", "LC_MESSAGES": "es_ES", "LANG": "es_ES"}, "en")
        self.check({"LC_MESSAGES": "es_ES", "LANG": "en_US"}, "es")
        self.check({"LC_ALL": "", "LC_MESSAGES": "", "LANG": "es_ES"}, "es")

    def test_explicit_is_normalised(self):
        self.check({"GALIVELOP_LANG": "es_ES.UTF-8"}, "es")
        self.check({"GALIVELOP_LANG": "EN_us"}, "en")
        self.check({"GALIVELOP_LANG": "es@euro", "LANG": "en_US"}, "es")

    def test_only_existing_locales(self):
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


class FormatTests(unittest.TestCase):
    def test_missing_parameter_keeps_the_placeholder(self):
        self.assertEqual(i18n.t("error.path.outside", "en"), load("en")["error.path.outside"])
        self.assertIn("{path}", i18n.t("error.path.outside", "es"))
        self.assertIn('"x/y"', i18n.t("error.path.outside", "en", path="x/y"))


if __name__ == "__main__":
    unittest.main()
