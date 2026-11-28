<!-- galivelop-workflow v0.9.1 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-2447cc83-5kxr8j` |
| **Fase / tarea** | `0.1`, `0.2` y `0.3` (R4.1-R4.4) fusionadas en `main` (PR #5, `d6decec`, CI en verde). Retro de `0.3` decidida (P4 aplicada; P1 anotada para `0.4`). |
| **Último punto estable** | R6.2: protocolo `grun.run/1` publicado (doc, esquema, `RUN_SCHEMA` a `/1`, test que falla sin el cambio). Antes, R6.1 (4 leves), R5 (`grun.lock/1`) y 0.4 (barridos de `queue.py`, `machine_lock.py`, `fsutil.held`); detalle en `git log`. |
| **Siguiente paso** | `0.4` y `R5` fusionadas en `main` (PR #6, `c827879`, CI en verde, 2026-11-27). R6.1 y R6.2 hechas; en `0.5` queda la parte de GVE (otro repo: leer `grun.run/1`, pasar por el turno, D-3) ; `grun.trace/0` diferido (D-16, decidido 2026-11-28). La persona abre una sesión en GVE con `docs/protocol/grun.run.1.md` y `schemas/grun.run.1.json`. Pendiente de la persona: `flock(1)` en `ollamaQueue.ts` de WMF, prueba en la Deck y quitar conectores/MCP sin uso con `/context`. |
| **Check** | `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`: verde (385 tests). |

## Autoría

Ningún commit hace referencia a Claude: antes del primer commit de cada sesión,
`git config user.name "Álvaro García Graña"` y `git config user.email` con el correo de la cuenta de GitHub de la persona (no se escribe en el repo); `agentSignatures: false`.
La rama se reescribió el 2026-11-27 (autor y firmas) con permiso de la persona; `main` no se tocó.

## Para la próxima publicación

`0.1` (R1) con los tests de las invariantes 1-12.

## Hecho (5 últimas)

1. 2026-11-27 — R4.1: servidor base (`grun/server.py`): Host/Origin, tabla error→HTTP con tabla de la aplicación, rutas de cola y `health`, `serve.lock`/`serve.json` (sin revisar).
2. 2026-11-27 — R3.2: alias `GVOICE_STATE_HOME` retirado (gvoice ya usa `GALIVELOP_STATE_HOME`, confirmado por la persona).
3. 2026-11-27 — R3.3: revisión de bloque, 2 medios arreglados (`export` atómico con `.grun.old-<pid>`, `profile` ante JSON hondo) y leves a pending.md.
4. 2026-11-27 — R3.3: barrido de leves: fsutil.read_json_as (doctor, queue, vendor), leves de vendor.py y doctor.py (sin revisar)
5. 2026-11-27 — R3.1: `grun vendor` (`grun/vendor.py`), copia con manifiesto y huella sha256 y su verificación (sin revisar).

## Pendiente

Lo pendiente está en [`docs/records/pending.md`](records/pending.md); se añade y se quita allí.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recover.py --state`.
