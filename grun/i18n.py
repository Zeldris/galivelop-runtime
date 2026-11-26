"""Búsqueda de textos es/en con respaldo.

Copiado de gvoice@8a17618 (`gvoice/i18n.py`, a su vez de gimg@4365f9a); adaptado: la variable de idioma es
`GALIVELOP_LANG` (en gvoice, `GVOICE_LANG`)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_LOCALES = Path(__file__).parent / "locales"
_cache = {}
FALLBACK = "en"


def available() -> frozenset:
    """Idiomas que tienen archivo de textos en locales/."""
    return frozenset(p.stem for p in _LOCALES.glob("*.json"))


def normalise(value: str) -> str:
    """`es_ES.UTF-8` -> `es`; un idioma sin archivo de textos -> el de respaldo."""
    lang = re.split(r"[_.@:-]", value.strip().lower())[0]
    return lang if lang in available() else FALLBACK


def default_lang() -> str:
    explicit = os.environ.get("GALIVELOP_LANG")
    if explicit:
        return normalise(explicit)
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return normalise(value)
    return FALLBACK


def _load(lang: str) -> dict:
    if lang not in available():
        return {}
    if lang not in _cache:
        path = _LOCALES / (lang + ".json")
        try:
            with open(path, encoding="utf-8") as fh:
                _cache[lang] = json.load(fh)
        except (OSError, ValueError):
            _cache[lang] = {}
    return _cache[lang]


def t(key: str, lang: str | None = None, **params) -> str:
    lang = lang or default_lang()
    for candidate in (lang, FALLBACK):
        text = _load(candidate).get(key)
        if text is not None:
            return text.format(**params)
    return key
