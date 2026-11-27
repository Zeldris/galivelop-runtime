# GR-2 · Candado de máquina: machine_lock de gvoice con titular y held_fds

## Goal

Segundo paso de `0.1` (R1, [roadmap](../roadmap.md)): el candado de máquina (`gpu.lock`), sacado de
`gvoice/machine_lock.py` (gvoice@8a17618) a `grun/machine_lock.py`, con la escritura informativa del titular
(`grun.lock/0`, DDD §4) y `held_fds()` para que el hijo del motor herede el candado (DDD §3.3).

## Scope

- `grun/machine_lock.py` desde `gvoice/machine_lock.py`: `hold(should_cancel, on_wait)` como contexto, la espera
  cancelable por sondeo con `flock(LOCK_EX|LOCK_NB)`, `held_fds()`, `busy()`; la ruta, `grun.paths.machine_lock_path`.
  El error, `machine_lock.unavailable` (ya en `CODES`).
- Titular (`Holder`, `grun.lock/0`): aplicación, pid, entrada (opcional) y desde cuándo, en JSON, escrito **dentro del
  mismo archivo y sobre el descriptor que tiene el `flock`** (truncar y escribir en el sitio). Nunca con
  `fsutil.atomic_write` ni `os.replace`: un archivo nuevo es otro inodo y daría dos titulares (invariante 5). El texto
  es informativo: el candado lo da el `flock`. Lectura del titular (`holder()`), tolerante a archivo vacío, a medias o
  de otro formato (gvoice actual, WMF con `flock(1)`, que no escriben nada).
- Docstring con «Copiado de gvoice@8a17618» y lo adaptado.
- Fuera: desalojo de Ollama y espera de memoria (GR-4), `worker.lock` y `queue.json.lock` (GR-3), `doctor` (GR-5).

## Acceptance

- [x] Invariante 1: dos subprocesos `hold()` sobre la misma ruta, con marcas de tiempo que no se solapan.
- [x] Invariante 2: subproceso que toma el candado y muere por SIGKILL; el padre lo obtiene a continuación.
- [x] Invariante 3: un titular lanza un hijo con `pass_fds=held_fds()`, se mata al titular y el candado sigue tomado
      hasta que acaba el hijo (el de gvoice `tests/test_engine_qwentts.py:361`, adaptado).
- [x] Invariante 5: análisis del código de `grun/` que falla si algo hace `unlink`, `remove` o `rmtree` sobre una ruta
      de candado; y `hold()` crea el archivo si falta.
- [x] Invariante 6 completa: la tabla de GR-1, ahora contra la ruta que usa `machine_lock`.
- [x] Titular: se escribe al tomar, se lee desde otro proceso, y un archivo vacío o con basura no rompe `holder()`.
- [x] Los tests de gvoice de `machine_lock`, adaptados, en `tests/`.
- [x] Check en verde.

## Files

`grun/machine_lock.py`, `tests/test_machine_lock.py` (y los tests de invariantes que hagan falta).

## Change log

- `grun/machine_lock.py`: copiado de gvoice@8a17618 (`hold`, `held_fds`, `busy`, `WaitCancelled`, mismo código
  `machine_lock.unavailable`); añadido `Holder`/`holder()` y `hold(app=, entry=)`, que escribe el titular
  `grun.lock/0` (`schema`, `app`, `pid`, `entry`, `since` en ISO UTC) con `ftruncate` + `pwrite` sobre el descriptor
  del `flock`, y lo vacía (`ftruncate`) al soltar, aún con el `flock`. Un fallo al escribir el titular no impide tomar
  el candado. `app` vale `"grun"` si no se pasa.
- `tests/test_machine_lock.py`: los de gvoice adaptados, más invariantes 1 (dos procesos, intervalos de reloj
  monótono), 2 (SIGKILL), 3 (hijo con `pass_fds=held_fds()` en su sesión, adaptado de
  `test_engine_qwentts.py:361` sin motor), 5 (análisis `ast` de `grun/` y `hold()` crea el archivo), 6 completa
  (la tabla de GR-1 con el archivo que crea `hold()`) y el titular. Sin `sleep` de espera: tuberías y señal `held`.

## Verification

- `bash .claude/gw/scripts/red-without-fix.sh "python3 -m unittest tests.test_machine_lock" grun/machine_lock.py`:
  rojo sin el módulo, verde con él.
- Check en verde: 99 tests (`unittest discover -s tests`, cinco pasadas seguidas sin fallos), `tests-after-main.py`,
  `ci-local.py --validate`.

Preguntas abiertas: van a [docs/questions.md](../questions.md), no aquí.
