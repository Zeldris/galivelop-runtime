<!-- galivelop-workflow v0.9.1 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-2447cc83-5kxr8j` |
| **Fase / tarea** | `0.1` (R1) y `0.2` (R3) fusionadas en `main` (PR #4, `e1277d7`). `0.3` (R4) repartida en R4.1-R4.4 (`docs/roadmap.md`): R4.1 y R4.2 hechas y revisadas (2 medios arreglados, leves en `pending.md`); R4.3 y R4.4 hechas y revisadas (bloque sin hallazgos graves ni medios; 5 leves en `pending.md`). Presupuesto de compactaciones: 1 |
| **Último punto estable** | R4.4: invariante 13, esquema `schemas/grun.queue.0.json` y ejemplos de `/api/queue` (`docs/tasks/R4.4.md`), sobre R4.3 (lanzador). |
| **Siguiente paso** | La persona confirmó (1-4): decisiones del agente aceptadas, ningún leve entra, `requires-python` ≥3.10, ir a `main`. Fase 2 en curso: `gw-opt-tokens` y `retro` (presentar a la persona), luego fase 3 (`reviewed.sh`, push, PR con skill `pr`). gimg sin `machine_lock.py` y D-7 en gvoice siguen pendientes de la persona. |
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
