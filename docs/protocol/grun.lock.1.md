# Protocolo `grun.lock/1`

El candado de máquina de Galivelop: un solo generador a la vez en la máquina (una imagen, una voz o un texto de
Ollama nunca comparten la memoria de una Steam Deck). Este documento es para un cliente que **no es Python** (WMF,
`ollamaQueue.ts`) y se basa solo en lo que hace `grun/machine_lock.py`. Esquema del registro del titular:
[`schemas/grun.lock.1.json`](../../schemas/grun.lock.1.json). Decisión: DDD D-3 y D-13.

El candado es un `flock(2)` exclusivo sobre un archivo. El texto que contiene es solo información.

## Ruta del archivo

`<estado>/gpu.lock`, con `<estado>` (de `grun/paths.py`):

1. `$GALIVELOP_STATE_HOME`, si es una ruta absoluta (una relativa se ignora);
2. si no, `$XDG_STATE_HOME/galivelop`, si `XDG_STATE_HOME` es absoluta;
3. si no, `~/.local/state/galivelop`.

`paths.py` aplica además una regla de Flatpak para las carpetas XDG (dentro de un Flatpak, `FLATPAK_ID` puesta, las
variables apuntan al sandbox); léase `paths.py` si el cliente puede correr en uno. La forma segura de que el cliente
y `grun` coincidan es que ambos reciban `GALIVELOP_STATE_HOME`.

## Reglas del archivo

- **Nunca se borra ni se sustituye** (ni `rm`, ni `mv` encima, ni escritura atómica por reemplazo): cambiaría el
  inodo y dos titulares tendrían candados sobre dos archivos distintos.
- **`flock(1)` no crea la carpeta**: si falta, falla al abrir (`flock` de `util-linux` probado: sale con 66 y «No such file or
  directory»; el código puede variar entre versiones). El cliente hace `mkdir -p <estado>` antes. `grun` la crea al tomar el candado.
- `grun` crea el archivo con modo `0600`. El cliente debe poder abrirlo para lectura y escritura o, al menos, para
  lectura (un `flock` vale sobre un descriptor de solo lectura).

## Tomar el candado con `flock(1)`

El cliente lanza `flock(1)` como proceso hijo que envuelve el trabajo (D-3); el candado vive mientras viva ese hijo
(el kernel lo suelta si el proceso muere, también con `kill -9`). Con `-E 75` el «ocupado» se distingue de un fallo
al abrir.

```sh
LOCK="${GALIVELOP_STATE_HOME:-${XDG_STATE_HOME:-$HOME/.local/state}/galivelop}/gpu.lock"
mkdir -p "$(dirname "$LOCK")"

# Esperar sin tope (como hace grun):
flock -x "$LOCK" ./generar-texto

# No bloqueante: 75 si otro lo tiene, sin esperar:
flock -n -E 75 "$LOCK" ./generar-texto

# Esperar con tope (queueTimeoutMs = 120000 -> -w 120): 75 si vence:
flock -w 120 -E 75 "$LOCK" ./generar-texto
```

Con `-w`, y con `-n`, el código `75` es «el candado sigue ocupado»; cualquier otro código distinto de 0 es el del
trabajo o un fallo del propio `flock`. Sin `-E`, el código de conflicto de `flock(1)` es 1 y se confunde con el del
trabajo.

**Cancelación.** Mientras `flock(1)` espera, el cliente la cancela matando a ese proceso hijo (`SIGTERM`): no ha
tomado nada y no hay que limpiar. Si ya lo tiene y el trabajo corre, matar al hijo suelta el candado. `grun` espera
sondeando cada 0,05 s con `LOCK_EX | LOCK_NB` para poder cancelar; un cliente que use `flock -w` en vez de sondear
cancela matando al proceso.

**Orden** (DDD §4): primero el candado de máquina, luego, si el titular no es Ollama, el desalojo de sus modelos, y
por último el motor. Un turno de Ollama toma el candado y lo suelta al acabar la llamada.

## Registro del titular (`grun.lock/1`)

Mientras `grun` tiene el candado, el archivo contiene un objeto JSON de una línea, escrito en el sitio por el
descriptor bloqueado (se trunca y se escribe; nunca se reemplaza el archivo). Se vacía (truncado a 0) antes de soltar.

| Campo | Tipo | Significado |
|---|---|---|
| `schema` | `"grun.lock/1"` | Versión del registro. |
| `app` | texto o `null` | Aplicación titular (la que pasó a `hold(app=...)`). |
| `pid` | entero ≥ 1 | Proceso de `grun` que lo tiene. |
| `entry` | texto, entero o `null` | Entrada de la cola de la aplicación. |
| `since` | texto `AAAA-MM-DDThh:mm:ssZ` | UTC, en segundos, desde que lo tomó. |

```json
{"schema": "grun.lock/1", "app": "galivelop-voice", "pid": 4242, "entry": "job-1", "since": "2026-11-27T10:00:00Z"}
```

**Un cliente no Python no tiene que escribir el registro.** `flock(1)` no escribe nada y sigue siendo titular: lo
único que decide quién lo tiene es el `flock`. Quien lea el archivo debe aceptar tres casos: vacío (nadie lo tiene, o
el titular no escribió), un objeto con estos campos, y cualquier otro contenido (se trata como «titular sin datos»).
`grun.machine_lock.holder()` da `None` si el candado está libre y `{}` si está tomado y no hay un objeto JSON
legible. Un lector ignora los campos que no conozca. El registro no es prueba de que el candado esté tomado: un
archivo con registro y sin `flock` activo es un registro rancio (ver abajo) y se ignora.

Un cliente que quiera escribir el suyo (opcional) debe hacerlo solo con el candado ya tomado, en el sitio y con los
campos de arriba; si falla la escritura, el candado sigue tomado (en `grun` es «mejor esfuerzo»).

### Saber si está ocupado sin esperar

Abrir el archivo existente (sin crearlo) y pedir `LOCK_SH | LOCK_NB`: si da «ocupado», está tomado; si no, libre.
Sin archivo, nadie lo tiene. Con `flock(1)`: `flock -n -s -E 75 "$LOCK" true` (`75` = ocupado) y, sin el archivo, un
fallo al abrir. Si no se puede abrir o el `flock` falla por otro motivo, el estado es **desconocido** (`busy()` da
`None`), que no es lo mismo que libre.

## De `grun.lock/0` a `grun.lock/1`

Es el paso previsto en D-13 (R5, el candado lo consume WMF, fuera de Python). **Qué cambia: solo el valor del campo
`schema`** (`grun.lock/0` pasa a `grun.lock/1`), y que desde ahora el formato está publicado (este documento y su
esquema). Los campos (`app`, `pid`, `entry`, `since`), sus tipos y la escritura son los mismos que en `/0`.

Compatibilidad: no hay ningún lector en este repo que compare el campo `schema` (`holder()` devuelve el objeto
tal cual), así que nada se rompe aquí; un lector externo que exigiese literalmente `grun.lock/0` tendría que aceptar
también `/1`. El `flock` y la ruta no cambian: un proceso con `grun` en `/0` y otro en `/1` siguen excluyéndose
entre sí. Un lector debe leer el campo `schema` y, ante una versión que no conozca, tratar el contenido como
«titular sin datos», no como error.

## Comportamiento ante fallos

- **Candado rancio.** No existe: el kernel suelta el `flock` cuando el proceso titular muere (incluso con
  `kill -9`), así que un archivo con registro de un titular muerto no bloquea a nadie. Si el registro dice un `pid`
  que ya no existe y el candado está libre, es un registro rancio: se ignora, y el siguiente titular lo sobrescribe.
  Lo contrario también pasa: un hijo que heredó el descriptor (`held_fds` en `grun`, `pass_fds` en el motor) mantiene
  el candado aunque muera el padre; el candado ocupado sin su `pid` vivo es entonces normal y el siguiente espera.
- **No se puede abrir (`EACCES`, carpeta imposible de crear, etc.).** En `grun`, `hold()` falla con
  `machine_lock.unavailable` (`path`, `reason`) y **no toma nada**; no hay espera. `busy()` da `None` (desconocido).
  Un cliente debe tratarlo como error de configuración y avisar, no como «libre» ni reintentar para siempre.
- **El `flock` falla con otro error que «ocupado»** (p. ej. un sistema de archivos sin bloqueos, `ENOLCK`): en
  `busy()` es `None`. El cliente no debe suponer que está libre.
- **Desconocido.** `None` de `busy()`/estado desconocido no es ni libre ni ocupado: se informa y no se decide por él.
- **Escritura del registro fallida.** No afecta al candado, que sigue tomado.
- **Espera cancelada.** `WaitCancelled`: no se toma nada.

## Invariantes para un cliente que no es Python

1. Toma el `flock` **exclusivo** sobre `<estado>/gpu.lock` mientras genera, y solo mientras genera.
2. Un solo archivo: nunca lo borra, lo mueve ni lo sustituye, y nunca crea otro candado equivalente.
3. Si espera, espera: no falla por estar ocupado (salvo su propio tope, `queueTimeoutMs`), y la espera se puede
   cancelar sin dejar nada tomado.
4. El candado dura lo que dura el proceso (o el descriptor) que lo tiene; no se apoya en un archivo `pid` ni en que
   el cliente «se acuerde» de soltar: matar al hijo basta.
5. El texto del archivo no decide nada: ni lo crea para tomar el candado ni lo lee para decidir si está tomado.
6. Respeta el orden: candado de máquina primero, después lo demás.
7. Crea la carpeta de estado antes de lanzar `flock(1)`, y trata un fallo al abrir como error, no como candado libre.

## Comprobación

`tests/test_lock_protocol.py`: el registro real de `hold()` valida contra el esquema, y, si `flock(1)` está
instalado, un `flock(1)` real y `hold()` se excluyen en las dos direcciones (no bloqueante, con tope y cancelable).
