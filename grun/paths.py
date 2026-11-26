"""Carpetas de estado y de datos, y la guarda de rutas.

Copiado de gvoice@8a17618 (`gvoice/paths.py`, a su vez de gimg@fa1076e); adaptado (D-1):
- `state_dir()`: `$GALIVELOP_STATE_HOME`, alias `$GVOICE_STATE_HOME` hasta R3 (gana la nueva si están las dos),
  luego `$XDG_STATE_HOME/galivelop`, luego `~/.local/state/galivelop`, con la regla de Flatpak de gvoice tal cual.
- `data_dir(app)` y `project_data_dir(app, name)` se parametrizan por nombre de aplicación (la carpeta que cuelga de
  `$XDG_DATA_HOME`); la variable que lo fija es `<APP>_DATA_HOME` (en mayúsculas, `-` como `_`) o la que se pase.
- `project_data_dir` valida con el patrón de nombre de gvoice (`^[a-z0-9][a-z0-9-]*$`) sin cargar esquemas.
- Fuera por ser de voz o de esquemas: `config_dir`, `models_dir`, `engine_dir`, `max_key`, `check_key`."""
from __future__ import annotations

import os
import re
from pathlib import Path

from .errors import GrunError, PathError

STATE_ENV = "GALIVELOP_STATE_HOME"
STATE_ENV_ALIAS = "GVOICE_STATE_HOME"  # alias hasta R3 (D-1)
_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")


def _xdg_base(xdg: str):
    """``$<xdg>`` si es absoluta (la especificación XDG manda ignorar las relativas), si no ``None``.

    Dentro de un Flatpak (``FLATPAK_ID`` puesto, p. ej. VS Code en la Deck) las carpetas XDG apuntan al sandbox,
    ``~/.var/app/<id>/...``, donde no mira el anfitrión: se ignoran, y así los dos lados comparten ``~/.config``,
    ``~/.local/share`` y ``~/.local/state``."""
    base = os.environ.get(xdg)
    if not base or not os.path.isabs(base):
        return None
    if os.environ.get("FLATPAK_ID"):
        sandbox = Path.home() / ".var" / "app"
        if Path(base) == sandbox or sandbox in Path(base).parents:
            return None
    return Path(base)


def data_dir(app: str, env: str | None = None) -> Path:
    """Datos de la aplicación `app`: ``$<env>`` (por defecto ``<APP>_DATA_HOME``), si no
    ``$XDG_DATA_HOME/<app>``, si no ``~/.local/share/<app>``."""
    explicit = os.environ.get(env or app.upper().replace("-", "_") + "_DATA_HOME")
    if explicit:
        return Path(explicit)
    base = _xdg_base("XDG_DATA_HOME")
    if base is not None:
        return base / app
    return Path.home() / ".local" / "share" / app


def state_dir() -> Path:
    """Estado compartido por los generadores Galivelop de una máquina: ``$GALIVELOP_STATE_HOME``, si no
    ``$GVOICE_STATE_HOME`` (alias), si no ``$XDG_STATE_HOME/galivelop``, si no ``~/.local/state/galivelop``. Es la
    misma carpeta para todos, así comparten el candado de la máquina."""
    explicit = os.environ.get(STATE_ENV) or os.environ.get(STATE_ENV_ALIAS)
    if explicit:
        return Path(explicit)
    base = _xdg_base("XDG_STATE_HOME")
    if base is not None:
        return base / "galivelop"
    return Path.home() / ".local" / "state" / "galivelop"


def machine_lock_path() -> Path:
    """El candado de la máquina: ``<state>/gpu.lock``."""
    return state_dir() / "gpu.lock"


def check_relative(rel) -> str:
    """Rechaza todo lo que no sea una ruta relativa simple; la devuelve igual."""
    if not isinstance(rel, str):
        raise PathError("path.type")
    if rel == "":
        raise PathError("path.empty")
    if "\x00" in rel:
        raise PathError("path.nul")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in rel):
        raise PathError("path.control")
    if "\\" in rel:
        raise PathError("path.backslash")
    if rel.startswith("/"):
        raise PathError("path.absolute")
    if rel.startswith("~"):
        raise PathError("path.tilde")
    if ".." in rel.split("/"):
        raise PathError("path.dotdot")
    return rel


def inside(root, rel) -> Path:
    """Resuelve `rel` bajo `root` (siguiendo enlaces) y exige que se quede dentro.

    El destino puede no existir aún. Devuelve la ruta resuelta."""
    check_relative(rel)
    try:
        real_root = Path(root).resolve()
        target = (real_root / rel).resolve()
    except (OSError, RuntimeError):
        raise PathError("path.unresolvable", path=rel)
    if target != real_root and real_root not in target.parents:
        raise PathError("path.outside", path=rel)
    return target


def project_data_dir(app: str, name, code: str = "project.bad_name") -> Path:
    """``<data de app>/projects/<name>``; `name` cumple el patrón de nombre (así ``.``, ``..`` y ``a/b`` no llegan a
    otra carpeta). Si no, lanza GrunError `code`."""
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise GrunError(code, project=str(name))
    return inside(data_dir(app), "projects/" + name)
