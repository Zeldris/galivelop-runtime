"""JSON atómico y candados por archivo.

Copiado de gvoice@8a17618 (`gvoice/fsutil.py`, a su vez de gimg@fa1076e); sin cambios de código: solo se traduce el
docstring. La escritura es `mkstemp` en el mismo directorio, `fsync` y `os.replace`."""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
import threading
from pathlib import Path

_MISSING = object()
_umask_lock = threading.Lock()


def honour_umask(fd: int) -> None:
    """Los archivos de `mkstemp` son 0600; el definitivo lleva el modo de un `open()` normal (0666 & ~umask)."""
    with _umask_lock:
        mask = os.umask(0)
        os.umask(mask)
    os.fchmod(fd, 0o666 & ~mask)


def write_json(path, data) -> None:
    """Escribe JSON (sangría 2, claves ordenadas, salto final) con archivo temporal + os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        honour_umask(fd)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def read_json(path, default=_MISSING):
    """Lee JSON; si falta el archivo devuelve `default` (o lanza FileNotFoundError)."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        if default is _MISSING:
            raise
        return default


@contextlib.contextmanager
def lock(path):
    """flock exclusivo sobre `<path>.lock` para leer-modificar-escribir `path`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # cerrar suelta el candado


@contextlib.contextmanager
def try_lock(path):
    """Como `lock` pero sin esperar: da ``True`` con el candado tomado, ``False`` si otro proceso lo tiene."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path.with_name(path.name + ".lock")), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            taken = True
        except BlockingIOError:
            taken = False
        yield taken
    finally:
        os.close(fd)
