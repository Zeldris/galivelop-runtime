# Retro cierre de `0.2` (R3) (2026-11-27)

**Estado:** decidida el 2026-11-27 (la persona aprueba las recomendaciones): P1 aprobada y aplazada a `0.3`, P2 aprobada y apuntada como pendiente de la persona, P3 aprobada y dejada en esta retro para `gw-harvest`.

Sesión tras el `/clear`: R3.2 revisado en sesión (diff trivial: ≈10 líneas de código, correcto, el test falla sin el
arreglo) y fase 2. R3.1 y R3.3 ya tuvieron revisión de bloque y retro (`retro-2026-11-27-r3-1.md`).

## Medidas (`gw-opt-tokens`)

- 6 llamadas, contexto medio 90 671, 544 k de entrada (96 % de caché); arranque fijo ~80 171 por llamada (88 %).
- Sin lecturas repetidas, sin imágenes, sin subagentes. Propuesta de ahorro: ninguna.
- Referencia apuntada en `.claude/gw/gw-opt-tokens.md` (aprobada por la persona).

## Propuestas

1. **Barrido de leves para `0.3`** (del proyecto). `pending.md` guarda 15 entradas; el script con más leves abiertos
   es `grun/queue.py` (4 menciones: `stop_batch` sin `type(batch_id) is int`, entre otras de R1.2+R1.3), luego
   `ollama.py` (3: URL con ruta, `evict`, `j…`) y `machine_lock.py` (3: `busy()` con EACCES). Una tarea de la
   letra R que limpie `queue.py` y, si cabe, `machine_lock.py` (comparten el candado y la cola). `handoff.py next-id`
   no sirve aquí (no hay `plan` en `gw.json`): el id lo da el roadmap. Riesgo: ninguno si cada leve lleva su test del
   motivo; la persona elige cuáles entran.
2. **D-7 del lado de gvoice** (del proyecto, fuera de este repo). El script de desalojo de gvoice sigue en su
   repo; `grun` ya desaloja. Falta que la sesión de gvoice lo retire y confirme los tests de gvoice con `grun`
   vendorizado (criterio de salida de `0.2`). Hasta entonces, `0.2` figura como «pendiente de comprobar en gvoice» en
   el plan: lo comprueba la persona o la sesión de gvoice, no los tests de aquí.
3. **Del flujo** (general): el gancho `Stop` pide commitear el ledger de métricas aunque `AGENTS.md` lo prohíba, y
   cada sesión lo vuelve a discutir. Que el gancho ignore un árbol cuyo único cambio sea `docs/metrics/ledger.jsonl`.

## Skills del proyecto

`gw-selector`, `gw-opt-tokens` y `retro` funcionaron sin fallos en esta sesión; no hay cambio que proponer.

## Para Galivelop-workflow

- P3.
