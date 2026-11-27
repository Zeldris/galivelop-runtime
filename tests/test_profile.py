import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from grun import profile
from grun.errors import GrunError

GOOD = {"timeoutS": 60, "minFreeMemoryMb": 100, "watchMemoryMb": 0, "engine": {"ollama": "abort"}, "extra": [1]}


class ProfileBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.presets = self.tmp / "presets"
        self.presets.mkdir()
        env = mock.patch.dict(os.environ, {"MY_PROFILE": ""})
        env.start()
        self.addCleanup(env.stop)

    def write(self, path, data):
        Path(path).write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return str(path)

    def preset(self, name, **over):
        self.write(self.presets / (name + ".json"), dict(GOOD, name=name, **over))

    def load(self, ref=None, **kw):
        kw.setdefault("presets", self.presets)
        kw.setdefault("env_var", "MY_PROFILE")
        return profile.load_profile(ref, **kw)

    def error(self, *args, **kw):
        with self.assertRaises(GrunError) as cm:
            self.load(*args, **kw)
        return cm.exception


class ResolutionTests(ProfileBase):
    def test_default_name(self):
        self.preset("steam-deck")
        self.assertEqual(self.load()["name"], "steam-deck")

    def test_order_ref_env_config_default(self):
        for name in ("steam-deck", "from-config", "from-env", "from-ref"):
            self.preset(name)
        config = self.write(self.tmp / "config.json", {"machineProfile": "from-config"})
        self.assertEqual(self.load(config_path=config)["name"], "from-config")
        with mock.patch.dict(os.environ, {"MY_PROFILE": "from-env"}):
            self.assertEqual(self.load(config_path=config)["name"], "from-env")
            self.assertEqual(self.load("from-ref", config_path=config)["name"], "from-ref")

    def test_bad_or_missing_config_is_no_setting(self):
        self.preset("steam-deck")
        for text in ("{", "[]", '{"machineProfile": 3}'):
            config = self.write(self.tmp / "config.json", text)
            self.assertEqual(self.load(config_path=config)["name"], "steam-deck")
        self.assertEqual(self.load(config_path=self.tmp / "none.json")["name"], "steam-deck")

    def test_custom_default(self):
        self.preset("mine")
        self.assertEqual(self.load(default="mine")["name"], "mine")

    def test_path_by_slash_or_json_suffix(self):
        path = self.write(self.tmp / "m.json", GOOD)
        self.assertEqual(self.load(path)["timeoutS"], 60)
        cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, cwd)
        self.assertEqual(self.load("m.json")["timeoutS"], 60)

    def test_unknown_fields_are_kept(self):
        self.preset("steam-deck")
        self.assertEqual(self.load()["extra"], [1])


class ErrorTests(ProfileBase):
    def test_bad_names(self):
        for name in ("Steam", "-x", "a b", "a_b", ".x", "steam-deck\n"):
            self.assertEqual(self.error(name).code, "machine.bad_name", name)
        self.assertEqual(self.error("UPPER").params["name"], "UPPER")

    def test_missing(self):
        err = self.error("nothing")
        self.assertEqual(err.code, "machine.missing")
        self.assertTrue(err.params["path"].endswith("nothing.json"))
        self.assertEqual(self.error(str(self.tmp / "no.json")).code, "machine.missing")

    def test_too_deep_json_is_unreadable_or_no_setting(self):
        self.preset("steam-deck")
        deep = "[" * 100000
        path = self.tmp / "deep.json"
        self.write(path, deep)
        err = self.error(str(path))
        self.assertEqual(err.code, "machine.unreadable")
        config = self.write(self.tmp / "config.json", deep)
        self.assertEqual(self.load(config_path=config)["name"], "steam-deck")

    def test_unreadable(self):
        for text in ("{not json", "", b"\xff\xfe"):
            path = self.tmp / "bad.json"
            if isinstance(text, bytes):
                path.write_bytes(text)
            else:
                self.write(path, text)
            self.assertEqual(self.error(str(path)).code, "machine.unreadable", text)
        self.assertEqual(self.error(str(self.tmp) + "/").code, "machine.unreadable")  # a directory

    def fields(self, **over):
        path = self.write(self.tmp / "p.json", dict({"timeoutS": 5}, **over))
        err = self.error(path)
        self.assertEqual(err.code, "machine.invalid")
        return sorted(e["path"] for e in err.params["errors"]), err

    def test_invalid_fields(self):
        cases = [
            ({"timeoutS": 0}, ["timeoutS"]), ({"timeoutS": "5"}, ["timeoutS"]), ({"timeoutS": True}, ["timeoutS"]),
            ({"timeoutS": 1.5}, ["timeoutS"]), ({"minFreeMemoryMb": -1}, ["minFreeMemoryMb"]),
            ({"watchMemoryMb": "x"}, ["watchMemoryMb"]), ({"minFreeMemoryMb": False}, ["minFreeMemoryMb"]),
            ({"engine": []}, ["engine"]), ({"engine": {"ollama": "kill"}}, ["engine.ollama"]),
            ({"engine": {"ollamaUrl": 3}}, ["engine.ollamaUrl"]),
            ({"timeoutS": 0, "watchMemoryMb": -5}, ["timeoutS", "watchMemoryMb"]),
        ]
        for over, expected in cases:
            with self.subTest(over=over):
                self.assertEqual(self.fields(**over)[0], expected)

    def test_missing_timeout_and_non_object(self):
        path = self.write(self.tmp / "p.json", {"minFreeMemoryMb": 1})
        self.assertEqual(self.error(path).params["errors"][0]["path"], "timeoutS")
        path = self.write(self.tmp / "q.json", "[1]")
        err = self.error(path)
        self.assertEqual((err.code, err.params["errors"][0]["code"]), ("machine.invalid", "machine.field"))

    def test_zero_is_allowed_for_memory(self):
        path = self.write(self.tmp / "p.json", {"timeoutS": 1, "minFreeMemoryMb": 0, "watchMemoryMb": 0,
                                                "engine": {"ollama": "ignore", "ollamaUrl": "http://x"}})
        self.assertEqual(self.load(path)["timeoutS"], 1)

    def test_validate_runs_after_and_may_raise(self):
        self.preset("steam-deck")
        seen = []
        self.load(validate=seen.append)
        self.assertEqual(seen[0]["name"], "steam-deck")

        def strict(p):
            raise GrunError("app.schema", field="x")

        self.assertEqual(self.error(validate=strict).code, "app.schema")

    def test_validate_not_called_when_core_fields_fail(self):
        path = self.write(self.tmp / "p.json", {"timeoutS": 0})
        seen = []
        self.assertEqual(self.error(path, validate=seen.append).code, "machine.invalid")
        self.assertEqual(seen, [])


if __name__ == "__main__":
    unittest.main()
