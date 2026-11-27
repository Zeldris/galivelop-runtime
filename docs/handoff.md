<!-- galivelop-workflow v0.9.1 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-2447cc83-5kxr8j` |
| **Fase / tarea** | `0.1` (R1): R1.3 hecho (cola, ficha `docs/tasks/R1.3.md`); falta la revisión de bloque de R1.2+R1.3. Presupuesto de compactaciones: 0 |
| **Último punto estable** | R1.3 (`cb8d388` + este commit): `grun/queue.py` (`Queue`, transiciones, huérfanas con `orphanCount`, lotes, `move`, pausa, progreso, `held`) con los tests de las invariantes 7-10 y 12; 159 tests. Antes, R1.2 (`f63aca7`). |
| **Siguiente paso** | Revisión de bloque (diff desde `6470a30`, R1.2 + R1.3) con `gw-reviewer`; luego R1.4 (worker). |
| **Check** | `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`: verde (159 tests). |

## Autoría

Ningún commit hace referencia a Claude: antes del primer commit de cada sesión,
`git config user.name "Álvaro García Graña"` y `git config user.email` con el correo de la cuenta de GitHub de la persona (no se escribe en el repo); `agentSignatures: false`.
La rama se reescribió el 2026-11-27 (autor y firmas) con permiso de la persona; `main` no se tocó.

## Para la próxima publicación

`0.1` (R1) con los tests de las invariantes 1-12.

## Hecho (5 últimas)

1. 2026-11-27 — R1.3: cola (`grun/queue.py`) con los tests de las invariantes 7-10 y 12.
2. 2026-11-27 — R1.2: candado de máquina (`grun/machine_lock.py`) con titular `grun.lock/0` y tests de las invariantes 1-6.
3. 2026-11-27 — F0 cerrada (PR #1 en `main`); `0.1` empieza con el roadmap activado.
4. 2026-11-26 — F0: roadmap de versiones (`docs/roadmap.md`), enlazado desde §7 del DDD.
5. 2026-11-26 — F-1 cerrada: las 17 preguntas de §8 respondidas (todas con la recomendación) y pasadas a «Decisiones» del DDD (D-1..D-17).

## Pendiente

Lo pendiente está en [`docs/records/pending.md`](records/pending.md); se añade y se quita allí.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recover.py --state`.
