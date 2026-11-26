# DDD: galivelop-runtime (borrador 1, 2026-11-26)

**Uso:** núcleo común de ejecución local para los generadores de Galivelop. Recoge lo que hoy está duplicado entre
gimg y gvoice («Copiado de gimg@<sha>», D7): pedidos, cola, worker, registro y rutas. Añade dos piezas que ningún
repo tiene completas: el candado de máquina compartido entre aplicaciones y la cola de Ollama.

- **Nombre:** Galivelop Runtime · **paquete:** `grun` · **espacio de artefactos:** `grun`
- **Visibilidad:** público · **stack:** Python ≥ 3.10, solo stdlib, sin red fuera de `localhost`
- **Depende de:** `galivelop-artifacts` (gart: valida sus artefactos) y `galivelop-models` (`gmod.machine/0`: el
  perfil de la máquina en la que corre). Los consumidores lo vendorizan, igual que gart, con su test de huella.

## 1. Propósito

Un trabajo pesado de IA local (imagen, voz, texto) se encola, espera a que la máquina esté libre, corre con un solo
dueño de la GPU, informa de su progreso y deja un registro. Todo esto pasa igual en cualquier aplicación de
Galivelop y sin que una aplicación tenga que saber nada de las demás.

**Éxito:**
1. gimg y gvoice borran sus módulos «Copiado de gimg@…» y usan `grun`, y sus tests siguen en verde.
2. Una imagen (gimg), una voz (gvoice) y una narración (Ollama de WMF) lanzadas a la vez en una Steam Deck nunca
   ocupan la GPU juntas. Se ejecutan de una en una, y ninguna falla por tener que esperar.
3. Si a un worker se le mata a mitad de un trabajo, no deja la máquina bloqueada ni el trabajo en «running» para
   siempre.

## 2. Lenguaje

| Término | Código | Significado |
|---|---|---|
| Pedido | `Order` | Lo que pide un proyecto: qué generar, con qué perfil y qué parámetros. Es el documento de la aplicación; `grun` solo lo lleva de un sitio a otro. |
| Intento | `Attempt` | Una ejecución de un pedido, con su semilla y su resultado. Un pedido tiene uno o más. |
| Entrada | `Entry` | Un intento puesto en la cola, con su estado y su posición. |
| Lote | `Batch` | Las entradas de un mismo envío; se mueven, se cancelan o se paran juntas. |
| Cola | `Queue` | La lista persistente de entradas de una aplicación (`<state>/queue.json`), cambiada solo por transacciones. |
| Estado | `EntryState` | `queued` → `running` → `done` \| `failed` \| `cancelled`. |
| Worker | `Worker` | El proceso que reclama la siguiente entrada, la ejecuta con un motor y la cierra. Hay uno por aplicación. |
| Motor | `Engine` | El adaptador que hace el trabajo de verdad (sd.cpp, qwentts.cpp, Ollama). Es de la aplicación, no de `grun`. |
| Candado de máquina | `MachineLock` | Un `flock` exclusivo sobre el `gpu.lock` común. Quien lo tiene es el único que usa la GPU en ese momento. |
| Titular | `Holder` | El proceso que tiene el candado ahora, con su aplicación, su entrada y desde cuándo. |
| Espera | `Wait` | El tiempo que una entrada pasa sin candado. Se puede cancelar y nunca cuenta como fallo. |
| Pausa | `Pause` | Una marca que impide al worker reclamar entradas nuevas; la que está corriendo termina. |
| Huérfana | `Orphan` | Una entrada en `running` cuyo worker ha muerto. Al recuperarla vuelve a la cola o se cierra como fallo. |
| Progreso | `Progress` | Pasos hechos y totales, más una vista previa si la hay, del intento que corre. |
| Error | `RunError` | Un código estable más sus parámetros. El texto se resuelve con i18n (es/en) al mostrarlo. |
| Límites | `Limits` | Topes de tamaño, número y duración, cargados del perfil de máquina. |
| Turno de Ollama | `OllamaTurn` | Una llamada a Ollama que pasa por el candado de máquina, para que el texto también haga cola. |

## 3. Contextos acotados

1. **Cola** (núcleo): entradas, lotes, transacciones con bloqueo de archivo, pausa, recuperación de huérfanas.
   Viene de `gimg/queue.py` (680 líneas) y `gvoice/queue.py` (433). Se unifica por la parte común; lo que es propio
   de cada aplicación entra por ganchos (`checks`, `estimate`).
2. **Worker**: reclamar, ejecutar con el motor, informar del progreso, atender la cancelación y cerrar la entrada.
   Viene de los dos `worker.py`. El motor llega como interfaz y `grun` no importa ninguno.
3. **Candado de máquina**: `hold()`, la espera cancelable, `held_fds` y el titular. Viene de
   `gvoice/machine_lock.py` (D8). Cambia una cosa: la ruta deja de ser de una sola aplicación y pasa a ser común
   (§8.1).
4. **Turno de Ollama**: un cliente mínimo a `localhost:11434` que toma el candado alrededor de cada generación. Su
   cola es la espera del candado, no una cola propia (§8.3).
5. **Soporte**: `paths` (XDG y variables `*_HOME` por aplicación), `limits`, `errors`, `fsutil` (escritura
   atómica), `i18n`, `log` y `trace`.
6. **Servidor local** (opcional, §8.2): la base HTTP de solo `localhost` que comparten `gimg/server.py` y
   `gvoice/server.py`: rutas de cola, progreso y vista previa. Las rutas de cada aplicación se quedan en su repo.

**Mapa con los demás repos:**
- `galivelop-artifacts` (gart): núcleo compartido (shared kernel). `grun` valida sus artefactos con gart.
- `galivelop-models` (gmod): cliente-proveedor. `grun` lee `gmod.machine/0` para los límites y la VRAM, y deja de
  tener `machine_profiles/` propios.
- `galivelop-image-generator` (gimg) y `galivelop-voice-generator` (gvoice): conformistas. Vendorizan `grun` y le
  conectan su motor, sus pedidos y su interfaz.
- `World-Maker-Fantasy`: cliente del turno de Ollama mediante el protocolo publicado (`grun.lock/0`). Es TypeScript,
  así que no vendoriza Python: sigue el protocolo del candado (§8.3).
- `galivelop-evaluator` (GVE): lee `grun.run/0` (duraciones, esperas y fallos) como medidas deterministas.
- `galivelop-forge` (futuro): orquesta pedidos de varias aplicaciones sobre esta misma base.

## 4. Modelo

- **Agregado raíz:** `Queue`. Toda mutación es una transacción (`_txn`) bajo bloqueo de archivo, y nada cambia una
  entrada fuera de ella.
- **Entidades:** `Entry` (id creciente por aplicación), `Batch`, `Holder`.
- **Objetos de valor:** `EntryState`, `Progress`, `RunError`, `Limits`, `LockPath`, `Priority` (§8.4).
- **Servicios:**
  - `enqueue`, `claim`, `finish`, `cancel`, `move`, `recover_orphans`;
  - `machine_lock.hold(should_cancel, on_wait)`;
  - `ollama.generate(...)`, que lo hace dentro de `hold`;
  - `Worker.run_once` / `Worker.loop`.
- **Interfaces que pone el consumidor:** `Engine.run(entry, on_progress, should_cancel) -> Result`,
  `OrderStore` (dónde vive el pedido y su salida) y `Checks` (validación previa al encolado).
- **Eventos** (líneas del registro, no un bus): `EntryQueued`, `EntryClaimed`, `LockWaited`, `LockAcquired`,
  `ProgressReported`, `EntryFinished`, `OrphanRecovered`.
- **Artefactos gart:**
  - `grun.queue/0`: el `queue.json` de una aplicación.
  - `grun.lock/0`: el contenido informativo del `gpu.lock` (aplicación, pid y entrada del titular; el candado lo
    da el `flock`, no este texto).
  - `grun.run/0`: el resumen de una ejecución terminada (tiempos de espera y ejecución, estado y código de error),
    pensado para GVE.
  - `grun.trace/0`: la traza por pasos de un intento.

## 5. Invariantes

Cada una lleva su test.

1. **Un solo titular por máquina:** dos procesos de aplicaciones distintas nunca tienen el candado a la vez. Test:
   dos subprocesos `hold()` sobre la misma ruta, con marcas de tiempo que no se solapan.
2. **Morir suelta el candado:** si al titular se le mata con SIGKILL, el siguiente lo obtiene sin hacer nada. Test:
   subproceso que toma el candado y se mata, y el padre que lo obtiene a continuación.
3. **Esperar no es fallar:** con el candado ocupado, una entrada espera. Si se cancela, sale con `WaitCancelled` y
   sin tomar nada. Test: candado tomado, cancelar la espera y comprobar el estado `cancelled` (no `failed`) y que
   el candado sigue libre.
4. **El `gpu.lock` nunca se borra:** borrarlo permitiría dos titulares sobre dos archivos distintos. Test: un
   `grep` que falle si algún módulo hace `unlink` sobre la ruta del candado, y un test de que `hold()` crea el
   archivo si falta.
5. **Orden determinista:** con la misma cola, `claim()` devuelve siempre la misma entrada: primero la prioridad,
   luego la posición y luego el id. Test: la misma cola cargada dos veces y el mismo orden de reclamo.
6. **Transiciones válidas:** solo se permiten `queued→running`, `running→done|failed|cancelled` y
   `queued→cancelled`. Test: tabla de transiciones con un error `invalid_transition` en el resto, comprobando el
   código del error.
7. **Huérfanas recuperadas:** si una entrada está en `running` y su worker no está vivo, al arrancar se recupera
   según la regla de §8.5. Test: cola con una entrada en `running` sin worker, `recover_orphans` y el estado
   esperado.
8. **Escritura atómica:** un corte a mitad de una transacción deja la cola de antes o la de después, nunca un JSON
   roto. Test: fallo inyectado entre la escritura y el `rename`, y la cola anterior se lee bien.
9. **Sin red fuera de localhost:** el servidor solo escucha en `127.0.0.1`, y el cliente de Ollama rechaza hosts
   que no sean locales. Test: arrancar con un host externo da el error `non_local_host`.
10. **Solo stdlib:** test que recorre los `import` del paquete contra `sys.stdlib_module_names`.
11. **Huella estable:** los esquemas `grun.*/N` estables no cambian. Test: huellas sha256 fijadas, igual que en
    gart.

## 6. Alcance

**Dentro:**
- cola, lotes, pausa y huérfanas;
- worker genérico con su interfaz de motor;
- candado de máquina común, con su protocolo publicado;
- turno de Ollama;
- rutas, límites, errores con i18n, escritura atómica, registro y traza;
- base del servidor local (si §8.2 dice que sí);
- herramienta `grun doctor`, que dice quién tiene el candado, qué espera y qué huérfanas hay.

**Fuera:**
- los motores (sd.cpp, qwentts.cpp): siguen en cada aplicación;
- el formato de los pedidos de cada aplicación;
- la interfaz web completa;
- el catálogo y la descarga de modelos (son de gmod);
- la planificación entre aplicaciones con prioridades globales (es de `galivelop-forge`);
- cualquier servicio en la nube.

## 7. Escalera de hitos

| Hito | Nivel | Qué | Lo decide |
|---|---|---|---|
| R0 | Diseño | Este DDD, decisiones de §8 y glosario | Persona |
| R1 | Extracción | `grun` con candado, cola, worker y soporte sacados de gvoice (la copia más nueva), con sus tests e invariantes 1-11 | Tests en verde |
| R2 | Hueco | gimg toma el candado de máquina común (hoy no lo toma): imagen y voz ya no coinciden en la GPU | Prueba en la Deck (persona) |
| R3 | Migración gvoice | gvoice borra sus «Copiado de gimg@…» y vendoriza `grun` | Tests de gvoice en verde |
| R4 | Migración gimg | Lo mismo en gimg, que es la más grande (cola de 680 líneas y servidor de 1124) | Tests de gimg en verde |
| R5 | Texto | Turno de Ollama y protocolo `grun.lock/0` documentado para WMF | Prueba de las tres a la vez en la Deck |
| R6 | Medidas | `grun.run/0` que lee GVE | GVE lo consume |

## 8. Preguntas abiertas

1. **¿Dónde vive el `gpu.lock` común?** Hoy está en `<state de gvoice>/gpu.lock`, así que gimg no lo vería aunque
   quisiera.
   **Recomendación:** `$XDG_RUNTIME_DIR/galivelop/gpu.lock` (o `~/.local/state/galivelop/gpu.lock` si no existe), con
   `GALIVELOP_LOCK` para cambiarlo. Es una ruta de la marca, no de una aplicación.
2. **¿Entra la base del servidor local?**
   **Recomendación:** sí, pero solo la parte común (arranque en localhost, rutas de cola, progreso y vista previa) y
   a partir de R4. Las pantallas se quedan en cada aplicación.
3. **¿Cómo pasa WMF (TypeScript) por el candado?**
   **Recomendación:** que siga el protocolo publicado (`flock` sobre la misma ruta, con `grun.lock/0` como
   información) con un módulo pequeño suyo. No hace falta un demonio, porque el kernel ya da la exclusión y la
   liberación al morir. Un demonio local solo tendría sentido si un día hacen falta prioridades entre aplicaciones,
   y eso sería `galivelop-forge`.
4. **¿Prioridades en la cola?**
   **Recomendación:** sí, dentro de cada aplicación (`high` / `normal` / `low`, y FIFO dentro de cada una). El
   candado entre aplicaciones queda sin prioridad: el primero que llega se lo lleva.
5. **¿Qué se hace con una huérfana?**
   **Recomendación:** que vuelva a `queued` una vez. Si vuelve a quedar huérfana, se cierra con el error
   `orphaned`, para que un motor que tumba el proceso no entre en bucle.
6. **¿Unificar las dos colas o empezar desde una?**
   **Recomendación:** partir de la de gvoice (más corta y más nueva) y subir a ganchos lo que gimg tiene de más
   (`estimate_for`, `compose`, `new_attempts_checked`). Lo que solo use gimg se queda en gimg.

## Decisiones

- _(ninguna aún: pendientes de §8)_
