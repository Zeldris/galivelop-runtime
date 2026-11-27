"""El candado de máquina (D8 de gvoice): un generador a la vez en la máquina.

Copiado de gvoice@8a17618 (`gvoice/machine_lock.py`); adaptado: `GvoiceError` pasa a `GrunError` (mismo código,
`machine_lock.unavailable`), la ruta es `grun.paths.machine_lock_path`, el docstring se traduce y se añade el
titular (`Holder`, `grun.lock/0`, DDD §4): `hold()` acepta `app` y `entry`, escribe el titular al tomar el candado y
lo vacía al soltarlo, y `holder()` lo lee.

Cada trabajo tiene un ``flock`` exclusivo sobre ``<state>/gpu.lock`` mientras corre, así una imagen y una voz nunca
comparten la memoria de una Steam Deck. Si otro proceso lo tiene, el trabajo *espera*, nunca falla: la espera sondea,
así una cancelación (``should_cancel``) o una señal la acaban. El núcleo suelta el ``flock`` cuando muere su proceso,
así un trabajador matado a mitad nunca deja la máquina bloqueada. Un hijo que hereda el descriptor (`held_fds`)
conserva el candado aunque muera su padre. El archivo nunca se borra (borrarlo dejaría a dos titulares con dos
archivos distintos); se crea con la carpeta de estado si falta.

El titular se escribe **en el sitio**, sobre el mismo descriptor que tiene el ``flock`` (truncar y escribir), nunca
con un archivo nuevo y ``os.replace``: otro inodo serían dos candados. Es solo información: el candado lo da el
``flock``, y los clientes que no escriben nada (gvoice actual, ``flock(1)`` de WMF) dejan el archivo vacío."""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from . import paths
from .errors import GrunError

POLL_S = 0.05
SCHEMA = "grun.lock/0"
_MAX_READ = 64 * 1024
_held = []  # descriptores de los candados que tiene ahora este proceso (ver `held_fds`)


class WaitCancelled(Exception):
    """`should_cancel()` dio verdadero mientras se esperaba el candado."""


@dataclass(frozen=True)
class Holder:
    """Quién dice tener el candado (`grun.lock/0`): aplicación, pid, entrada (opcional) y desde cuándo (ISO 8601, UTC)."""
    app: str
    pid: int
    since: str
    entry: object = None


def _write_holder(fd: int, app: str, entry) -> None:
    data = {"schema": SCHEMA, "app": app, "pid": os.getpid(), "entry": entry,
            "since": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    raw = (json.dumps(data, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    os.ftruncate(fd, 0)
    os.pwrite(fd, raw, 0)


@contextlib.contextmanager
def hold(should_cancel=None, on_wait=None, poll_s: float = POLL_S, app: str = "grun", entry=None):
    """Tiene el candado de la máquina durante el bloque ``with``. `on_wait` se llama una vez, cuando el candado resulta
    estar ocupado; a `should_cancel` se le pregunta durante la espera (verdadero lanza `WaitCancelled` y no toma nada).
    `app` y `entry` van al titular."""
    path = paths.machine_lock_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:
        raise GrunError("machine_lock.unavailable", path=str(path), reason=exc.strerror or str(exc))
    try:
        waited = False
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if not waited:
                    waited = True
                    if on_wait is not None:
                        on_wait()
                if should_cancel is not None and should_cancel():
                    raise WaitCancelled()
                time.sleep(poll_s)
        with contextlib.suppress(OSError):  # informativo: un disco lleno no quita el candado
            _write_holder(fd, app, entry)
        _held.append(fd)
        try:
            yield
        finally:
            _held.remove(fd)
            with contextlib.suppress(OSError):
                os.ftruncate(fd, 0)  # todavía con el flock: nadie lee un titular que ya se fue
    finally:
        os.close(fd)  # cerrar suelta el candado


def held_fds() -> list:
    """Los descriptores del candado tomado ahora. El motor real se los pasa a su proceso (``pass_fds``): el ``flock``
    es del archivo abierto, así sigue tomado mientras viva ese proceso aunque maten a este (un motor huérfano mantiene
    la máquina ocupada y el siguiente trabajo espera en vez de correr a la vez)."""
    return list(_held)


def busy() -> bool:
    """¿Tiene ahora el candado otro proceso (u otro descriptor abierto)? Una lectura pura que no crea nada."""
    try:
        fd = os.open(str(paths.machine_lock_path()), os.O_RDWR)
    except OSError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False
    finally:
        os.close(fd)


def holder():
    """El titular escrito en el candado, o ``None`` si no hay archivo, está vacío, a medias o es de otro formato.
    Una lectura pura: no toma el candado ni crea nada."""
    try:
        with open(paths.machine_lock_path(), "rb") as fh:
            raw = fh.read(_MAX_READ)
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return None
    app, pid, since = data.get("app"), data.get("pid"), data.get("since")
    if not isinstance(app, str) or type(pid) is not int or not isinstance(since, str):
        return None
    return Holder(app=app, pid=pid, since=since, entry=data.get("entry"))
