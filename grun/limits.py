"""Límites de seguridad de un perfil de máquina: tiempo, memoria y modelos.

Copiado de gvoice@8a17618 (`gvoice/limits.py`, a su vez de gimg@fa1076e); adaptado:
- `GvoiceError` pasa a `GrunError`; las variables de pruebas son `GALIVELOP_MEMINFO` y `GALIVELOP_PROC_STATUS`
  (en gvoice, `GVOICE_MEMINFO` y `GVOICE_PROC_STATUS`).
- Fuera: la carga de perfiles (`load_machine`, `DEFAULT_PROFILE`, los `machine.*`), que depende de esquemas, de la
  carpeta de configuración y de los perfiles de la aplicación; `grun` recibe el perfil ya cargado (un `dict`)."""
from __future__ import annotations

import os

from .errors import GrunError


class LimitError(GrunError):
    """Un trabajo pasa un límite del perfil de máquina."""


def timeout_s(machine: dict) -> int:
    """Límite de tiempo de un intento, en segundos (``timeoutS``)."""
    return machine["timeoutS"]


def check_memory(free_mb, machine: dict) -> None:
    """Lanza `LimitError` si `free_mb` está por debajo de ``minFreeMemoryMb`` (para empezar un trabajo).
    ``None`` (desconocida) pasa."""
    minimum = machine.get("minFreeMemoryMb")
    if free_mb is not None and minimum is not None and free_mb < minimum:
        raise LimitError("limit.memory", free=free_mb, min=minimum)


def must_abort(free_mb, machine: dict) -> bool:
    """Si hay que abortar un trabajo en marcha: la memoria libre cayó por debajo de ``watchMemoryMb``."""
    watch = machine.get("watchMemoryMb")
    return free_mb is not None and watch is not None and free_mb < watch


def check_model(use: str, model: str, machine: dict) -> None:
    """Lanza `LimitError` si el perfil no admite `model` para `use` (una clave de ``models`` del perfil)."""
    models = machine.get("models") or {}
    allowed = models.get(use)
    if allowed is None:
        return
    allowed = [allowed] if isinstance(allowed, str) else list(allowed)
    if model not in allowed:
        raise LimitError("limit.model", model=model, use=use, allowed=", ".join(allowed))


MEMINFO_ENV = "GALIVELOP_MEMINFO"  # pruebas: un archivo con el formato de /proc/meminfo
PROC_STATUS_ENV = "GALIVELOP_PROC_STATUS"  # pruebas: un archivo con el formato de /proc/<pid>/status; ``{pid}`` se sustituye


def _meminfo_mb(field: str, meminfo: str | None = None):
    """Campo `field` de ``/proc/meminfo`` (kB) en MB, o ``None`` donde no se pueda leer. `meminfo` por defecto es
    ``$GALIVELOP_MEMINFO``, si no ``/proc/meminfo``."""
    meminfo = meminfo or os.environ.get(MEMINFO_ENV) or "/proc/meminfo"
    try:
        with open(meminfo, encoding="ascii") as fh:
            for line in fh:
                if line.startswith(field + ":"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def available_memory_mb(meminfo: str | None = None):
    """``MemAvailable`` en MB, o ``None`` donde no se pueda leer."""
    return _meminfo_mb("MemAvailable", meminfo)


def total_memory_mb(meminfo: str | None = None):
    """``MemTotal`` en MB, o ``None`` donde no se pueda leer (misma fuente que `available_memory_mb`)."""
    return _meminfo_mb("MemTotal", meminfo)


def peak_rss_mb(pid: int):
    """Memoria residente máxima (``VmHWM``) del proceso `pid` en MB, o ``None`` si no se puede leer (ya no existe,
    o no hay ``/proc``). El archivo es ``$GALIVELOP_PROC_STATUS`` (``{pid}`` sustituido) si está puesta."""
    template = os.environ.get(PROC_STATUS_ENV) or "/proc/{pid}/status"
    try:
        with open(template.format(pid=pid), encoding="ascii", errors="replace") as fh:
            for line in fh:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None
