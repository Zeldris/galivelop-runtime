# DDD: galivelop-runtime (borrador 2, 2026-11-26)

> Borrador 2 (F-1): corregido y ampliado tras comprobarlo contra gimg, gvoice, gart, gmod, forge y WMF. Lo
> comprobado, con sus rutas, está en [estado-actual.md](estado-actual.md). Las preguntas de §8 están respondidas
> (todas con su recomendación) y recogidas en «Decisiones» (D-1..D-17).

**Uso:** núcleo común de ejecución local para los generadores de Galivelop. Recoge lo que hoy está duplicado entre
gimg y gvoice. gvoice copió de gimg su núcleo genérico con la marca «Copiado de gimg@<sha>» (decisión D7 de gvoice),
y hoy las dos copias han divergido. Ese núcleo son la cola, el worker, las rutas, los límites, los errores, el
registro y la escritura atómica. Además completa dos piezas que existen solo a medias:
- el **candado de máquina** (decisión D8 de gvoice): hoy solo lo toma gvoice;
- el **turno de Ollama**: hoy la contención con Ollama se resuelve sacando sus modelos de la memoria, y WMF tiene su
  propia cola de Ollama dentro del proceso.

- **Nombre:** Galivelop Runtime · **paquete:** `grun` · **espacio de artefactos:** `grun`, del que este repo es el
  dueño y que nadie más ha reservado.
- **Visibilidad:** público · **stack:** Python ≥ 3.10, solo stdlib, solo POSIX (los candados son `fcntl.flock`;
  Windows queda fuera), y sin red fuera de `localhost`.
- **Depende de** (§8, P-12):
  - `galivelop-artifacts` (gart), para validar sus artefactos;
  - `galivelop-models` (gmod), por `gmod.machine/0`, el perfil de la máquina.

  **Ninguno de los dos tiene código todavía**: gart es solo documentos y gmod, un README. `grun` no puede esperar a
  ninguno para R1.
- **Cómo lo usan:** los consumidores en Python vendorizan `grun` (una copia con su versión y un test que compara su
  huella sha256), igual que decidió gart en su ADR 0002. Los consumidores en otros lenguajes siguen el protocolo
  publicado del candado (§8, P-3).

## 1. Propósito

Un trabajo pesado de IA local (imagen, voz, texto) se encola, espera a que la máquina esté libre, corre con un solo
dueño de la GPU, informa de su progreso y deja un registro. Todo esto pasa igual en cualquier aplicación de
Galivelop y sin que una aplicación tenga que saber nada de las demás.

**Éxito:**
1. gvoice y gimg borran sus copias del núcleo («Copiado de gimg@…» en gvoice, y los módulos de origen en gimg),
   usan `grun` vendorizado y sus tests siguen en verde. Sus interfaces, que leen `/api/queue`, siguen funcionando
   sin cambios.
2. En una Steam Deck se lanzan a la vez una imagen (gimg), una voz (gvoice) y una narración (Ollama de WMF). Nunca
   ocupan la GPU juntas, se ejecutan de una en una y ninguna falla por tener que esperar. Tampoco falla ninguna por
   memoria que deje ocupada la anterior (modelos de Ollama aún cargados).
3. Si un worker o el proceso hijo de su motor mueren a mitad de un trabajo, no dejan la máquina bloqueada ni el
   trabajo en «running» para siempre. Al recuperarse, el trabajo no se genera dos veces.

## 2. Lenguaje

| Término | Código | Significado |
|---|---|---|
| Pedido | `Order` | Lo que pide un proyecto: qué generar, con qué perfil y qué parámetros. Es el documento de la aplicación; `grun` solo lo lleva de un sitio a otro. |
| Intento | `Attempt` | Una ejecución de un pedido, con su semilla y su resultado. Un pedido tiene uno o más. Se crea de forma idempotente por entrada (`attempt_for_entry`), y por eso una recuperación no repite trabajo. |
| Entrada | `Entry` | Un intento puesto en la cola, con su estado, su posición y sus marcas (`cancelRequested`, `held`). |
| Lote | `Batch` | Las entradas de un mismo envío; se mueven, se cancelan o se paran juntas. Hoy es un campo `batch {id, index, size}` de la entrada (solo en gimg), no un objeto aparte. |
| Cola | `Queue` | La lista persistente de entradas de una aplicación (`<data>/queue.json`, con `{nextId, entries}`), cambiada solo por transacciones. |
| Estado | `EntryState` | `queued` → `running` → `done` \| `failed` \| `cancelled`. |
| Petición de cancelación | `cancelRequested` | La marca que pide parar una entrada que corre. El worker la lee y cierra la entrada como `cancelled`. |
| Worker | `Worker` | El proceso que reclama la siguiente entrada, la ejecuta con un motor y la cierra. Hay uno por aplicación, garantizado por `worker.lock`. |
| Lanzador | `Launcher` | Lo que arranca el worker cuando hay trabajo y nadie tiene `worker.lock` (hoy `G/service.py`). |
| Motor | `Engine` | El adaptador que hace el trabajo de verdad (sd.cpp, qwentts.cpp). Es de la aplicación, no de `grun`. |
| Candado de máquina | `MachineLock` | Un `flock` exclusivo sobre el `gpu.lock` común. Quien lo tiene es el único que usa la GPU en ese momento. |
| Titular | `Holder` | El proceso que tiene el candado ahora, con su aplicación, su entrada y desde cuándo. Lo escribe él mismo en el `gpu.lock` al tomarlo (`grun.lock/1`) y es solo información. |
| Espera | `Wait` | El tiempo que una entrada pasa sin poder correr: esperando el candado o, ya con él, a tener memoria libre. Se puede cancelar (`WaitCancelled`) y nunca cuenta como fallo. |
| Pausa | `Pause` | Una marca (`<data>/queue.paused`) que impide al worker reclamar entradas nuevas; la que está corriendo termina. |
| Huérfana | `Orphan` | Una entrada en `running` cuando nadie tiene `worker.lock`. Al recuperarla vuelve a la cola, queda `cancelled` si tenía `cancelRequested`, o se cierra como fallo (§8, P-5). |
| Progreso | `Progress` | Pasos hechos y totales, con un tiempo estimado (`{step, steps, etaS}`), más una vista previa si la hay, del intento que corre. |
| Error | `RunError` | Un código estable más sus parámetros. El texto se resuelve con i18n (es/en, `en` por defecto) al mostrarlo. |
| Límites | `Limits` | Topes de memoria, tamaño, número y duración, cargados del perfil de máquina. |
| Turno de Ollama | `OllamaTurn` | Una llamada a Ollama que pasa por el candado de máquina, para que el texto también haga cola. |
| Desalojo | `Evict` | Lo que hace el nuevo titular al tomar el candado: sacar de la memoria los modelos de Ollama que siguen cargados. Hoy es la guarda `engine.ollama=unload` de gimg (§8, P-7). |

## 3. Contextos acotados

1. **Cola** (núcleo): entradas, lotes, transacciones con bloqueo de archivo, pausa, movimientos, recuperación de
   huérfanas y poda de terminadas (`KEEP_TERMINAL=200`, sin reutilizar ids).
   - Viene de `gimg/queue.py` (680 líneas) y `gvoice/queue.py` (433), que han divergido.
   - Lo común entra en `grun`. Lo propio de cada aplicación entra por ganchos (`Checks`, `Estimate`,
     `PendingCleaner`), y su vocabulario, por campos libres de la entrada (`kind`, `take`, `mode`…).
   - Hoy las dos colas importan módulos de su aplicación (`orders`, `projects`, `engine`, `compose`, `failures`), y
     cortar esa dependencia es el trabajo principal de la extracción.
2. **Worker**: reclamar, esperar el candado y la memoria, ejecutar con el motor, informar del progreso, atender la
   cancelación y cerrar la entrada sin lanzar nunca una excepción.
   - Viene de los dos `worker.py`.
   - El motor llega como interfaz y `grun` no importa ninguno.
   - Incluye el lanzador opcional (de `gimg/service.py`).
3. **Candado de máquina**: `hold()`, la espera cancelable, `held_fds()` (para que el hijo del motor herede el
   candado), `busy()` y el titular.
   - Viene de `gvoice/machine_lock.py` (78 líneas, D8 de gvoice).
   - Añade la escritura informativa del titular.
4. **Turno de Ollama**: un cliente mínimo a `localhost:11434` que toma el candado alrededor de cada generación, y el
   desalojo de modelos de Ollama para los demás titulares (§8, P-7). Su cola es la espera del candado, no una cola
   propia.
5. **Soporte**:
   - `paths`: XDG con el caso de Flatpak, y variables `<APP>_*_HOME` por aplicación;
   - `limits`, `errors`, `i18n` (con sus `locales/{en,es}.json`) y `fsutil` (escritura atómica y candados);
   - `log`: el JSONL por proyecto, con `estimate`.
6. **Servidor local** (opcional, §8, P-2): la base HTTP de solo `localhost`.
   - Comprueba la cabecera `Host`, para que nadie entre por DNS rebinding.
   - Lleva la tabla que pasa de código de error a estado HTTP, más las rutas `health` y de cola: listar, cancelar,
     mover, pausar, progreso y vista previa.
   - Las rutas y pantallas de cada aplicación se quedan en su repo.
7. **Doctor**: `grun doctor` dice quién tiene el candado, qué espera, qué huérfanas hay y qué candados de aplicación
   están tomados. `gimg doctor` lo llama en vez de duplicarlo (§8, P-15).

**Mapa con los demás repos:**
- **`galivelop-artifacts` (gart):** núcleo compartido (shared kernel). `grun` publica sus tipos `grun.*/N` y los valida
  con gart cuando gart tenga código. Hasta entonces, los valida con sus propios tests (§8, P-12).
- **`galivelop-models` (gmod):** cliente-proveedor. `grun` leerá `gmod.machine/0` para los límites. Hasta que exista,
  lee los `machine_profiles/` de cada aplicación con un cargador que pone el consumidor (§8, P-12). Los perfiles de
  hoy (`minFreeMemoryMb`, `watchMemoryMb`, `timeoutS`, `engine.*`) son la entrada de gmod para diseñar ese esquema.
- **`galivelop-image-generator` (gimg) y `galivelop-voice-generator` (gvoice):** conformistas. Vendorizan `grun` y le
  conectan su motor, sus pedidos, sus ganchos y su interfaz.
- **`World-Maker-Fantasy` (WMF):** cliente del candado mediante el protocolo publicado (`grun.lock/1`, `docs/protocol/grun.lock.1.md`, y §8, P-3).
  - Su backend es TypeScript y ya serializa sus llamadas con `ollamaQueue.ts` (concurrencia 1), así que el candado
    va dentro de esa cola.
  - Sus herramientas en Python o shell pueden usar `flock` directamente.
- **`galivelop-evaluator` (GVE):** lee `grun.run/0` (duraciones, esperas y fallos) como medidas deterministas.
  También llama a Ollama, así que tiene que pasar por el turno como WMF.
- **`galivelop-forge` (futuro, hoy vacío):** orquestará pedidos de varias aplicaciones sobre esta misma base, con
  prioridades entre aplicaciones.

## 4. Modelo

- **Agregado raíz:** `Queue`. Toda mutación es una transacción (`_txn`): `flock` exclusivo sobre `queue.json.lock`,
  y no escribe si nada cambió. Nada cambia una entrada fuera de ella.
- **Entidades:** `Entry` (id entero creciente por aplicación, que no baja aunque se poden entradas), `Holder`.
- **Objetos de valor:** `EntryState`, `Progress`, `RunError`, `Limits`, `LockPath`, `BatchRef` (`{id, index, size}`).
- **Servicios:**
  - de cola: `enqueue`, `claim`, `finish`, `cancel`, `cancel_batch`, `move`, `move_batch`, `pause`, `resume`,
    `set_progress`, `set_preview`, `recover_orphans` y `prune`;
  - `machine_lock.hold(should_cancel, on_wait)` → contexto con `held_fds()`;
  - `ollama.generate(...)`, dentro de `hold`;
  - `Worker.run_once` y `Worker.loop`; `Launcher.maybe_launch`.
- **Interfaces que pone el consumidor:**
  - `Engine.run(job, on_progress, should_cancel, pass_fds) -> Result`. Lanza `EngineError(code, params)`,
    `EngineTimeout` o `Cancelled`. gvoice pasa sus tres operaciones (`design`, `line`, `voiceprint`) a tipos de
    trabajo según `kind` (§8, P-9).
  - `OrderStore`: dónde vive el pedido y su salida. Incluye `attempt_for_entry` y `add_attempt(entry_id=…)`, que
    son idempotentes.
  - `Checks`: validación previa al encolado.
  - `Estimate`: tiempo estimado a partir del registro.
  - `PendingCleaner`: qué archivos a medias se borran al recuperar una entrada.
  - `ProfileLoader`: perfil de máquina, hasta que exista gmod.
- **Archivos de candado** (ninguno se borra nunca):
  - `gpu.lock`, uno por máquina y común a todas las aplicaciones;
  - `<data>/worker.lock`, uno por aplicación: un solo worker, y sirve para detectar huérfanas;
  - `<data>/queue.json.lock`, uno por aplicación: las transacciones;
  - `<data>/serve.lock`, uno por aplicación, si hay servidor.
- **Orden dentro de un titular:** primero el candado de máquina, luego el desalojo de Ollama, luego la espera de
  memoria y por último el motor. Todas las esperas se pueden cancelar.
- **Eventos** (líneas del registro, no un bus): `EntryQueued`, `EntryClaimed`, `LockWaited`, `LockAcquired`,
  `MemoryWaited`, `OllamaEvicted`, `ProgressReported`, `EntryFinished`, `OrphanRecovered`.
- **Errores:**
  - Se conservan los códigos que ya usan las dos aplicaciones (`queue.*`, `worker.*`, `engine.*`, `machine_lock.*`
    y `path.*`; lista en [estado-actual.md](estado-actual.md)), para que sus tests y textos sigan valiendo.
  - Se añaden `queue.invalid_transition`, `queue.orphaned` y `net.non_local_host` (§8, P-14).
- **Artefactos gart** (todos `/0`, provisionales y sin huella, hasta que se promuevan; §8, P-13):
  - `grun.queue/0`: el `queue.json` de una aplicación. Acepta entradas antiguas sin los campos nuevos (gimg ya
    añadió campos con valores por defecto) y deja campos libres por aplicación.
  - `grun.lock/1` (desde R5, D-13; era `/0`): el contenido informativo del `gpu.lock` (aplicación, pid, entrada y desde cuándo). El candado lo
    da el `flock`, no este texto.
  - `grun.run/0`: el resumen de una ejecución terminada (tiempos de espera y ejecución, estado y código de error),
    pensado para GVE.
  - `grun.trace/0`: la traza por pasos de un intento. Es nueva (no existe en ningún repo) y no entra en R1 (§8,
    P-16).

## 5. Invariantes

Cada una lleva su test.

1. **Un solo titular por máquina:** dos procesos de aplicaciones distintas nunca tienen el candado a la vez. Test:
   dos subprocesos `hold()` sobre la misma ruta, con marcas de tiempo que no se solapan.
2. **Morir suelta el candado:** si el titular muere por SIGKILL y no tenía hijos que hubieran heredado el candado,
   el siguiente lo obtiene sin hacer nada. Test: subproceso que toma el candado y se mata, y el padre que lo
   obtiene a continuación.
3. **El hijo del motor hereda el candado:** mientras viva un proceso del motor lanzado con `held_fds()`, la máquina
   sigue ocupada aunque su worker haya muerto. Test: worker que lanza un hijo con `pass_fds`, matar al worker y
   comprobar que el candado sigue tomado hasta que el hijo acaba. Es el de `gvoice tests/test_engine_qwentts.py:361`.
4. **Esperar no es fallar:** con el candado ocupado, o sin memoria libre, una entrada espera. Si se cancela, sale
   con `WaitCancelled` y sin tomar nada. Test: candado tomado, cancelar la espera y comprobar el estado `cancelled`
   (no `failed`) y que el candado sigue libre.
5. **Los archivos de candado nunca se borran:** borrar `gpu.lock`, `worker.lock` o `queue.json.lock` permitiría dos
   titulares sobre dos archivos distintos. Test: un análisis del código que falle si algún módulo hace `unlink`,
   `remove` o `rmtree` sobre una ruta de candado, y otro de que `hold()` crea el archivo si falta.
6. **Una sola ruta de candado:** con el mismo entorno, toda versión de `grun`, el `machine_lock` actual de gvoice y
   el protocolo de WMF calculan la misma ruta de `gpu.lock`. Test: una tabla de entornos (con y sin
   `XDG_STATE_HOME`, dentro y fuera de Flatpak, con la variable de cambio) y la misma ruta en cada fila.
7. **Orden determinista:** con la misma cola, `claim()` devuelve siempre la misma entrada: primero la posición y luego
   el id (prioridad: §8, P-4). Test: la misma cola cargada dos veces y el mismo orden de reclamo.
8. **Transiciones válidas:** solo se permiten `queued→running`, `queued→cancelled`, `running→done|failed|cancelled`
   (esta última, solo desde `finish` del worker con `cancelRequested` o desde la recuperación) y `running→queued`
   (solo desde la recuperación). Test: tabla de transiciones con un error `queue.invalid_transition` en el resto,
   comprobando el código del error.
9. **Huérfanas recuperadas sin trabajo doble:** si una entrada está en `running` y nadie tiene `worker.lock`, se
   recupera según la regla de §8, P-5. El motor no vuelve a correr para un intento que ya existe. Test: cola con una
   entrada en `running` sin worker, `recover_orphans`, el estado esperado, y un `OrderStore` falso que cuenta las
   llamadas al motor.
10. **Escritura atómica:** un corte a mitad de una transacción deja la cola de antes o la de después, nunca un JSON
    roto. Test: fallo inyectado entre la escritura y el `replace`, y la cola anterior se lee bien.
11. **Sin red fuera de localhost:** el servidor solo escucha en `127.0.0.1`, comprueba la cabecera `Host`, y el
    cliente de Ollama rechaza hosts que no sean locales. Test: arrancar con un host externo da el error
    `net.non_local_host`.
12. **Solo stdlib:** un test recorre los `import` del paquete contra `sys.stdlib_module_names`.
13. **La API de cola no se rompe:** la forma de `/api/queue` y de la entrada que leen las interfaces de gimg y gvoice
    no pierde campos ni cambia su significado. Test: respuestas fijadas como ejemplo y validadas contra
    `grun.queue/0`.
14. **Huella estable:** los esquemas `grun.*/N` con N ≥ 1 no cambian. Test: huellas sha256 fijadas, con el
    procedimiento de gart cuando gart lo defina. Mientras todo sea `/0`, este test no tiene nada que guardar.

## 6. Alcance

**Dentro:**
- cola, lotes, movimientos, pausa, progreso y vista previa, huérfanas y poda;
- worker genérico con su interfaz de motor, la espera de memoria y el lanzador opcional;
- candado de máquina común, con su titular y su protocolo publicado;
- turno de Ollama y desalojo;
- rutas, límites, errores con i18n, escritura atómica y registro;
- base del servidor local (si P-2 dice que sí);
- `grun doctor`.

**Fuera:**
- los motores (sd.cpp, qwentts.cpp): siguen en cada aplicación;
- el formato de los pedidos de cada aplicación, y la composición de imagen de gimg;
- la interfaz web, aunque el contrato de `/api/queue` que lee sí está dentro (invariante 13);
- el catálogo y la descarga de modelos (son de gmod);
- la planificación entre aplicaciones con prioridades globales (es de `galivelop-forge`);
- Windows;
- cualquier servicio en la nube.

## 7. Escalera de hitos

| Hito | Nivel | Qué | Lo decide |
|---|---|---|---|
| R0 | Diseño | Este DDD, las decisiones de §8 y el glosario (F-1). El paso a `main` y el reparto en versiones ([roadmap](../roadmap.md)) es F0 | Persona |
| R1 | Extracción | `grun` con candado, cola, worker y soporte: base de gvoice más las funciones generales de gimg (P-6), con los tests de las invariantes 1-12 | Tests en verde |
| R2 | Hueco | gimg toma el candado de máquina común (hoy no lo toma) y le pasa `held_fds` a sd.cpp: imagen y voz ya no coinciden en la GPU. Puede adelantarse a R1 con una copia de `machine_lock` (P-17) | Prueba en la Deck (persona) |
| R3 | Migración gvoice | gvoice borra sus «Copiado de gimg@…» y vendoriza `grun` | Tests de gvoice en verde e invariante 13 |
| R4 | Migración gimg | Lo mismo en gimg, que es la más grande (cola de 680 líneas y servidor de 1124), más la base del servidor (P-2) | Tests de gimg en verde e invariante 13 |
| R5 | Texto | Turno de Ollama, desalojo y protocolo `grun.lock/1` documentado e integrado en `ollamaQueue.ts` de WMF | Prueba de las tres a la vez en la Deck |
| R6 | Medidas | `grun.run/1` que lee GVE, y GVE pasa por el turno | GVE lo consume |

**Bloqueos externos:**
- La validación con gart espera a que gart tenga su registro.
- `gmod.machine/0` espera a gmod.
- Ninguno de los dos bloquea R1-R4 (P-12).

## 8. Preguntas abiertas

Cada una lleva su recomendación. Se responden por número en [`docs/questions.md`](../questions.md) (Q-n = P-n).

1. **Ruta del `gpu.lock` común.** gvoice ya usa `$XDG_STATE_HOME/galivelop/gpu.lock` (o
   `~/.local/state/galivelop/gpu.lock`), y dentro de Flatpak ignora XDG. El borrador 1 proponía
   `$XDG_RUNTIME_DIR`, pero eso daría otro archivo, y una gvoice vieja y una nueva no se excluirían. Además,
   `XDG_RUNTIME_DIR` puede faltar en la Deck.
   **Recomendación:** mantener exactamente la ruta de gvoice, con su regla de Flatpak. Como variable de cambio,
   `GALIVELOP_STATE_HOME`, aceptando `GVOICE_STATE_HOME` como alias hasta R3.
2. **¿Entra la base del servidor local?**
   **Recomendación:** sí, desde R4: arranque en localhost con la comprobación de `Host`, la tabla de error a HTTP de
   gimg, `health` y las rutas de cola. Las pantallas se quedan en cada aplicación.
3. **¿Cómo pasa WMF (Node) por el candado?** Node no tiene `flock` de serie, y un archivo con pid no se suelta solo
   al morir.
   **Recomendación:** dentro de `ollamaQueue.enqueue`, lanzar `flock(1)` (util-linux, que ya viene en SteamOS) como
   proceso hijo que tiene el candado mientras vive. Matarlo al acabar, o al vencer un tope de tiempo igual al
   `queueTimeoutMs`, para que un `fetch` colgado no deje la máquina tomada. No hace falta un demonio. Lo mismo vale
   para GVE.
4. **¿Prioridades en la cola?** Hoy no existen en ninguna aplicación; gimg tiene `position` y `move`.
   **Recomendación:** no en R1. El orden es posición y luego id; las prioridades se apuntan como pendiente y, si
   llegan, serán entre aplicaciones (de forge). El candado entre aplicaciones queda sin prioridad: el primero que
   llega se lo lleva.
5. **¿Qué se hace con una huérfana?** Hoy vuelve a la cola sin límite, o queda `cancelled` si tenía
   `cancelRequested`. La idempotencia de `attempt_for_entry` evita repetir trabajo ya hecho.
   **Recomendación:** mantener eso y añadir un contador `orphanCount`. A la segunda vez, se cierra como `failed` con
   `queue.orphaned`, para que un motor que tumba el proceso no entre en bucle.
6. **¿De qué cola se parte?**
   **Recomendación:** de la de gvoice (más corta y más nueva), subiendo a `grun` lo que gimg tiene de **general**:
   lotes, `move`, pausa, progreso, vista previa y entradas retenidas. Lo que es solo de imagen (`compose`, plantillas,
   `estimate_for` con su proveedor) entra por ganchos o se queda en gimg.
7. **¿Cómo se reparten la memoria Ollama y los demás?** El candado no libera la VRAM: Ollama mantiene sus modelos
   cargados después de su turno (`keep_alive`). gimg ya tiene la guarda `engine.ollama = abort|unload|ignore` y gvoice
   descarga a mano con un script.
   **Recomendación:** el desalojo pasa a `grun`. El titular que no es Ollama, al tomar el candado, descarga los
   modelos de Ollama (`keep_alive: 0`) antes de esperar memoria. WMF mantiene su `keep_alive` entre turnos seguidos.
   La guarda de gimg queda como configuración de ese desalojo, con `unload` por defecto, y el script de gvoice se
   retira en R3.
8. **¿Dónde va la espera de memoria?**
   **Recomendación:** como hoy en gvoice: dentro del candado, después del desalojo, cancelable con `WaitCancelled`.
   Usa `minFreeMemoryMb` del perfil y es común para gimg y gvoice.
9. **¿Qué forma tiene la interfaz del motor?**
   **Recomendación:** `Engine.run(job, on_progress, should_cancel, pass_fds) -> Result`, a la manera de gimg (que ya
   tiene progreso y vista previa). gvoice pasa `design`, `line` y `voiceprint` a tipos de trabajo, y su
   `on_progress` puede no hacer nada.
10. **¿Dónde vive la cola?**
    **Recomendación:** donde ya está, `<data>/queue.json`, sin migrar. Solo el `gpu.lock` va a la carpeta común.
11. **¿Quién arranca el worker?**
    **Recomendación:** `grun` trae el lanzador de gimg (`maybe_launch`) como pieza opcional. gimg lo usa desde R4 y
    gvoice decide si lo adopta.
12. **¿Qué hace `grun` mientras gart y gmod no tienen código?**
    **Recomendación:** no esperarlos. Los esquemas `grun.*` son archivos JSON Schema validados por los tests de `grun`
    (se pasan a gart cuando tenga registro), y los límites llegan por un `ProfileLoader` que lee los
    `machine_profiles/` de cada aplicación hasta que exista `gmod.machine/0`.
13. **¿Cuándo pasan los artefactos de `/0` a `/1`?** Hasta entonces la huella (invariante 14) no guarda nada.
    **Recomendación:** `grun.lock/1` en R5 (lo consume WMF, fuera de Python) y `grun.run/1` en R6 (lo consume GVE).
    `grun.queue` se queda en `/0` mientras solo la lean las interfaces de las propias aplicaciones.
14. **¿Qué códigos de error son de `grun`?**
    **Recomendación:** se quedan los que ya existen con su nombre (`queue.*`, `worker.*`, `engine.*`,
    `machine_lock.*` y `path.*`), y sus textos pasan a los `locales` de `grun`. Los nuevos son
    `queue.invalid_transition`, `queue.orphaned` y `net.non_local_host`. Cada aplicación junta los textos de `grun`
    con los suyos.
15. **¿`grun doctor` y `gimg doctor`?**
    **Recomendación:** `grun doctor` cubre el candado, la cola, las huérfanas y los candados de aplicación, y `gimg
    doctor` lo llama para esa parte. gvoice gana un doctor sin escribirlo.
16. **¿Entra `grun.trace/0`?** No existe en ningún repo.
    **Recomendación:** fuera de R1-R4. Se apunta como pendiente y se decide con GVE en R6.
17. **¿Se adelanta R2?** Es lo que más se nota en la Deck: imagen y voz dejan de coincidir. Además, basta con que
    gimg copie `machine_lock.py` de gvoice y le pase `held_fds` a sd.cpp.
    **Recomendación:** sí, hacer R2 antes que R1, en el repo de gimg, con la marca «Copiado de gvoice@<sha>», que
    desaparece en R4.

## Decisiones

Tomadas el 2026-11-26 (F-1): la persona acepta las 17 recomendaciones de §8 (Q-1..Q-17 en [`docs/questions.md`](../questions.md)). D-n responde a P-n.

- **D-1.** Ruta del `gpu.lock`: la de gvoice tal cual (`$XDG_STATE_HOME/galivelop/gpu.lock`, o `~/.local/state/galivelop/gpu.lock`, con su regla de Flatpak). Variable de cambio `GALIVELOP_STATE_HOME`, con `GVOICE_STATE_HOME` como alias hasta R3.
- **D-2.** La base del servidor local entra en `grun` desde R4 (localhost, comprobación de `Host`, tabla error→HTTP, `health` y rutas de cola). Las pantallas se quedan en cada aplicación.
- **D-3.** WMF y GVE pasan por el candado lanzando `flock(1)` como proceso hijo dentro de su cola de Ollama, con un tope igual a `queueTimeoutMs`. Sin demonio.
- **D-4.** Sin prioridades en R1: orden por posición y luego id; entre aplicaciones, el primero que llega. Las prioridades, a pendiente (forge).
- **D-5.** Huérfanas: vuelven a la cola, con un contador `orphanCount`; a la segunda se cierran como `failed` con `queue.orphaned`.
- **D-6.** La cola de `grun` parte de la de gvoice, más lo general de gimg (lotes, `move`, pausa, progreso, vista previa, `held`). Lo solo de imagen, por ganchos o en gimg.
- **D-7.** El desalojo de Ollama pasa a `grun`: el titular que no es Ollama descarga sus modelos (`keep_alive: 0`) al tomar el candado. La guarda de gimg queda como configuración, con `unload` por defecto; el script de gvoice se retira en R3.
- **D-8.** La espera de memoria va dentro del candado, después del desalojo, y es cancelable (`WaitCancelled`), con `minFreeMemoryMb` del perfil.
- **D-9.** Interfaz del motor: `Engine.run(job, on_progress, should_cancel, pass_fds) -> Result`; las operaciones de gvoice pasan a tipos de trabajo.
- **D-10.** La cola se queda en `<data>/queue.json`, sin migrar.
- **D-11.** El lanzador de gimg (`maybe_launch`) entra en `grun` como pieza opcional; gimg lo usa desde R4 y gvoice decide.
- **D-12.** `grun` no espera a gart ni a gmod: esquemas JSON propios validados por sus tests y un `ProfileLoader` sobre los `machine_profiles/` de cada aplicación.
- **D-13.** `grun.lock/1` en R5 y `grun.run/1` en R6; `grun.queue` se queda en `/0`.
- **D-14.** Se conservan los códigos de error existentes con su nombre, con sus textos en los `locales` de `grun`. Nuevos: `queue.invalid_transition`, `queue.orphaned`, `net.non_local_host`.
- **D-15.** `grun doctor` cubre candado, cola, huérfanas y candados de aplicación; `gimg doctor` lo llama.
- **D-16.** `grun.trace/0` queda fuera de R1-R4; se decide con GVE en R6 (a pendiente).
- **D-17.** R2 se adelanta a R1: gimg copia `machine_lock.py` de gvoice («Copiado de gvoice@<sha>», que desaparece en R4) y pasa `held_fds` a sd.cpp.
