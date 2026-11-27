import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from grun import paths
from grun.errors import GrunError, PathError

STATE_VARS = ("GALIVELOP_STATE_HOME", "GVOICE_STATE_HOME", "XDG_STATE_HOME", "FLATPAK_ID")
APP = ("galivelop-voice", "GVOICE")


def env(**kw):
    base = {k: "" for k in ("GVOICE_CONFIG_HOME", "GVOICE_DATA_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME") + STATE_VARS}
    base.update(HOME="/h", **kw)
    return mock.patch.dict(os.environ, base)


class FolderTests(unittest.TestCase):
    def test_explicit_wins(self):
        with env(GVOICE_CONFIG_HOME="/a", XDG_CONFIG_HOME="/x", GVOICE_DATA_HOME="/b", XDG_DATA_HOME="/y"):
            self.assertEqual(paths.config_dir(*APP), Path("/a"))
            self.assertEqual(paths.data_dir(*APP), Path("/b"))

    def test_xdg(self):
        with env(XDG_CONFIG_HOME="/x", XDG_DATA_HOME="/y"):
            self.assertEqual(paths.config_dir(*APP), Path("/x/galivelop-voice"))
            self.assertEqual(paths.data_dir(*APP), Path("/y/galivelop-voice"))

    def test_relative_xdg_ignored(self):
        with env(XDG_CONFIG_HOME="rel", XDG_DATA_HOME="./rel"):
            self.assertEqual(paths.config_dir(*APP), Path("/h/.config/galivelop-voice"))
            self.assertEqual(paths.data_dir(*APP), Path("/h/.local/share/galivelop-voice"))

    def test_home_fallback_and_other_application(self):
        with env():
            self.assertEqual(paths.data_dir(*APP), Path("/h/.local/share/galivelop-voice"))
            self.assertEqual(paths.data_dir("galivelop-image", "GIMG"), Path("/h/.local/share/galivelop-image"))
        with env(**{"GIMG_DATA_HOME": "/i"}):
            self.assertEqual(paths.data_dir("galivelop-image", "GIMG"), Path("/i"))


class StateDirTests(unittest.TestCase):
    """D-1: GALIVELOP_STATE_HOME > GVOICE_STATE_HOME (alias) > XDG_STATE_HOME/galivelop > ~/.local/state/galivelop."""

    def test_precedence_of_the_three_variables_and_the_alias(self):
        with env(GALIVELOP_STATE_HOME="/new", GVOICE_STATE_HOME="/old", XDG_STATE_HOME="/xdg"):
            self.assertEqual(paths.state_dir(), Path("/new"))
        with env(GVOICE_STATE_HOME="/old", XDG_STATE_HOME="/xdg"):
            self.assertEqual(paths.state_dir(), Path("/old"))
        with env(XDG_STATE_HOME="/xdg"):
            self.assertEqual(paths.state_dir(), Path("/xdg/galivelop"))
        with env():
            self.assertEqual(paths.state_dir(), Path("/h/.local/state/galivelop"))

    def test_empty_new_variable_falls_to_the_alias(self):
        with env(GALIVELOP_STATE_HOME="", GVOICE_STATE_HOME="/old"):
            self.assertEqual(paths.state_dir(), Path("/old"))

    def test_relative_xdg_state_ignored(self):
        with env(XDG_STATE_HOME="rel"):
            self.assertEqual(paths.state_dir(), Path("/h/.local/state/galivelop"))

    def test_machine_lock_path(self):
        with env(GALIVELOP_STATE_HOME="/s"):
            self.assertEqual(paths.machine_lock_path(), Path("/s/gpu.lock"))
        with env(XDG_STATE_HOME="/xdg"):
            self.assertEqual(paths.machine_lock_path(), Path("/xdg/galivelop/gpu.lock"))

    def test_application_files(self):
        d = Path("/d")
        self.assertEqual(paths.queue_path(d), Path("/d/queue.json"))
        self.assertEqual(paths.queue_lock_path(d), Path("/d/queue.json.lock"))
        self.assertEqual(paths.worker_lock_path(d), Path("/d/worker.lock"))
        self.assertEqual(paths.pause_path(d), Path("/d/queue.paused"))


class FlatpakTests(unittest.TestCase):
    """Inside the VS Code Flatpak the XDG folders point to the sandbox; the host folders are used instead."""

    def test_sandbox_xdg_is_ignored_inside_flatpak(self):
        app = "/h/.var/app/com.visualstudio.code"
        with env(FLATPAK_ID="com.visualstudio.code", XDG_DATA_HOME=app + "/data",
                 XDG_CONFIG_HOME=app + "/config", XDG_STATE_HOME=app + "/.local/state"):
            self.assertEqual(paths.data_dir(*APP), Path("/h/.local/share/galivelop-voice"))
            self.assertEqual(paths.config_dir(*APP), Path("/h/.config/galivelop-voice"))
            self.assertEqual(paths.state_dir(), Path("/h/.local/state/galivelop"))

    def test_explicit_and_other_xdg_still_win_inside_flatpak(self):
        with env(FLATPAK_ID="com.visualstudio.code", GALIVELOP_STATE_HOME="/s",
                 XDG_STATE_HOME="/h/.var/app/x/state"):
            self.assertEqual(paths.state_dir(), Path("/s"))
        with env(FLATPAK_ID="com.visualstudio.code", XDG_STATE_HOME="/y"):
            self.assertEqual(paths.state_dir(), Path("/y/galivelop"))

    def test_outside_flatpak_the_xdg_value_is_kept(self):
        with env(XDG_STATE_HOME="/h/.var/app/x/state"):
            self.assertEqual(paths.state_dir(), Path("/h/.var/app/x/state/galivelop"))

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
            ("/etc/passwd", "path.absolute"),
            ("~", "path.tilde"),
            ("~/x", "path.tilde"),
            ("..", "path.dotdot"),
            ("../x", "path.dotdot"),
            ("a/../x", "path.dotdot"),
            ("a/..", "path.dotdot"),
            ("a\\b", "path.backslash"),
            ("a\x00b", "path.nul"),
            ("a\nb", "path.control"),
            ("a\tb", "path.control"),
            ("a\x7fb", "path.control"),
            ("", "path.empty"),
            (None, "path.type"),
        ]
        for rel, code in cases:
            with self.subTest(rel=rel):
                self.assertEqual(self.reason(rel), code)

    def test_dots_inside_names_are_fine(self):
        self.assertEqual(paths.inside(self.root, "a..b/c"), self.root / "a..b" / "c")

    def test_nonexistent_target(self):
        self.assertEqual(paths.inside(self.root, "new/dir/x"), self.root / "new/dir/x")

    def test_symlink_outside_rejected(self):
        os.symlink(self.outside, self.root / "link")
        self.assertEqual(self.reason("link/x"), "path.outside")
        self.assertEqual(self.reason("link"), "path.outside")

    def test_symlink_to_file_outside_rejected(self):
        (self.outside / "f").write_text("x")
        os.symlink(self.outside / "f", self.root / "flink")
        self.assertEqual(self.reason("flink"), "path.outside")

    def test_symlink_inside_ok(self):
        (self.root / "real").mkdir()
        os.symlink(self.root / "real", self.root / "alias")
        self.assertEqual(paths.inside(self.root, "alias/x"), self.root / "real" / "x")

    def test_root_is_symlink(self):
        link = self.tmp / "rootlink"
        os.symlink(self.root, link)
        self.assertEqual(paths.inside(link, "a/x"), self.root / "a" / "x")
        os.symlink(self.outside, self.root / "out")
        self.assertEqual(self.reason("out/x", root=link), "path.outside")

    def test_symlink_loop(self):
        os.symlink(self.root / "b", self.root / "a")
        os.symlink(self.root / "a", self.root / "b")
        # Depending on the Python version the loop raises or resolves in place;
        # either way the guard never lets a path out of the root.
        try:
            target = paths.inside(self.root, "a/x")
        except PathError as exc:
            self.assertEqual(exc.code, "path.unresolvable")
        else:
            self.assertIn(self.root, target.parents)

    def test_root_itself(self):
        self.assertEqual(paths.inside(self.root, "."), self.root)

    def test_error_message_translated(self):
        err = PathError("path.dotdot")
        self.assertIn("..", err.message("es"))
        self.assertNotEqual(err.message("es"), err.message("en"))


class RelativeExplicitTests(unittest.TestCase):
    """A relative explicit folder would depend on the working directory: it is ignored, like a relative XDG one."""

    def test_relative_config_and_data_ignored(self):
        with env(GVOICE_CONFIG_HOME="rel", GVOICE_DATA_HOME="./d", XDG_DATA_HOME="/y"):
            self.assertEqual(paths.config_dir(*APP), Path("/h/.config/galivelop-voice"))
            self.assertEqual(paths.data_dir(*APP), Path("/y/galivelop-voice"))

    def test_relative_state_ignored_and_falls_to_the_next(self):
        with env(GALIVELOP_STATE_HOME="rel", GVOICE_STATE_HOME="/old"):
            self.assertEqual(paths.state_dir(), Path("/old"))
        with env(GALIVELOP_STATE_HOME="rel", GVOICE_STATE_HOME="old", XDG_STATE_HOME="/xdg"):
            self.assertEqual(paths.machine_lock_path(), Path("/xdg/galivelop/gpu.lock"))


if __name__ == "__main__":
    unittest.main()
