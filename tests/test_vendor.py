import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from grun import __version__, vendor
from grun.errors import GrunError

ROOT = Path(__file__).resolve().parent.parent


def codes(problems):
    return sorted((p["code"], p["params"].get("file")) for p in problems)


class VendorTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dest = Path(self._tmp.name)

    def export(self):
        return vendor.export(self.dest, source="test@abc")

    def test_export_copies_the_package_and_writes_the_manifest(self):
        manifest = self.export()
        target = self.dest / "grun"
        self.assertEqual(manifest["version"], __version__)
        self.assertEqual(manifest["source"], "test@abc")
        self.assertEqual(manifest["files"], vendor.collect(target))
        self.assertEqual(manifest["files"], vendor.collect(vendor.PACKAGE))
        self.assertIn("vendor.py", manifest["files"])
        self.assertIn("locales/en.json", manifest["files"])
        self.assertEqual(json.loads((target / "VENDOR.json").read_text()), manifest)
        self.assertEqual(manifest["fingerprint"], vendor.fingerprint(manifest["files"]))
        self.assertEqual(vendor.verify(target), [])

    def test_the_copy_leaves_out_caches_and_the_manifest_is_not_fingerprinted(self):
        self.export()
        (self.dest / "grun" / "__pycache__").mkdir()
        (self.dest / "grun" / "__pycache__" / "x.pyc").write_bytes(b"x")
        self.assertEqual(vendor.verify(self.dest / "grun"), [])
        self.assertFalse(any("__pycache__" in n or n == "VENDOR.json" for n in vendor.collect(self.dest / "grun")))

    def test_the_fingerprint_is_stable_and_depends_on_names_and_contents(self):
        a = {"a.py": "1" * 64, "b.py": "2" * 64}
        self.assertEqual(vendor.fingerprint(a), vendor.fingerprint(dict(reversed(list(a.items())))))
        self.assertNotEqual(vendor.fingerprint(a), vendor.fingerprint({"a.py": "1" * 64, "c.py": "2" * 64}))
        self.assertNotEqual(vendor.fingerprint(a), vendor.fingerprint({"a.py": "2" * 64, "b.py": "1" * 64}))

    def test_a_changed_missing_and_extra_file_are_reported_by_name(self):
        self.export()
        t = self.dest / "grun"
        (t / "paths.py").write_text("# tampered\n")
        (t / "errors.py").unlink()
        (t / "new.py").write_text("x = 1\n")
        self.assertEqual(codes(vendor.verify(t)), [("vendor.changed", "paths.py"), ("vendor.extra", "new.py"),
                                                   ("vendor.missing", "errors.py")])

    def test_a_manifest_edited_to_hide_a_change_fails_its_own_fingerprint(self):
        self.export()
        t = self.dest / "grun"
        (t / "paths.py").write_text("# tampered\n")
        manifest = json.loads((t / "VENDOR.json").read_text())
        manifest["files"]["paths.py"] = vendor.collect(t)["paths.py"]
        (t / "VENDOR.json").write_text(json.dumps(manifest))
        self.assertEqual(codes(vendor.verify(t)), [("vendor.fingerprint", None)])

    def test_a_pinned_fingerprint_must_match_the_copy(self):
        manifest = self.export()
        t = self.dest / "grun"
        self.assertEqual(vendor.verify(t, pinned=manifest["fingerprint"]), [])
        found = vendor.verify(t, pinned="0" * 64)
        self.assertEqual(codes(found), [("vendor.pinned", None)])
        self.assertEqual(found[0]["params"], {"expected": "0" * 64, "found": manifest["fingerprint"]})

    def test_a_missing_or_broken_manifest_is_one_problem_and_nothing_else(self):
        t = self.dest / "grun"
        t.mkdir()
        self.assertEqual(codes(vendor.verify(t)), [("vendor.no_manifest", None)])
        for bad in ("not json", "[]", json.dumps({"schema": "other/0", "files": {}}),
                    json.dumps({"schema": vendor.SCHEMA, "files": {"a.py": 3}})):
            (t / "VENDOR.json").write_text(bad)
            self.assertEqual(codes(vendor.verify(t)), [("vendor.bad_manifest", None)], bad)

    def test_exporting_again_replaces_a_vendored_copy(self):
        self.export()
        stale = self.dest / "grun" / "stale.py"
        stale.write_text("x = 1\n")
        self.export()
        self.assertFalse(stale.exists())
        self.assertEqual(vendor.verify(self.dest / "grun"), [])

    def test_a_folder_that_is_not_a_vendored_copy_is_never_touched(self):
        target = self.dest / "grun"
        target.mkdir()
        keep = target / "mine.py"
        keep.write_text("keep\n")
        with self.assertRaises(GrunError) as cm:
            self.export()
        self.assertEqual(cm.exception.code, "vendor.not_vendored")
        self.assertEqual(cm.exception.params, {"path": str(target)})
        self.assertEqual(keep.read_text(), "keep\n")
        self.assertEqual([p.name for p in target.iterdir()], ["mine.py"])

    def test_it_never_deletes_the_package_that_is_running(self):
        # A copy exported into `self.dest` is vendored (has a manifest) and, run from there, is its own source.
        self.export()
        copy = self.dest / "grun"
        before = vendor.collect(copy)
        code = ("import sys; from grun import vendor; "
                "from grun.errors import GrunError\n"
                "try: vendor.export(%r)\nexcept GrunError as e: print(e.code); sys.exit(0)\n"
                "sys.exit(1)" % str(self.dest))
        out = subprocess.run([sys.executable, "-c", code], cwd=self.dest, capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, "vendor.is_source"), out.stderr)
        self.assertEqual(vendor.collect(copy), before)
        self.assertEqual(vendor.verify(copy), [])

    def test_the_vendored_copy_runs_on_its_own(self):
        self.export()
        out = subprocess.run([sys.executable, "-c", "import grun, grun.vendor; print(grun.__version__)"],
                             cwd=self.dest, capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, __version__), out.stderr)


class VendorCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dest = Path(self._tmp.name)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = vendor.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_dest_then_verify_round_trip_with_json(self):
        code, out, _ = self.run_cli("--dest", str(self.dest), "--json")
        manifest = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(manifest["schema"], vendor.SCHEMA)
        code, out, _ = self.run_cli("--verify", str(self.dest / "grun"), "--pinned", manifest["fingerprint"])
        self.assertEqual((code, out.strip()), (0, "ok"))

    def test_verify_exits_1_and_names_the_problem(self):
        self.run_cli("--dest", str(self.dest))
        (self.dest / "grun" / "paths.py").write_text("# tampered\n")
        code, out, _ = self.run_cli("--verify", str(self.dest / "grun"))
        self.assertEqual(code, 1)
        self.assertIn('vendor.changed {"file": "paths.py"}', out)

    def test_dest_over_a_foreign_folder_exits_1_with_the_reason(self):
        (self.dest / "grun").mkdir()
        code, _, err = self.run_cli("--dest", str(self.dest))
        self.assertEqual(code, 1)
        self.assertIn("not a vendored grun copy", err)

    def test_dest_that_is_a_file_exits_1_with_a_message_not_a_traceback(self):
        f = self.dest / "afile"
        f.write_text("x")
        code, _, err = self.run_cli("--dest", str(f))
        self.assertEqual(code, 1)
        self.assertIn("grun vendor:", err)

    def test_bad_usage_exits_2(self):
        self.assertEqual(self.run_cli()[0], 2)
        self.assertEqual(self.run_cli("--dest", "a", "--verify", "b")[0], 2)
        code, _, err = self.run_cli("--dest", str(self.dest), "--pinned", "x")
        self.assertEqual((code, "--pinned needs --verify" in err), (2, True))

    def test_the_module_dispatches_vendor_and_still_runs_doctor(self):
        run = lambda *a: subprocess.run([sys.executable, "-m", "grun", *a], cwd=ROOT, capture_output=True, text=True)
        out = run("vendor", "--dest", str(self.dest))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(run("vendor").returncode, 2)
        self.assertEqual(run("doctor").returncode, 2)


if __name__ == "__main__":
    unittest.main()
