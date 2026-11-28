# Roadmap: versiones de `grun`

Reparto de la escalera de hitos del [DDD](design/ddd.md) (§7, R0-R6) en versiones de `grun`, con las decisiones
D-1..D-17. Lo que se hace en otro repo (gimg, gvoice, WMF, GVE) no es una versión de `grun`: se apunta en la versión
de `grun` que lo hace posible.

Mientras la versión sea `0.x`, cada versión menor puede romper la interfaz de Python; los esquemas `grun.*/N` con
N ≥ 1 no cambian nunca (invariante 14). Cada versión se cierra con su check en verde, las tres fases antes de `main` y
una etiqueta `vX.Y.0`.

| Versión | Hito | Qué trae | Se da por cerrada cuando |
|---|---|---|---|
| — (F0) | R0 | DDD con D-1..D-17, estado actual verificado, este roadmap. Sin código | La persona aprueba el PR a `main` |
| — (en gimg) | R2 | gimg copia `machine_lock.py` de gvoice («Copiado de gvoice@<sha>») y pasa `held_fds` a sd.cpp (D-17). Va antes que `0.1` | Prueba en la Deck (persona) |
| `0.1` | R1 | El paquete `grun` (ver la sección `0.1`) con los tests de las invariantes 1-12 | Tests en verde |
| `0.2` | R3 | Lo que pida gvoice al vendorizar `grun`: herramienta de vendorizado con huella sha256, alias `GVOICE_STATE_HOME` retirado (D-1), script de desalojo de gvoice retirado (D-7) | Tests de gvoice en verde con `grun` vendorizado e invariante 13 |
| `0.3` | R4 | Base del servidor local (D-2), lanzador opcional `maybe_launch` (D-11), los ganchos de cola que necesita la imagen (D-6), `gimg doctor` llama a `grun doctor` (D-15). gimg borra su copia de `machine_lock.py` | Tests de gimg en verde con `grun` vendorizado e invariante 13 |
| `0.4` | R5 | Turno de Ollama: protocolo `grun.lock/1` publicado (D-13) e integración de `flock(1)` en `ollamaQueue.ts` de WMF (D-3) | Prueba de imagen, voz y texto a la vez en la Deck (persona) |
| `0.5` | R6 | `grun.run/1` que lee GVE (D-13); GVE pasa por el turno (D-3); decisión sobre `grun.trace/0` (D-16) | GVE lo consume |
| `1.0` | — | Interfaz de Python estable: la primera versión tras `0.5` en la que no ha hecho falta romperla | La persona lo decide |

## `0.1` «Paquete grun» (R1)

R1 es la extracción entera y no cabe en una sola tarea. Se parte en pasos con su propio commit, en este orden (cada
uno usa los anteriores). El estado se marca con `python3 .claude/gw/scripts/roadmap.py done <id>`.

| Id | Paso | Estado |
|---|---|---|
| R1.1 | **Soporte:** rutas (D-1, con `GALIVELOP_STATE_HOME` y el alias `GVOICE_STATE_HOME`), límites, errores con i18n y los códigos de D-14, escritura atómica y registro | hecho (2026-11-27) |
| R1.2 | **Candado de máquina:** el `machine_lock` de gvoice, con su titular y `held_fds` | hecho (2026-11-27) |
| R1.3 | **Cola:** la de gvoice más lo general de gimg (D-6): lotes, `move`, pausa, progreso, vista previa, `held`; orden por posición y luego id (D-4); `<data>/queue.json` sin migrar (D-10); huérfanas con `orphanCount` (D-5) | hecho (2026-11-27) |
| R1.4 | **Worker:** interfaz `Engine.run` (D-9), desalojo de Ollama al tomar el candado (D-7) y espera de memoria cancelable dentro del candado (D-8), con `ProfileLoader` sobre `machine_profiles/` (D-12) | hecho (2026-11-27) |
| R1.5 | **`grun doctor`** (D-15) | hecho (2026-11-27) |

El desalojo entra en `0.1`, no en `0.4`: gvoice retira su script en R3 (D-7) y necesita que `grun` ya lo haga.
`0.4` solo añade el turno de Ollama para los procesos que no son Python.

## `0.2` «Vendorizado» (R3)

| Id | Paso | Estado |
|---|---|---|
| R3.1 | **`grun vendor`:** copia con `VENDOR.json` y huella sha256, y su verificación (`docs/tasks/R3.1.md`) | hecho (2026-11-27) |
| R3.2 | **Alias `GVOICE_STATE_HOME` retirado** (D-1), cuando gvoice ya use `GALIVELOP_STATE_HOME` | hecho (2026-11-27) |
| R3.3 | **Barrido de leves:** función común de lectura de JSON que da el código `bad_*` ante `RecursionError`/`OSError` (`doctor`, `queue`, `vendor`), más los leves de `doctor.py` y `vendor.py` de `pending.md` | hecho (2026-11-27) |

## `0.3` «Servidor y lanzador» (R4)

Solo lo que vive en este repo; lo de gimg (borrar copias, `gimg doctor` que llama a `grun.doctor.diagnose`, usar el
servidor y el lanzador) lo hace la persona o una sesión en gimg, y se apunta en `pending.md`. Fuentes leídas de gimg
(solo lectura): `service.py` (`maybe_launch_worker`, l.190-217), `server.py` (tabla error→HTTP l.44-93, `_check_origin`
l.275-286, rutas de cola, `health` l.381-390).

| Id | Paso | Estado |
|---|---|---|
| R4.1 | **Servidor base** (`grun/server.py`, D-2): bind solo a `127.0.0.1`, comprobación de `Host`/`Origin`/`Sec-Fetch-Site` (`net.non_local_host`, invariante 11), `serve.lock` + `serve.json`, tabla error→HTTP genérica con tabla de la aplicación inyectable, `health` y rutas de cola (listar, vista previa, cancelar, mover, lotes, pausa, `clear`) | hecha (`docs/tasks/R4.1.md`) |
| R4.2 | **Ganchos de cola** (D-6): `Checks` (validación antes de encolar) y `Estimate` (`estimateMs` en la vista); `held` y `clean_pending` ya existen | hecho (2026-11-27) |
| R4.3 | **Lanzador** (`grun/launcher.py`, D-11): `maybe_launch(queue, command, log, ...)` desde `maybe_launch_worker`, con la cola y el comando inyectados | hecha (`docs/tasks/R4.3.md`) |
| R4.4 | **Invariante 13:** respuestas de `/api/queue` fijadas como ejemplo y validadas contra `grun.queue/0` | hecha (`docs/tasks/R4.4.md`) |

Bloqueo externo: R2 (gimg con `machine_lock.py` y `held_fds`) no está en el checkout de gimg; sin él, «gimg borra su
copia de `machine_lock.py`» no tiene objeto y la prueba de gimg de la versión no se puede dar.

## `0.5` «GVE» (R6)

| Id | Paso | Estado |
|---|---|---|
| R6.1 | **Barrido de `ollama.py`:** URL con ruta/query/fragmento rechazada, `evict` mira `should_cancel` antes de cada descarga, `holder` ante JSON hondo, `doctor` avisa de `busy()` desconocido | hecho (2026-11-28) |

## Bloqueos externos

- La validación con gart espera a que gart tenga su registro; `gmod.machine/0` espera a gmod. Ninguno bloquea
  `0.1`-`0.3` (D-12).
- Las prioridades entre aplicaciones son de galivelop-forge (D-4) y no tienen versión aquí.
