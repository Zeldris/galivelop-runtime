"""El candado de máquina: invariantes 1, 2, 3, 5 y 6 completa, y el titular (`grun.lock/0`).

Copiado de gvoice@8a17618 (`tests/test_machine_lock.py` y el test del motor huérfano de
`tests/test_engine_qwentts.py:361`); adaptado: `GvoiceError` pasa a `GrunError`, la variable de estado a
`GALIVELOP_STATE_HOME`, el motor huérfano es un hijo de Python con `pass_fds=held_fds()` en su propia sesión, y se
añaden los tests del titular, del solapamiento entre dos procesos y el análisis estático de borrados."""
import ast
import contextlib
import fcntl
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from grun import machine_lock, paths
from grun.errors import GrunError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_paths import LOCK_TABLE, VARS  # noqa: E402  (la tabla de GR-1)

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 30
HOLDER = (
    "import fcntl, os, sys, time\n"
    "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
    "fcntl.flock(fd, fcntl.LOCK_EX)\n"
    "print('held', flush=True)\n"
    "time.sleep(60)\n")
# Toma el candado con hold(), apunta [entrada, salida] y espera una línea en stdin antes de soltarlo.
TIMED = (
    "import sys, time\n"
    "from grun import machine_lock\n"
    "with machine_lock.hold(app=sys.argv[1], poll_s=0.01):\n"
    "    start = time.monotonic()\n"
    "    print('held', flush=True)\n"
    "    sys.stdin.readline()\n"
    "    end = time.monotonic()\n"
    "print(repr([start, end]), flush=True)\n")
# Toma el candado, lanza un hijo en su propia sesión que hereda el descriptor y espera a que lo maten.
ORPHAN = (
    "import subprocess, sys, time\n"
    "from grun import machine_lock\n"
    "with machine_lock.hold(app='motor'):\n"
    "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],\n"
    "                             pass_fds=machine_lock.held_fds(), start_new_session=True)\n"
    "    print(child.pid, flush=True)\n"
    "    time.sleep(60)\n")


class LockBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        env = mock.patch.dict(os.environ, {"GALIVELOP_STATE_HOME": str(self.tmp / "state")})
        env.start()
        self.addCleanup(env.stop)

    def spawn(self, code, *args, stdin=None):
        proc = subprocess.Popen([sys.executable, "-c", code, *args], stdout=subprocess.PIPE, stdin=stdin,
                                text=True, cwd=str(ROOT))
        self.addCleanup(proc.stdout.close)
        if stdin is not None:
            self.addCleanup(lambda: proc.stdin.closed or proc.stdin.close())
        self.addCleanup(proc.wait, TIMEOUT)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        return proc

    def holder(self):
        """Otro proceso con el candado (sin titular escrito, como gvoice actual o `flock(1)`)."""
        path = paths.machine_lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        proc = self.spawn(HOLDER, str(path))
        self.assertEqual(proc.stdout.readline().strip(), "held")
        return proc

    def until_free(self):
        end = time.monotonic() + TIMEOUT
        while machine_lock.busy() and time.monotonic() < end:
            time.sleep(0.02)
        return not machine_lock.busy()


class HoldTests(LockBase):
    def test_creates_the_missing_state_folder(self):
        self.assertFalse((self.tmp / "state").exists())
        with machine_lock.hold():
            self.assertTrue(paths.machine_lock_path().is_file())
            self.assertTrue(machine_lock.busy())
        self.assertFalse(machine_lock.busy())
        self.assertTrue(paths.machine_lock_path().is_file())  # nunca se borra

    def test_creates_the_missing_file_in_an_existing_folder(self):
        (self.tmp / "state").mkdir()
        with machine_lock.hold():
            self.assertTrue(paths.machine_lock_path().is_file())

    def test_busy_is_a_pure_read(self):
        self.assertFalse(machine_lock.busy())
        self.assertFalse((self.tmp / "state").exists())

    def test_released_on_error(self):
        with self.assertRaises(RuntimeError):
            with machine_lock.hold():
                raise RuntimeError("boom")
        self.assertFalse(machine_lock.busy())

    def test_unwritable_state_folder(self):
        blocker = self.tmp / "file"
        blocker.write_text("x")
        with mock.patch.dict(os.environ, {"GALIVELOP_STATE_HOME": str(blocker / "sub")}):
            with self.assertRaises(GrunError) as cm:
                with machine_lock.hold():
                    self.fail("no debe tomar el candado")
        self.assertEqual(cm.exception.code, "machine_lock.unavailable")
        self.assertEqual(cm.exception.params["path"], str(blocker / "sub" / "gpu.lock"))
        self.assertTrue(cm.exception.params["reason"])

    def test_busy_lock_waits_then_proceeds(self):
        proc = self.holder()
        self.assertTrue(machine_lock.busy())
        waited = threading.Event()
        got = threading.Event()

        def take():
            with machine_lock.hold(on_wait=waited.set, poll_s=0.01):
                got.set()

        thread = threading.Thread(target=take)
        thread.start()
        self.assertTrue(waited.wait(TIMEOUT))  # avisó de la espera
        self.assertFalse(got.is_set())  # sigue esperando: no falló
        proc.kill()
        proc.wait()
        thread.join(TIMEOUT)
        self.assertTrue(got.is_set())

    def test_on_wait_is_called_once(self):
        proc = self.holder()
        calls = []
        polls = []

        def cancel():
            polls.append(1)
            return len(polls) > 5

        with self.assertRaises(machine_lock.WaitCancelled):
            with machine_lock.hold(cancel, lambda: calls.append(1), poll_s=0.001):
                pass
        self.assertEqual(calls, [1])
        proc.kill()

    def test_wait_is_cancellable(self):
        self.holder()
        cancel = threading.Event()
        threading.Timer(0.2, cancel.set).start()
        start = time.monotonic()
        with self.assertRaises(machine_lock.WaitCancelled):
            with machine_lock.hold(cancel.is_set, poll_s=0.01):
                self.fail("no debe tomar el candado")
        self.assertLess(time.monotonic() - start, TIMEOUT)
        self.assertEqual(machine_lock.held_fds(), [])

    def test_process_dying_with_the_lock_frees_it(self):
        """Invariante 2: un titular muerto por SIGKILL suelta el candado."""
        proc = self.spawn(TIMED, "otra", stdin=subprocess.PIPE)
        self.assertEqual(proc.stdout.readline().strip(), "held")
        self.assertTrue(machine_lock.busy())
        proc.kill()  # SIGKILL: sin ocasión de limpiar
        proc.wait(TIMEOUT)
        self.assertFalse(machine_lock.busy())
        with machine_lock.hold(should_cancel=lambda: True):
            pass

    def test_lock_is_exclusive_between_two_holds_in_one_process(self):
        with machine_lock.hold():
            fd = os.open(str(paths.machine_lock_path()), os.O_RDWR)
            self.addCleanup(os.close, fd)
            with self.assertRaises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_held_fds(self):
        self.assertEqual(machine_lock.held_fds(), [])
        with machine_lock.hold():
            fds = machine_lock.held_fds()
            self.assertEqual(len(fds), 1)
            self.assertEqual(os.fstat(fds[0]).st_ino, paths.machine_lock_path().stat().st_ino)
        self.assertEqual(machine_lock.held_fds(), [])


class TwoProcesses(LockBase):
    def test_holds_never_overlap(self):
        """Invariante 1: dos procesos con `hold()` sobre la misma ruta; sus intervalos no se solapan."""
        first = self.spawn(TIMED, "imagen", stdin=subprocess.PIPE)
        self.assertEqual(first.stdout.readline().strip(), "held")
        second = self.spawn(TIMED, "voz", stdin=subprocess.PIPE)
        # El segundo espera mientras el primero lo tiene: el titular sigue siendo el primero.
        self.assertEqual(machine_lock.holder().app, "imagen")
        first.stdin.write("\n")
        first.stdin.close()
        a = eval(first.stdout.readline())
        self.assertEqual(first.wait(TIMEOUT), 0)
        self.assertEqual(second.stdout.readline().strip(), "held")
        self.assertEqual(machine_lock.holder().app, "voz")
        second.stdin.write("\n")
        second.stdin.close()
        b = eval(second.stdout.readline())
        self.assertEqual(second.wait(TIMEOUT), 0)
        self.assertLessEqual(a[1], b[0])  # el reloj monótono es común a la máquina


class Inheritance(LockBase):
    def test_an_orphaned_child_keeps_the_machine_lock(self):
        """Invariante 3: el hijo con `pass_fds=held_fds()` sigue con el candado tras matar al titular."""
        worker = self.spawn(ORPHAN)
        child = int(worker.stdout.readline())

        def kill_child():
            with contextlib.suppress(ProcessLookupError):
                os.kill(child, signal.SIGKILL)
        self.addCleanup(kill_child)
        self.assertTrue(machine_lock.busy())
        worker.kill()  # SIGKILL: no corre ningún finally; se cierra solo el descriptor del titular
        worker.wait(TIMEOUT)
        self.assertTrue(machine_lock.busy())  # el hijo, vivo en su sesión, sigue con el candado
        with self.assertRaises(machine_lock.WaitCancelled):
            with machine_lock.hold(should_cancel=lambda: True):
                pass
        kill_child()
        self.assertTrue(self.until_free())  # libre de nuevo en cuanto acaba el hijo


class HolderTests(LockBase):
    def test_written_on_take_and_read_from_another_process(self):
        with machine_lock.hold(app="gimg", entry=7):
            out = subprocess.run(
                [sys.executable, "-c", "from grun import machine_lock as m; h = m.holder();"
                 "print(h.app, h.pid, h.entry, h.since)"],
                capture_output=True, text=True, cwd=str(ROOT), timeout=TIMEOUT, check=True).stdout.split()
            self.assertEqual(out[:3], ["gimg", str(os.getpid()), "7"])
            self.assertTrue(out[3])
            data = json.loads(paths.machine_lock_path().read_text())
            self.assertEqual(data["schema"], "grun.lock/0")
            self.assertEqual(data["app"], "gimg")
            self.assertEqual(data["entry"], 7)
        self.assertIsNone(machine_lock.holder())  # al soltar se vacía

    def test_entry_is_optional(self):
        with machine_lock.hold(app="wmf"):
            h = machine_lock.holder()
            self.assertEqual((h.app, h.pid, h.entry), ("wmf", os.getpid(), None))

    def test_written_in_place_on_the_same_inode(self):
        path = paths.machine_lock_path()
        path.parent.mkdir(parents=True)
        path.write_text('{"schema": "grun.lock/0", "app": "viejo-y-mucho-mas-largo-que-el-nuevo", "pid": 1}')
        inode = path.stat().st_ino
        with machine_lock.hold(app="g"):
            self.assertEqual(path.stat().st_ino, inode)
            self.assertEqual(machine_lock.holder().app, "g")  # truncado: no quedan restos del anterior
        self.assertEqual(path.stat().st_ino, inode)

    def test_garbage_does_not_break_holder(self):
        path = paths.machine_lock_path()
        self.assertIsNone(machine_lock.holder())  # no existe
        path.parent.mkdir(parents=True)
        for text in ("", '{"schema": "grun.lock/0", "app": "a', "\x00\xff basura", "[1, 2]", '"x"',
                     '{"schema": "otro/9", "app": "a", "pid": 1}', '{"app": 3, "pid": "x"}'):
            with self.subTest(text=text):
                path.write_bytes(text.encode("utf-8", "surrogateescape") if "\xff" not in text
                                 else b"\x00\xff basura")
                self.assertIsNone(machine_lock.holder())

    def test_foreign_holder_without_content(self):
        self.holder()  # como gvoice actual o `flock(1)`: no escriben nada
        self.assertTrue(machine_lock.busy())
        self.assertIsNone(machine_lock.holder())


class NeverDeleted(unittest.TestCase):
    """Invariante 5: nada en `grun/` borra un archivo de candado."""
    DELETERS = {"unlink", "remove", "rmtree", "removedirs", "rmdir"}

    def offenders(self, source, name="<src>"):
        found = []
        for node in ast.walk(ast.parse(source, name)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            attr = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if attr not in self.DELETERS:
                continue
            text = ast.unparse(node).lower()
            if "lock" in text:
                found.append("%s:%d %s" % (name, node.lineno, ast.unparse(node)))
        return found

    def test_scan_catches_a_deletion(self):
        self.assertTrue(self.offenders("os.unlink(paths.machine_lock_path())"))
        self.assertTrue(self.offenders("lock_path.unlink()"))
        self.assertTrue(self.offenders("shutil.rmtree(lock_dir)"))
        self.assertFalse(self.offenders("os.unlink(tmp)"))

    def test_grun_never_deletes_a_lock(self):
        found = []
        for path in sorted((ROOT / "grun").rglob("*.py")):
            found += self.offenders(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)))
        self.assertEqual(found, [])


class PathTableAgainstHold(unittest.TestCase):
    """Invariante 6 completa: la tabla de GR-1, ahora con el archivo que crea `hold()`."""

    def test_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()

            def moved(value):
                return str(root) + value if value.startswith("/") else value

            for name, setting, expected in LOCK_TABLE:
                with self.subTest(name):
                    base = {k: "" for k in VARS}
                    base.update({k: moved(v) for k, v in setting.items()}, HOME=moved("/h"))
                    with mock.patch.dict(os.environ, base):
                        with machine_lock.hold():
                            self.assertEqual(machine_lock.held_fds() and
                                             os.fstat(machine_lock.held_fds()[0]).st_ino,
                                             Path(moved(expected)).stat().st_ino)


if __name__ == "__main__":
    unittest.main()
