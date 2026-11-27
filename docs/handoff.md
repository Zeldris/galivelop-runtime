<!-- galivelop-workflow v0.9.1 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `claude/release-v0.1.0` |
| **Fase / tarea** | `0.1` (R1) publicada: etiqueta `v0.1.0` en `90c468b` y release en GitHub. `0.2` (R3): R3.1 hecho y revisado. Presupuesto de compactaciones: 0 |
| **Último punto estable** | `v0.1.0` (`90c468b`), publicada el 2026-11-27. En `90c468b` no corre CI (push a `main`); el CI verde es el del PR #3, sobre `27b32c5` (mismo árbol). |
| **Siguiente paso** | Arreglar el test que falla con locale en español y el estado del README (`pending.md`), en rama y PR a `main`. Luego R3.2 (alias) cuando devuelva la sesión de gvoice (`session_01VdeHm9ESLr7pEB8izbfdt1`) y R3.3 (barrido de leves). |
| **Check** | `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`: verde en CI y con `LC_ALL=C.UTF-8` (294 tests); con `es_ES.UTF-8`, 1 falla. |

## Autoría

Ningún commit hace referencia a Claude: antes del primer commit de cada sesión,
`git config user.name "Álvaro García Graña"` y `git config user.email` con el correo de la cuenta de GitHub de la persona (no se escribe en el repo); `agentSignatures: false`.
La rama se reescribió el 2026-11-27 (autor y firmas) con permiso de la persona; `main` no se tocó.

## Para la próxima publicación

`0.1` (R1) con los tests de las invariantes 1-12.

## Hecho (5 últimas)

1. 2026-11-27 — R3.1: `grun vendor` (`grun/vendor.py`), copia con manifiesto y huella sha256 y su verificación (sin revisar).
2. 2026-11-27 — R1.4: worker (`grun/worker.py`), interfaz del motor, desalojo de Ollama y `ProfileLoader`, con tests de las invariantes 4, 9 y 11 (sin revisar).
3. 2026-11-27 — R1.3: cola (`grun/queue.py`) con los tests de las invariantes 7-10 y 12.
4. 2026-11-27 — R1.2: candado de máquina (`grun/machine_lock.py`) con titular `grun.lock/0` y tests de las invariantes 1-6.
5. 2026-11-27 — F0 cerrada (PR #1 en `main`); `0.1` empieza con el roadmap activado.

## Pendiente

Lo pendiente está en [`docs/records/pending.md`](records/pending.md); se añade y se quita allí.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recover.py --state`.
