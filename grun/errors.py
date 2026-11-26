"""Errores con un código estable y parámetros, para que cualquier interfaz los pueda mostrar.

Copiado de gvoice@8a17618 (`gvoice/errors.py`); adaptado: `GvoiceError` pasa a `GrunError`, se quita el formato de
errores del validador de esquemas (`errors=`, `schema.format_error`) porque `grun` no lleva esquemas, y se añade
`CODES`, la lista de códigos con texto en `locales/` (D-14): los de gvoice que no son de voz con su nombre, más
`queue.invalid_transition`, `queue.orphaned` y `net.non_local_host`."""
from __future__ import annotations

from . import i18n

CODES = (
    "path.type", "path.empty", "path.nul", "path.control", "path.backslash", "path.absolute", "path.tilde",
    "path.dotdot", "path.outside", "path.unresolvable",
    "project.bad_name", "log.bad_project",
    "limit.memory", "limit.model",
    "machine_lock.unavailable",
    "queue.corrupt", "queue.unknown", "queue.not_cancellable", "queue.not_running", "queue.bad_state",
    "worker.already_running", "worker.unexpected",
    # Nuevos (D-14)
    "queue.invalid_transition", "queue.orphaned", "net.non_local_host",
)


class GrunError(Exception):
    """Un error para la persona: `code` elige el texto `error.<code>`, `params` lo rellenan."""

    def __init__(self, code: str, **params):
        super().__init__(code)
        self.code = code
        self.params = params

    def message(self, lang: str | None = None) -> str:
        return i18n.t("error." + self.code, lang, **self.params)

    def __str__(self):
        return "%s %r" % (self.code, self.params)


class PathError(GrunError):
    """Una ruta de fuera (archivo de proyecto, pedido) no pasó la guarda de rutas."""
