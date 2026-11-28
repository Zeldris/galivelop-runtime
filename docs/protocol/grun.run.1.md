# Protocolo `grun.run/1`

El resumen de una ejecución terminada, pensado para `galivelop-evaluator` (GVE), que lo lee como medida
determinista (duraciones, esperas y fallos). Esquema: [`schemas/grun.run.1.json`](../../schemas/grun.run.1.json).
Decisión: DDD D-13 (`grun.run/1` en R6). Solo describe lo que hace hoy `grun/worker.py`.

## Dónde está

Una línea JSON por entrada cerrada, añadida al final del registro JSONL de la aplicación (`log_path` del `Worker`,
con `grun.log.append`: bajo candado de archivo, claves ordenadas). Comparte archivo con las líneas de eventos
(`EntryClaimed`, `LockAcquired`, `EntryFinished`…): **las de eventos llevan `event` y no `schema`**; el resumen lleva
`schema` y no `event`. Un lector filtra por `schema == "grun.run/1"` e ignora el resto, y salta las líneas que no
son JSON (el registro tolera una línea a medias). Si el worker no tiene `log_path`, no hay resumen. El registro es
de mejor esfuerzo: un fallo al escribirlo no cambia el resultado de la entrada (`worker.log_failed` a stderr).

## Campos

| Campo | Tipo | Significado |
|---|---|---|
| `schema` | `"grun.run/1"` | Versión. |
| `app` | texto | Aplicación dueña de la cola. |
| `entry` | texto o entero | Id de la entrada. |
| `state` | `done`, `failed` o `cancelled` | Estado final **tal como quedó en la cola**: si la cola rechazó `cancelled` sin petición de cancelar, es `failed` con `worker.unexpected`. |
| `errorCode` | texto o `null` | Código del error (`engine.timeout`, `worker.unexpected`…); `null` si `done` o `cancelled`. |
| `lockWaitMs` | entero ≥ 0 | Espera por el candado de máquina. |
| `memoryWaitMs` | entero ≥ 0 | Espera por memoria libre; 0 si no esperó. |
| `runMs` | entero ≥ 0 | Duración total de la entrada en el worker, **espera incluida** (de `EntryClaimed` a cerrar), no solo el motor. |

El tiempo de motor es `runMs − lockWaitMs − memoryWaitMs` (con el desalojo de Ollama dentro de ese resto).

## De `grun.run/0` a `grun.run/1`

Es el paso previsto en D-13 (R6: lo consume GVE, fuera de Python). **Qué cambia: solo el valor de `schema`**
(`grun.run/0` pasa a `grun.run/1`) y que el formato queda publicado (este documento y su esquema). Los campos y
sus tipos son los mismos. Nada de este repo compara el campo `schema` al leer. Un lector externo que exigiese
`grun.run/0` tiene que aceptar también `/1`; ante una versión que no conozca, ignora la línea, no falla. Los
archivos de registro viejos conservan líneas `/0`: un lector que quiera el histórico acepta ambas.

## Fuera

- `grun.trace/0` (traza por pasos de un intento): diferido por decisión D-16 (2026-11-28), hasta que GVE pida el detalle por intento.
- Que GVE pase por el turno de la máquina (D-3): integración en el repo de GVE, no aquí.
