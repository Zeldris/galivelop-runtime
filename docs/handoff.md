<!-- galivelop-workflow v0.9.1 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-efbc000f-ebqwiq` |
| **Fase / tarea** | F-1: mejorar, ampliar y cerciorar el DDD (`docs/design/ddd.md`). Después, F0: llevar lo decidido a `main` y repartirlo en versiones. |
| **Último punto estable** | DDD borrador 2 (`docs/design/ddd.md`), comprobado contra gimg, gvoice, gart, gmod, forge y WMF; lo comprobado, en `docs/design/estado-actual.md`. Las 17 preguntas de §8, en `docs/questions.md` (Q-1..Q-17). |
| **Siguiente paso** | F-1: la persona responde Q-1..Q-17 (`questions.py answer "1. ok, …"`); pasar las respuestas a «Decisiones» del DDD y a `docs/records/decisions.md`. Luego F0. |
| **Check** | `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`: verde. Por ahora solo `tests/test_ddd.py`, un test de marcador; los tests de invariantes llegan con R1. |

## Para la próxima publicación

Flujo + DDD revisado, en F0 (PR a `main`), cuando F-1 cierre §8.

## Hecho (5 últimas)

1. 2026-11-26: DDD borrador 2 (F-1): corregido contra los repos vecinos (ruta del `gpu.lock`, cola en `<data>`, sin prioridades, desalojo de Ollama), ampliado (archivos de candado, interfaces, invariantes 1-14) y §8 en 17 preguntas.
2. 2026-11-26: se aplica Galivelop-workflow v0.9.1, con el DDD borrador 1 y la doble licencia (MIT + CC BY-NC-SA 4.0).

## Pendiente

Lo pendiente está en [`docs/records/pending.md`](records/pending.md); se añade y se quita allí.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recover.py --state`.
