"""Invariante 6 (parcial): la ruta del `gpu.lock` por entorno, la misma que da `gvoice/paths.py`.

Copiado de gvoice@8a17618 (tests/test_paths.py); adaptado: tabla de entornos de `state_dir`/`machine_lock_path`,
`GALIVELOP_STATE_HOME` con alias `GVOICE_STATE_HOME`, rutas de datos parametrizadas por aplicación."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from grun import paths
from grun.errors import GrunError, PathError

SANDBOX = "/h/.var/app/com.visualstudio.code"
VARS = ("GALIVELOP_STATE_HOME", "GVOICE_STATE_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "FLATPAK_ID",
        "GALIVELOP_TEST_DATA_HOME")

# (nombre, entorno, ruta de gpu.lock). Las filas sin variable nueva se verificaron a mano contra la
# `machine_lock_path()` de gvoice@8a17618 con el mismo entorno (GVOICE_STATE_HOME incluida); las de
# GALIVELOP_STATE_HOME las fija D-1 (gvoice no la conoce).
LOCK_TABLE = [
    ("sin nada", {}, "/h/.local/state/galivelop/gpu.lock"),
    ("XDG_STATE_HOME", {"XDG_STATE_HOME": "/x"}, "/x/galivelop/gpu.lock"),
    ("XDG relativo se ignora", {"XDG_STATE_HOME": "rel"}, "/h/.local/state/galivelop/gpu.lock"),
    ("flatpak, XDG en el sandbox",
     {"FLATPAK_ID": "com.visualstudio.code", "XDG_STATE_HOME": SANDBOX + "/.local/state"},
     "/h/.local/state/galivelop/gpu.lock"),
    ("flatpak, XDG fuera del sandbox",
     {"FLATPAK_ID": "com.visualstudio.code", "XDG_STATE_HOME": "/y"}, "/y/galivelop/gpu.lock"),
    ("sin flatpak, XDG con forma de sandbox se respeta",
     {"XDG_STATE_HOME": "/h/.var/app/x/.local/state"}, "/h/.var/app/x/.local/state/galivelop/gpu.lock"),
    ("GVOICE_STATE_HOME", {"GVOICE_STATE_HOME": "/v", "XDG_STATE_HOME": "/x"}, "/v/gpu.lock"),
    ("GALIVELOP_STATE_HOME", {"GALIVELOP_STATE_HOME": "/g", "XDG_STATE_HOME": "/x"}, "/g/gpu.lock"),
    ("las dos: gana la nueva",
     {"GALIVELOP_STATE_HOME": "/g", "GVOICE_STATE_HOME": "/v"}, "/g/gpu.lock"),
    ("flatpak no anula la explícita",
     {"FLATPAK_ID": "com.visualstudio.code", "GALIVELOP_STATE_HOME": "/g"}, "/g/gpu.lock"),
    ("GALIVELOP_STATE_HOME vacía cae a la alias",
     {"GALIVELOP_STATE_HOME": "", "GVOICE_STATE_HOME": "/v"}, "/v/gpu.lock"),
]


def env(**kw):
    base = {k: "" for k in VARS}
    base.update(HOME="/h", **kw)
    return mock.patch.dict(os.environ, base)


class MachineLockPathTable(unittest.TestCase):
    def test_table(self):
        for name, setting, expected in LOCK_TABLE:
            with self.subTest(name):
                with env(**setting):
                    self.assertEqual(paths.machine_lock_path(), Path(expected))
                    self.assertEqual(paths.state_dir(), Path(expected).parent)


class DataDirTests(unittest.TestCase):
    def test_explicit_wins(self):
        with env(GALIVELOP_TEST_DATA_HOME="/a", XDG_DATA_HOME="/y"):
            self.assertEqual(paths.data_dir("galivelop-test"), Path("/a"))

    def test_explicit_variable_name_is_given(self):
        with env(XDG_DATA_HOME="/y"), mock.patch.dict(os.environ, {"OTRA_DATA": "/o"}):
            self.assertEqual(paths.data_dir("galivelop-test", "OTRA_DATA"), Path("/o"))

    def test_xdg_and_home_fallback_per_app(self):
        with env(XDG_DATA_HOME="/y"):
            self.assertEqual(paths.data_dir("galivelop-test"), Path("/y/galivelop-test"))
        with env(XDG_DATA_HOME="rel"):
            self.assertEqual(paths.data_dir("galivelop-test"), Path("/h/.local/share/galivelop-test"))

    def test_sandbox_xdg_ignored_inside_flatpak_only(self):
        with env(FLATPAK_ID="com.visualstudio.code", XDG_DATA_HOME=SANDBOX + "/data"):
            self.assertEqual(paths.data_dir("galivelop-test"), Path("/h/.local/share/galivelop-test"))
        with env(XDG_DATA_HOME=SANDBOX + "/data"):
            self.assertEqual(paths.data_dir("galivelop-test"), Path(SANDBOX + "/data/galivelop-test"))

    def test_project_data_dir(self):
        with env(GALIVELOP_TEST_DATA_HOME="/d"):
            self.assertEqual(paths.project_data_dir("galivelop-test", "my-game"), Path("/d/projects/my-game"))
            for bad in ("..", ".", "a/b", "A", "", None, "ok\n"):
                with self.subTest(bad=bad):
                    with self.assertRaises(GrunError) as cm:
                        paths.project_data_dir("galivelop-test", bad)
                    self.assertEqual(cm.exception.code, "project.bad_name")
                    self.assertEqual(cm.exception.params["project"], str(bad))

    def test_project_data_dir_custom_code(self):
        with env(GALIVELOP_TEST_DATA_HOME="/d"):
            with self.assertRaises(GrunError) as cm:
                paths.project_data_dir("galivelop-test", "..", "log.bad_project")
            self.assertEqual(cm.exception.code, "log.bad_project")


class InsideTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.root = self.tmp / "root"
        self.root.mkdir()
        self.outside = self.tmp / "outside"
        self.outside.mkdir()

    def reason(self, rel, root=None):
        with self.assertRaises(PathError) as cm:
            paths.inside(root or self.root, rel)
        return cm.exception.code

    def test_rejections_with_reason(self):
        cases = [
            ("/etc/passwd", "path.absolute"), ("~", "path.tilde"), ("~/x", "path.tilde"),
            ("..", "path.dotdot"), ("../x", "path.dotdot"), ("a/../x", "path.dotdot"), ("a/..", "path.dotdot"),
            ("a\\b", "path.backslash"), ("a\x00b", "path.nul"), ("a\nb", "path.control"),
            ("a\tb", "path.control"), ("a\x7fb", "path.control"), ("", "path.empty"), (None, "path.type"),
        ]
        for rel, code in cases:
            with self.subTest(rel=rel):
                self.assertEqual(self.reason(rel), code)

    def test_dots_inside_names_are_fine(self):
        self.assertEqual(paths.inside(self.root, "a..b/c"), self.root / "a..b" / "c")

    def test_nonexistent_target(self):
        self.assertEqual(paths.inside(self.root, "new/dir/x.wav"), self.root / "new/dir/x.wav")

    def test_symlink_outside_rejected(self):
        os.symlink(self.outside, self.root / "link")
        self.assertEqual(self.reason("link/x.wav"), "path.outside")
        self.assertEqual(self.reason("link"), "path.outside")

    def test_symlink_to_file_outside_rejected(self):
        (self.outside / "f").write_text("x")
        os.symlink(self.outside / "f", self.root / "flink")
        self.assertEqual(self.reason("flink"), "path.outside")

    def test_symlink_inside_ok(self):
        (self.root / "real").mkdir()
        os.symlink(self.root / "real", self.root / "alias")
        self.assertEqual(paths.inside(self.root, "alias/x.wav"), self.root / "real" / "x.wav")

    def test_root_is_symlink(self):
        link = self.tmp / "rootlink"
        os.symlink(self.root, link)
        self.assertEqual(paths.inside(link, "a/x.wav"), self.root / "a" / "x.wav")
        os.symlink(self.outside, self.root / "out")
        self.assertEqual(self.reason("out/x", root=link), "path.outside")

    def test_symlink_loop(self):
        os.symlink(self.root / "b", self.root / "a")
        os.symlink(self.root / "a", self.root / "b")
        try:
            target = paths.inside(self.root, "a/x")
        except PathError as exc:
            self.assertEqual(exc.code, "path.unresolvable")
        else:
            self.assertIn(self.root, target.parents)

    def test_root_itself(self):
        self.assertEqual(paths.inside(self.root, "."), self.root)


if __name__ == "__main__":
    unittest.main()
