# Retro: cierre de `0.3` (R4.1-R4.4)

**Estado:** decidida: P4 aprobada y aplicada; P3 aprobada (queda para el workflow); P1 aprobada y anotada para `0.4`; P2 aplazada.

Fuentes: `measure.py` del tramo tras el último `/clear` (10 llamadas, contexto medio 91 983, 920 k de entrada, 97 % de caché; arranque fijo ~80 510 por llamada, 88 %), `pending.md`, `git log origin/main..HEAD`. `task.py deviations` no da nada: no hay `plan` en `gw.json`. No hay `.claude/gw/retro.md`.

## Gasto (`gw-opt-tokens`)

- El tramo es corto y casi todo es arranque fijo (88 %): lo único que lo baja es hacer menos llamadas; los conectores no se pueden quitar (ya apuntado).
- `pending.md` se leyó 3 veces (1 213 tok, 10 199 arrastrados): es el mayor resultado del tramo.
- Sin subagentes, sin imágenes, sin ficheros grandes repetidos.

## Candidatos, por gravedad

**P1. Barrido de leves en `queue.py` como tarea `R5.1` (proyecto).** `queue.py` suma 6 leves abiertos (`stop_batch` con `True==1`, `enqueue` con generadores, `_number` acepta `inf`, poda por llegada, `checks` que devuelve `""`, `items` recorrido dos veces) y el bloque R4 lo tocó. Propuesta: una tarea para `0.4` que los cierre, con un test rojo sin arreglo cada uno. La persona elige cuáles entran. Después, `machine_lock.py` (3 leves) como segunda opción.

**P2. `pending.md` con una línea corta por entrada (proyecto).** Cada entrada mide hasta 1 000 caracteres y `grep -n '^- '` los vuelca enteros. Propuesta: un título de ≤120 caracteres por entrada (qué y dónde) y el detalle en la línea siguiente, para que `grep` devuelva solo títulos. Ahorro: ~900 tokens por lectura y arrastre. Riesgo: ninguno; costo: reescribir 18 entradas una vez.

**P3. Gancho `Stop` que pide commitear el ledger (workflow).** Se contradice con `AGENTS.md` («no se hace un commit solo para el ledger»): cada fin de turno con solo `ledger.jsonl` modificado fuerza a explicar por qué no se commitea. Propuesta al workflow: que el gancho ignore el cambio si solo toca `docs/metrics/ledger.jsonl`.

**P4. Skills del flujo (workflow).** `gw-selector` y `retro` funcionaron; `handoff.py next-id` falla sin `plan` en `gw.json` y el `taskId` por defecto (`[A-Z]{2,5}-\d+`) no casa con los ids `R4.1` del proyecto. Propuesta: fijar `plan` y `taskId` en `.claude/gw.json` (proyecto) para que `next-id` y `task.py` funcionen.

## For Galivelop-workflow

- P3: el gancho `Stop` ignora un árbol sucio cuyo único cambio es el ledger de métricas.

## Decisión

La persona aprobó las recomendaciones (5-8): P1 anotada en `pending.md` para una tarea de `0.4` sin tocar `queue.py` ahora; P2 aplazada; P3 en `## For Galivelop-workflow`; P4 aplicada (`plan: ["docs/roadmap.md"]`, `taskId: R\d+\.\d+` en `gw.json`; `handoff.py next-id` pide el prefijo con punto, p. ej. `R5.`).
