# Retro de 0.4 (R5, barrido de leves y protocolo `grun.lock/1`)

**Estado:** pendiente

Sesión: barrido de leves de `queue.py`, `machine_lock.py` y `fsutil.py`, protocolo `grun.lock/1` y revisión de bloque
(`c1a6e1b`..`1d22820`). Tres subagentes (`gw-worker` ×2, `gw-reviewer`), todos `sonnet`, 1,13 M de entrada; la sesión
principal, 43 llamadas, 4,71 M. `gw-selector` y `gw-orchestrate-dealer` funcionaron: ningún reparto se repitió y la
revisión no halló graves ni medios. La medición de `gw-opt-tokens` está en `.claude/gw/gw-opt-tokens.md`.

## Candidatos, por gravedad

**P1. Barrido de `ollama.py` (proyecto, tarea `R6.1`, antes de `0.5`).** `ollama.py` tiene 3 leves abiertos, los
que más; `0.4` no lo tocó. Lista para que elijas:
- `ollama.py:34`: una URL con ruta, query o fragmento produce peticiones mal formadas.
- `ollama.py:62` y `machine_lock.py:116`: `json.loads` sin `RecursionError`.
- `ollama.py:87`: `evict` no mira `should_cancel` entre modelos al descargar.
- De paso, `doctor.py:67` trata `busy() is None` como libre y no avisa (nació en este barrido).
Hecho cuando cada leve elegido tiene su test rojo sin arreglo y sale de `pending.md`.

**P2. Regla de `REVIEW.md` para tests con procesos hijo (proyecto).** El revisor halló un test que mata solo el
Python hijo y deja `flock(1)` con su `sleep 60` vivo y el candado tomado. Es criterio del revisor, no comprobable con un
guion: una línea en `REVIEW.md`: «Un test que lanza procesos hijo los mata por grupo (`start_new_session`) en el
cleanup.» Riesgo: ninguno. Los dos leves de tests de esta revisión (en `pending.md`) siguen aparte.

**P3. El gancho `Stop` pide commit por el ledger de métricas (flujo).** El gancho 3 pidió seis veces un commit solo
para `docs/metrics/ledger.jsonl`, que `AGENTS.md` prohíbe; cada vez costó un turno. Propuesta al flujo: que el gancho
ignore un árbol cuyo único cambio es el ledger.

**P4. El gancho `Stop` pide comprobar el CI tras cada commit, también de solo documentos (flujo).** Cuatro de las
cinco subidas de esta sesión añadieron un despertar (`send_later` + `ReadNotifications`, ~32 k arrastrados cada uno).
Propuesta al flujo: pedir la comprobación solo cuando el diff toca código, o una sola al cerrar el bloque.

**P5. Aplazada de `0.3` (títulos cortos en `pending.md`).** Sigue aplazada: con `grep | cut` basta mientras no
estorbe; se retoma si `pending.md` pasa de ~30 entradas (hoy 20).

## Para `Galivelop-workflow`

- P3 y P4 (ganchos `Stop`).
- `red-without-fix.sh` admite una sola orden: el worker dejó dos tests sin rojo comprobado. Propuesta: aceptar varias
  órdenes, o que el informe del worker liste los tests sin comprobar (lo hizo, pero a mano).

## Propuestas de skills del proyecto

Sin cambios: `gw-selector`, `gw-orchestrate-dealer`, `pr` y la revisión rindieron; `gw-opt-tokens` dio cuatro
propuestas, tres aplicadas y una (conectores/MCP) de tu cuenta.
