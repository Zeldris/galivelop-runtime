<!-- galivelop-workflow v0.9.1 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-efbc000f-ebqwiq` |
| **Fase / tarea** | F-1: mejorar, ampliar y cerciorar el DDD (`docs/design/ddd.md`). Después, F0: llevar lo decidido a `main` y repartirlo en versiones. |
| **Último punto estable** | Flujo Galivelop-workflow v0.9.1 aplicado, el DDD (borrador 1) en `docs/design/ddd.md` y las licencias. |
| **Siguiente paso** | F-1: repasar el DDD contra gimg/gvoice (añadir los repos a la sesión), cerrar las preguntas de §8 con la persona en `docs/questions.md` y pasarlas a «Decisiones». |
| **Check** | `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`: verde. Por ahora solo `tests/test_ddd.py`, un test de marcador; los tests de invariantes llegan con R1. |

## Para la próxima publicación

Flujo + DDD revisado, en F0 (PR a `main`), cuando F-1 cierre §8.

## Hecho (5 últimas)

1. 2026-11-26: se aplica Galivelop-workflow v0.9.1, con el DDD borrador 1 y la doble licencia (MIT + CC BY-NC-SA 4.0).

## Pendiente

Lo pendiente está en el archivo de `pendingFile` (`.claude/gw.json`; por defecto `docs/records/pending.md`): decisiones de la persona que bloquean algo, problemas conocidos, ideas sin planificar. Se añade y se quita allí; `handoff.py move-pending` rehace esta línea y `handoff.py add-pending "texto"` añade sin leer el archivo.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recover.py --state`.
