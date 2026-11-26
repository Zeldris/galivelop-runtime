# GR-1 · Soporte de grun: rutas, límites, errores, escritura atómica y registro

## Goal

Primer paso de `0.1` (R1, [roadmap](../roadmap.md)): las piezas de soporte que usan el candado, la cola y el worker
(GR-2..GR-4), sacadas de gvoice (`galivelop-voice-generator@8a17618`, `gvoice/`) al paquete `grun/`.

## Scope

- `grun/paths.py` desde `gvoice/paths.py`: solo lo general (estado de la marca y `gpu.lock`, datos de la aplicación).
  D-1: `$GALIVELOP_STATE_HOME`, alias `$GVOICE_STATE_HOME` (gana la nueva si están las dos) hasta R3, luego
  `$XDG_STATE_HOME/galivelop`, luego `~/.local/state/galivelop`, con la regla de Flatpak de gvoice tal cual. Las rutas
  de la aplicación se parametrizan por nombre de aplicación (gvoice no se nombra en el código salvo en el alias).
- `grun/limits.py` desde `gvoice/limits.py`: lo que no es propio de voz.
- `grun/errors.py` + `grun/i18n.py` + `grun/locales/{es,en}.json` desde gvoice. D-14: se conservan los códigos de
  gvoice con su nombre y se añaden `queue.invalid_transition`, `queue.orphaned`, `net.non_local_host`. Los códigos
  propios de voz se quedan fuera. Los de gimg entran cuando los pida la cola (GR-3).
- `grun/fsutil.py` desde `gvoice/fsutil.py`: escritura atómica (`mkstemp` en el mismo directorio, `fsync`,
  `os.replace`).
- `grun/log.py` desde `gvoice/log.py`: registro, con el nombre de la aplicación como parámetro.
- Cada módulo copiado lleva en su docstring «Copiado de gvoice@8a17618» y qué se adaptó.
- Fuera: `machine_lock` (GR-2), cola (GR-3), worker y motor (GR-4), servidor (R4).

## Acceptance

- [x] Invariante 6 (parcial): tabla de entornos (con y sin `XDG_STATE_HOME`, dentro y fuera de Flatpak, con
      `GALIVELOP_STATE_HOME`, con `GVOICE_STATE_HOME`, con las dos) y la ruta de `gpu.lock` esperada en cada fila,
      la misma que da `gvoice/paths.py`.
- [x] Invariante 10 (parte de escritura): fallo inyectado entre la escritura y el `replace` deja el archivo anterior
      legible y sin temporales.
- [x] Invariante 12: test que recorre los `import` de `grun/` contra `sys.stdlib_module_names` (con lista propia si
      Python < 3.10).
- [x] Los tres códigos nuevos y todos los conservados tienen texto en `es` y `en`; test que compara las claves de los
      dos `locales` con los códigos de `errors.py`.
- [x] Los tests de gvoice que cubren estos módulos, adaptados, en `tests/`.
- [x] Check en verde.

## Files

`grun/__init__.py`, `grun/paths.py`, `grun/limits.py`, `grun/errors.py`, `grun/i18n.py`, `grun/locales/`,
`grun/fsutil.py`, `grun/log.py`, `tests/test_*.py`.

## Change log

- `grun/` nuevo (solo stdlib, Python >= 3.10 según el DDD): `paths`, `limits`, `errors`, `i18n`, `fsutil`, `log` y
  `locales/{es,en}.json`, cada uno con «Copiado de gvoice@8a17618» y lo adaptado en su docstring.
- `paths`: `state_dir` con `GALIVELOP_STATE_HOME` (alias `GVOICE_STATE_HOME`), `machine_lock_path`, `data_dir(app)`,
  `project_data_dir(app, name)`, `inside`/`check_relative`. Fuera: `config_dir`, `models_dir`, `engine_dir`, claves.
- `limits`: `LimitError`, memoria, modelos por uso, lectura de `/proc` (`GALIVELOP_MEMINFO`, `GALIVELOP_PROC_STATUS`).
  Fuera: `load_machine` y los perfiles.
- `errors`: `GrunError` (sin el formato de errores de esquema) y `CODES`: los de gvoice no propios de voz
  (`path.*`, `project.bad_name`, `log.bad_project`, `limit.*`, `machine_lock.unavailable`, `queue.{corrupt,unknown,
  not_cancellable,not_running,bad_state}`, `worker.{already_running,unexpected}`) más `queue.invalid_transition`,
  `queue.orphaned`, `net.non_local_host`.
- `i18n`: `GALIVELOP_LANG`. `log`: nombre de aplicación como parámetro, campos `app.*` sin `voice`.
- Tests: `tests/test_{paths,fsutil,stdlib_only,i18n,errors,limits,log}.py`.

## Verification

- `python3 -m unittest discover -s tests`: 75 tests en verde (vistos en rojo antes de escribir `grun/`).
- Invariante 6: las filas de la tabla sin variable nueva se comprobaron contra `gvoice/paths.py` de
  gvoice@8a17618 con el mismo entorno (todas coinciden); las de `GALIVELOP_STATE_HOME` las fija D-1.
- `python3 .claude/gw/scripts/tests-after-main.py` y `python3 .claude/gw/scripts/ci-local.py --validate`: en verde
  (`actionlint` no instalado, solo aviso).

Preguntas abiertas: van a [docs/questions.md](../questions.md), no aquí.
