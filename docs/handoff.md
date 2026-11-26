<!-- galivelop-workflow v0.9.1 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-efbc000f-ebqwiq` |
| **Fase / tarea** | `0.1` (R1): `GR-1` (soporte) hecho; siguiente `GR-2`. Rama de la sesión (contiene `main`). Presupuesto de compactaciones: 1 (llevamos 0). |
| **Último punto estable** | `GR-1`: paquete `grun/` (`paths`, `limits`, `errors`, `i18n`, `fsutil`, `log`, `locales`) copiado de gvoice@8a17618, 75 tests (invariantes 6 parcial, 10 parcial, 12). |
| **Siguiente paso** | Revisión de bloque del diff desde `main` (pasa de 1000 líneas; trailer `Findings:`), luego `GR-2` (candado de máquina: `gvoice/machine_lock.py` con titular y `held_fds`; invariantes 1, 2, 3, 5 y 6 completa). gvoice se lee clonado en `/home/user/zeldris/galivelop-voice-generator` (si no está: `git clone --depth 1` del repo público). R2 se hace en una sesión de gimg (D-17). |
| **Check** | `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`: verde. Por ahora solo `tests/test_ddd.py`, un test de marcador; los tests de invariantes llegan con R1. |

## Para la próxima publicación

`0.1` (R1): el paquete `grun` con los tests de las invariantes 1-12.

## Hecho (5 últimas)

1. 2026-11-26 — F0 cerrada: PR #1 a `main` (`3dcba99`), CI en verde; retro F0 decidida (Q-18..Q-22).
2. 2026-11-26 — F0: roadmap de versiones (`docs/roadmap.md`), enlazado desde §7 del DDD.
3. 2026-11-26 — F-1 cerrada: las 17 preguntas de §8 respondidas (todas con la recomendación) y pasadas a «Decisiones» del DDD (D-1..D-17).
4. 2026-11-26: DDD borrador 2 (F-1): corregido contra los repos vecinos (ruta del `gpu.lock`, cola en `<data>`, sin prioridades, desalojo de Ollama), ampliado (archivos de candado, interfaces, invariantes 1-14) y §8 en 17 preguntas.
5. 2026-11-26: se aplica Galivelop-workflow v0.9.1, con el DDD borrador 1 y la doble licencia (MIT + CC BY-NC-SA 4.0).

## Pendiente

Lo pendiente está en [`docs/records/pending.md`](records/pending.md); se añade y se quita allí.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recover.py --state`.
