"""Registro JSONL de cada operación del motor y estimación de duración.

Copiado de gvoice@8a17618 (`gvoice/log.py`, a su vez de gimg@fa1076e); adaptado:
- El nombre de la aplicación es el primer parámetro de `log_path`, `append` y `estimate` (carpeta de datos).
- Los campos `app.voice.*` pasan a `app.*` (`app.key`, `app.seed`, `app.device`, `app.engine_commit`,
  `app.engine_version`, `app.min_free_mb`, `app.peak_rss_mb`, `app.backend`, `app.command`) y `operation` es un
  parámetro obligatorio de `record_for`.
- Fuera por ser de voz: `OP_DESIGN`, `OP_LINE`, `OP_PRINT`, `app.voice.text_chars` y `app.voice.audio_ms`."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone

from . import fsutil, paths


def log_path(app: str, project: str):
    return paths.project_data_dir(app, project, "log.bad_project") / "log.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pick_stat(result, stats: dict, name: str):
    value = getattr(result, name, None)
    return stats.get(name) if value is None else value


def record_for(key: str, task: str, spec: dict, machine: dict, provider: str | None, operation: str,
               result=None, error: str | None = None, ts: str | None = None,
               stats: dict | None = None) -> dict:
    """La línea de registro de una operación: de un resultado del motor (`result`) o de un mensaje de error.
    `spec` puede llevar ``seed``, ``model`` y ``device``; lo que dice el resultado manda sobre la especificación.
    `operation` es ``gen_ai.operation.name``. `stats` (``min_free_mb``, ``peak_rss_mb``) son las cifras de memoria
    de una ejecución fallida; las del resultado mandan. Los valores ausentes se omiten, nunca ``null``."""
    def pick(name):
        value = getattr(result, name, None)
        return spec.get(name) if value is None else value

    stats = stats or {}
    line = {
        "ts": ts or _now(),
        "gen_ai.operation.name": operation,
        "gen_ai.provider.name": provider,
        "gen_ai.request.model": pick("model"),
        "app.task": task,
        "app.machine_profile": machine.get("name"),
        "app.duration_ms": getattr(result, "duration_ms", None),
        "app.load_ms": getattr(result, "load_ms", None),
        "app.error": error,
        "app.key": key,
        "app.seed": pick("seed"),
        "app.device": pick("device"),
        "app.engine_commit": getattr(result, "engine_commit", None),
        "app.engine_version": getattr(result, "engine_version", None),
        "app.min_free_mb": pick_stat(result, stats, "min_free_mb"),
        "app.peak_rss_mb": pick_stat(result, stats, "peak_rss_mb"),
        "app.backend": getattr(result, "backend", None),
        "app.command": getattr(result, "command", None),
    }
    return {k: v for k, v in line.items() if v is not None}


def append(app: str, project: str, record: dict) -> None:
    """Añade una línea JSON al registro del proyecto."""
    path = log_path(app, project)
    text = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with fsutil.lock(path):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()


def _lines(path):
    try:
        fh = open(path, encoding="utf-8")
    except FileNotFoundError:
        return
    with fh:
        for raw in fh:
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            if isinstance(line, dict):
                yield line


def estimate(app: str, project: str, provider: str, operation: str, model: str, device: str):
    """Mediana de ``app.duration_ms`` (ms) de las líneas sin error con el mismo proveedor, operación, modelo y
    dispositivo (el mismo modelo es más lento en la CPU que en Vulkan); ``None`` sin datos."""
    values = []
    for line in _lines(log_path(app, project)):
        duration = line.get("app.duration_ms")
        if ("app.error" in line or line.get("gen_ai.provider.name") != provider
                or line.get("gen_ai.operation.name") != operation
                or line.get("gen_ai.request.model") != model
                or line.get("app.device") != device
                or not isinstance(duration, (int, float)) or isinstance(duration, bool)):
            continue
        values.append(duration)
    return statistics.median(values) if values else None
