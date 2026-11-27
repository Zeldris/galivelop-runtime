<!-- galivelop-workflow v0.9.1 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-2447cc83-5kxr8j` |
| **Fase / tarea** | `0.1` (R1): R1 completo (R1.1-R1.5); R1.5 revisada (1 medio arreglado, leves en pendientes). Presupuesto de compactaciones: 0 |
| **Último punto estable** | este commit: arreglo de la revisión de R1.5 (`doctor` no lanza con carpeta sin permiso). Antes, `grun doctor` (`fd52a9f`). |
| **Siguiente paso** | Revisión de R1 cerrada; comprobar el CI de este commit y empezar `0.2` (R3: vendorizado de `grun` en gvoice) según `docs/roadmap.md`. Antes de `main`, las fases 2 y 3. |
| **Check** | `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`: verde (277 tests). |

## Autoría

Ningún commit hace referencia a Claude: antes del primer commit de cada sesión,
`git config user.name "Álvaro García Graña"` y `git config user.email` con el correo de la cuenta de GitHub de la persona (no se escribe en el repo); `agentSignatures: false`.
La rama se reescribió el 2026-11-27 (autor y firmas) con permiso de la persona; `main` no se tocó.

## Para la próxima publicación

`0.1` (R1) con los tests de las invariantes 1-12.

## Hecho (5 últimas)

1. 2026-11-27 — R1.4: worker (`grun/worker.py`), interfaz del motor, desalojo de Ollama y `ProfileLoader`, con tests de las invariantes 4, 9 y 11 (sin revisar).
2. 2026-11-27 — R1.3: cola (`grun/queue.py`) con los tests de las invariantes 7-10 y 12.
3. 2026-11-27 — R1.2: candado de máquina (`grun/machine_lock.py`) con titular `grun.lock/0` y tests de las invariantes 1-6.
4. 2026-11-27 — F0 cerrada (PR #1 en `main`); `0.1` empieza con el roadmap activado.
5. 2026-11-26 — F0: roadmap de versiones (`docs/roadmap.md`), enlazado desde §7 del DDD.

## Pendiente

Lo pendiente está en [`docs/records/pending.md`](records/pending.md); se añade y se quita allí.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recover.py --state`.
