# Estado actual verificado (F-1, 2026-11-26)

Lo que hay hoy en los repos vecinos y en lo que se apoya el [DDD](ddd.md). Se comprobó leyendo clones superficiales
(un solo commit) de cada repo, sin ejecutar nada. Rutas: `G/` = `galivelop-image-generator/gimg/`,
`V/` = `galivelop-voice-generator/gvoice/`, `WMF/` = `World-Maker-Fantasy/`.

## Correcciones al borrador 1

| Borrador 1 decía | Lo que hay | Prueba |
|---|---|---|
| El `gpu.lock` está «en el state de gvoice», así que gimg no lo vería | Ya está en la carpeta común de la marca: `$GVOICE_STATE_HOME`, si no `$XDG_STATE_HOME/galivelop/gpu.lock`, y si no `~/.local/state/galivelop/gpu.lock`. gimg podría calcular la misma ruta; lo que pasa es que no la toma. | `V/paths.py:46-63`, gvoice `docs/plan.md:23` (D8) |
| La cola vive en `<state>/queue.json` | Vive en `<data>/queue.json`, con `queue.paused` y `worker.log` al lado | `G/queue.py:62`, `V/queue.py:51` |
| «D7» y «D8», sin más | Son decisiones de **gvoice**. En gimg, D7 y D8 significan otra cosa («WMF es el piloto» y «pedido, no encargo») | gvoice `docs/plan.md:22-23`, gimg `docs/plan.md:19-20` |
| `running→cancelled` es una transición directa | Una entrada que corre recibe la marca `cancelRequested`. El worker la lee y cierra con `finish(cancelled)`, y la recuperación de huérfanas también la respeta | `G/queue.py`, `V/queue.py` (`cancel`, `finish`, `_recover`) |
| Hay prioridades (§8.4) | No hay prioridades en ninguna de las dos. gimg ordena por `position` y luego por id; gvoice, por el id más bajo | `G/queue.py` (`_pos`), `V/queue.py` (`_first_queued`) |
| La huérfana se detecta porque «su worker no está vivo» | Se detecta con un `flock` sobre `<data>/worker.lock`, que se sondea con `LOCK_SH\|LOCK_NB`; el `pid` es solo informativo. Una huérfana vuelve a la cola sin límite de veces | `_no_worker`, `_txn(recover=True)` en las dos colas |
| `compose` es un gancho de la cola | Es parte del worker de gimg (`worker._generate`). La cola solo valida plantillas | `G/worker.py`, `G/queue.py` (`check_specs`) |
| `trace` es un módulo de soporte que se extrae | `G/trace.py` es un vectorizador de mapa de bits a SVG. No existe ninguna traza por pasos: `grun.trace/0` sería todo nuevo | `G/trace.py` |
| `grun` «deja de tener `machine_profiles/` propios» | `grun` nunca los tuvo: los tienen gimg y gvoice, con esquemas distintos | `G/machine_profiles/steam-deck.json`, `V/machine_profiles/steam-deck.json` |
| El motor es `Engine.run(entry, on_progress, should_cancel)` | gimg: `Engine.generate(job, should_cancel)`, con `on_progress` dentro del `job`. gvoice: `design`, `line` y `voiceprint(job, should_cancel)`, sin progreso ni vista previa | `G/engine.py`, `V/engine.py:130-140` |
| Los consumidores vendorizan `grun` «igual que gart» | Ni gimg ni gvoice usan gart todavía, y gart aún no tiene código: es un patrón decidido, no un ejemplo que ya funcione | `galivelop-artifacts/docs/adr/0002` |
| WMF «es TypeScript» | El backend que llama a Ollama es TypeScript (Node/Fastify). El repo también tiene unos 127 `.py` de QA y herramientas, y scripts de shell | `WMF/backend/src/lib/ollama.ts` |

## Confirmado

- Tamaños: `G/queue.py` tiene 680 líneas, `V/queue.py` 433 y `G/server.py` 1124. Otros: `V/server.py` 235,
  `G/worker.py` 475, `V/worker.py` 346 y `V/machine_lock.py` 78.
- Marcas «Copiado de gimg@…»: solo están en gvoice, con los commits `fa1076e`, `4365f9a`, `46248251` y `47bd0a9`.
  Todas las copias han divergido; las que más, `queue`, `worker`, `server`, `orders` y `cli`. No se puede comprobar
  que esos commits existan, porque el clon de gimg es superficial.
- `V/machine_lock.py`:
  - es `hold(should_cancel, on_wait, poll_s=0.05)`, un gestor de contexto;
  - expone `WaitCancelled`, `held_fds()` y `busy()`;
  - usa `flock` con `LOCK_EX|LOCK_NB` en un bucle de sondeo;
  - nunca borra el archivo (lo comprueba `tests/test_machine_lock.py:66`);
  - su error es `machine_lock.unavailable`.

  No escribe **ningún dato del titular** en el archivo, así que `Holder` y `grun.lock/0` son trabajo nuevo.
- `held_fds` pasa al motor con `pass_fds` (`V/engine_qwentts.py:221`). Así, un proceso hijo huérfano sigue teniendo
  el candado (`tests/test_engine_qwentts.py:361`).
- gimg no toma ningún candado de máquina. Solo tiene `worker.lock`, `queue.json.lock` y `serve.lock`.
- Los estados son `queued|running|done|failed|cancelled` en las dos.
- `_txn` funciona igual en las dos: `flock` sobre `queue.json.lock`, y no escribe si nada cambió.
- La escritura atómica usa `mkstemp` en el mismo directorio, `fsync` del archivo y `os.replace`
  (`G/fsutil.py:23-40`). No hace `fsync` del directorio.
- Las dos guardan solo las 200 últimas entradas terminadas (`KEEP_TERMINAL`).
- Las dos usan Python ≥ 3.10, solo stdlib, y el servidor en `127.0.0.1` comprueba la cabecera `Host`.

## Lo que el borrador 1 no contaba

- **gimg ya tiene una guarda de Ollama:** `engine.ollama = abort|unload|ignore`, con `GIMG_OLLAMA_URL` y por
  defecto `localhost:11434` (`G/engine_sdcpp.py:38-40, 189-215, 365-377`). gvoice, por su parte, descarga los modelos
  de Ollama a mano desde un script (`voice-generator/scripts/comun.sh:23-31`, con `keep_alive:0`). **Hoy la
  contención se resuelve sacando modelos de la memoria, no con un candado.**
- **gvoice espera a tener memoria libre con el candado ya tomado:** si no hay `MemAvailable ≥ minFreeMemoryMb`,
  espera, y esa espera se puede cancelar con `WaitCancelled` (`V/worker.py:125`). Antes de limpiar sus carpetas de
  trabajo comprueba que nadie tenga el candado (`machine_lock.busy()`, `V/worker.py:335`).
- **Cada aplicación tiene ya tres candados propios:** `worker.lock`, `queue.json.lock` y, en gimg, `serve.lock`.
  Ninguno se borra nunca.
- **Recuperación sin repetir trabajo:** `orders.add_attempt(entry_id=…)` y `attempt_for_entry` hacen que una
  huérfana que vuelve a la cola no genere dos veces lo mismo. gimg además retoma una imagen que quedó a medio
  componer (`G/worker.py:6-7`).
- **Lo que solo tiene gimg:**
  - `move` y `move_batch` (`up|down|top`), `cancel_batch` y `stop_batch`;
  - la pausa (`queue.paused`);
  - progreso y vista previa (`set_progress` y `set_preview`, que se sirven en `GET /api/queue/{id}/preview`);
  - entradas retenidas (`held`);
  - un servicio que arranca el worker solo (`G/service.py`, con `maybe_launch_worker`);
  - un `doctor.py` de 551 líneas;
  - la tabla que pasa cada código de error a un estado HTTP (`G/server.py:47-67`).
- **Lo que solo tiene gvoice:** `kind` (`voice|line|prints`), `take`, `enqueue_prints` y `production_model`; la
  espera de memoria; y en `paths` el caso de Flatpak, que ignora las variables XDG dentro de la caja de arena
  (`V/paths.py:15-27`).
- **Códigos de error en uso** que hay que respetar:
  - `queue.unknown|corrupt|not_cancellable|not_running|bad_state|bad_move|not_movable|batch_not_found|bad_progress`;
  - `worker.already_running|unexpected`, `engine.failed|timeout|low_memory` y `machine_lock.unavailable`;
  - `path.*`, de `check_relative`, que es igual en las dos.

  `invalid_transition`, `non_local_host` y `orphaned` no existen todavía.
- **Variables de entorno por aplicación:** `<APP>_{CONFIG,DATA,MODELS}_HOME`, `<APP>_MACHINE_PROFILE`,
  `<APP>_ENGINE`, `<APP>_LANG`, `<APP>_DEBUG`, `<APP>_FAKE_DELAY` y `<APP>_FAKE_FAIL`. gvoice tiene además
  `GVOICE_STATE_HOME`, que usan sus tests.
- **Interfaz de usuario:** las dos interfaces leen `/api/queue` cada cierto tiempo. Si cambia la forma de la entrada,
  las dos se rompen.
- **WMF:**
  - ya tiene una cola de Ollama dentro del proceso, con concurrencia 1 (`WMF/backend/src/lib/ollamaQueue.ts`), y un
    `queueTimeoutMs` de 150 s que deja avanzar la cola aunque un `fetch` se quede colgado;
  - Ollama se llama en `backend/src/lib/ollama.ts`, `embeddings.ts`, `retrieval.ts` y `routes/turn.ts`, con
    `OLLAMA_BASE_URL` (por defecto `http://localhost:11434`);
  - Node no tiene `flock` de serie;
  - en la Deck, `XDG_RUNTIME_DIR` puede faltar (`WMF/tools/qa/deck/ia-ronda.sh:30`).
- **GVE también usa Ollama** en `:11434` (comentarios de WMF), así que también tendría que pasar por el turno.
- **gart solo tiene documentos:** el DDD y los ADR 0001-0006.
  - Los tipos siguen la forma `^[a-z][a-z0-9]*\.[a-z][a-z0-9_.]*/(0|[1-9][0-9]*)$`.
  - Un esquema `/0` es provisional: puede cambiar sin migración y no lleva huella.
  - Uno `/n` con n ≥ 1 es estable.
  - Cada repo es dueño de su espacio de nombres sin registrarlo en ningún sitio, y nadie más ha reservado `grun`.
  - No está definido cómo se calcula la huella (bytes del archivo o JSON canónico).
- **gmod está vacío** (solo un README de una línea). `gmod.machine/0` no existe todavía. Los perfiles actuales no
  tienen un campo de VRAM ni un id de máquina; lo más parecido es `minFreeMemoryMb` y `watchMemoryMb`, y gimg tiene
  además `engine.maxVram`.
- **forge está vacío** (solo un README de una línea).
- **Plataforma:** todos los candados usan `fcntl`, así que solo funcionan en POSIX.
