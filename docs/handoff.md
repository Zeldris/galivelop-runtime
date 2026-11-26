<!-- galivelop-workflow v0.9.1 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-efbc000f-ebqwiq` |
| **Fase / tarea** | F0: llevar lo decidido en F-1 a `main` (PR) y repartirlo en versiones. F-1 cerrada el 2026-11-26. |
| **Último punto estable** | F0: R0-R6 repartidos en versiones en [`docs/roadmap.md`](roadmap.md) (R2 en gimg antes de `0.1`; `0.1`=R1 en 5 pasos … `0.5`=R6; `1.0` lo decide la persona). |
| **Siguiente paso** | F0: `reviewed.sh`, descripción del PR con la skill `pr` y PR a `main` cuando la persona lo confirme. Retro F0 decidida (Q-18..Q-22). |
| **Check** | `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`: verde. Por ahora solo `tests/test_ddd.py`, un test de marcador; los tests de invariantes llegan con R1. |

## Para la próxima publicación

Flujo + DDD revisado, en F0 (PR a `main`), cuando F-1 cierre §8.

## Hecho (5 últimas)

1. 2026-11-26 — F0: roadmap de versiones (`docs/roadmap.md`), enlazado desde §7 del DDD.
2. 2026-11-26 — F-1 cerrada: las 17 preguntas de §8 respondidas (todas con la recomendación) y pasadas a «Decisiones» del DDD (D-1..D-17).
3. 2026-11-26: DDD borrador 2 (F-1): corregido contra los repos vecinos (ruta del `gpu.lock`, cola en `<data>`, sin prioridades, desalojo de Ollama), ampliado (archivos de candado, interfaces, invariantes 1-14) y §8 en 17 preguntas.
4. 2026-11-26: se aplica Galivelop-workflow v0.9.1, con el DDD borrador 1 y la doble licencia (MIT + CC BY-NC-SA 4.0).

## Pendiente

Lo pendiente está en [`docs/records/pending.md`](records/pending.md); se añade y se quita allí.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recover.py --state`.
