# Questions

Questions for the user, one entry each; `python3 .claude/gw/scripts/questions.py` reads and rewrites this
file (format: header of scripts/questions.py). Answer by number: `questions.py answer "5. a, 6. ok"`.

## Q-1
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: Ruta del gpu.lock común (DDD §8, P-1)
- Recommendation: Mantener la ruta de gvoice ($XDG_STATE_HOME/galivelop/gpu.lock, con su regla de Flatpak); variable GALIVELOP_STATE_HOME con GVOICE_STATE_HOME como alias hasta R3
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-2
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿Entra la base del servidor local en grun? (P-2)
- Recommendation: Sí, desde R4: localhost con comprobación de Host, tabla error→HTTP de gimg, health y rutas de cola; las pantallas se quedan en cada aplicación
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-3
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿Cómo pasa WMF (Node) por el candado? (P-3)
- Recommendation: flock(1) como proceso hijo dentro de ollamaQueue.enqueue, con tope igual a queueTimeoutMs; sin demonio; igual para GVE
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-4
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿Prioridades en la cola? (P-4)
- Recommendation: No en R1: orden por posición y luego id; prioridades entre aplicaciones, de forge, como pendiente
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-5
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿Qué se hace con una huérfana? (P-5)
- Recommendation: Mantener la vuelta a la cola y añadir orphanCount: a la segunda, failed con queue.orphaned
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-6
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿De qué cola se parte? (P-6)
- Recommendation: De la de gvoice, subiendo lo general de gimg (lotes, move, pausa, progreso, vista previa, held); lo de imagen por ganchos o en gimg
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-7
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿Cómo se reparten la memoria Ollama y los demás? (P-7)
- Recommendation: El desalojo pasa a grun: el titular que no es Ollama descarga sus modelos (keep_alive 0); la guarda de gimg queda como configuración con unload por defecto; el script de gvoice se retira en R3
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-8
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿Dónde va la espera de memoria? (P-8)
- Recommendation: Dentro del candado, tras el desalojo, cancelable con WaitCancelled, con minFreeMemoryMb del perfil
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-9
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿Qué forma tiene la interfaz del motor? (P-9)
- Recommendation: Engine.run(job, on_progress, should_cancel, pass_fds) -> Result, a la manera de gimg; gvoice pasa design/line/voiceprint a tipos de trabajo
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-10
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿Dónde vive la cola? (P-10)
- Recommendation: Donde ya está, <data>/queue.json, sin migrar
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-11
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿Quién arranca el worker? (P-11)
- Recommendation: grun trae el lanzador de gimg como pieza opcional; gimg lo usa desde R4 y gvoice decide
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-12
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿Qué hace grun mientras gart y gmod no tienen código? (P-12)
- Recommendation: No esperarlos: JSON Schema propios validados por sus tests y un ProfileLoader que lee los machine_profiles de cada aplicación
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-13
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿Cuándo pasan los artefactos de /0 a /1? (P-13)
- Recommendation: grun.lock/1 en R5 y grun.run/1 en R6; grun.queue se queda en /0
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-14
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿Qué códigos de error son de grun? (P-14)
- Recommendation: Los existentes con su nombre y sus textos en los locales de grun; nuevos: queue.invalid_transition, queue.orphaned, net.non_local_host
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-15
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿grun doctor y gimg doctor? (P-15)
- Recommendation: grun doctor cubre candado, cola, huérfanas y candados de aplicación; gimg doctor lo llama
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-16
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿Entra grun.trace/0? (P-16)
- Recommendation: Fuera de R1-R4; pendiente, se decide con GVE en R6
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-17
- Refs: F-1
- Status: answered
- Asked: 2026-11-26
- Question: ¿Se adelanta R2 a R1? (P-17)
- Recommendation: Sí: en gimg, con una copia de machine_lock.py de gvoice marcada «Copiado de gvoice@<sha>», que desaparece en R4
- Answer: ok (recomendación)
- Answered: 2026-11-26

## Q-18
- Refs: F0
- Status: answered
- Asked: 2026-11-26
- Question: ¿Apagas el conector Claude_Docs, que este proyecto no usa? (retro P1)
- Recommendation: Sí: lo apagas tú en el entorno; /context dice cuánto pesa
- Answer: no: en Claude cloud no se pueden desactivar los conectores
- Answered: 2026-11-26

## Q-19
- Refs: F0
- Status: answered
- Asked: 2026-11-26
- Question: ¿Apunto la referencia medida en .claude/gw/gw-opt-tokens.md? (retro P2)
- Recommendation: Sí
- Answer: ok
- Answered: 2026-11-26

## Q-20
- Refs: F0
- Status: answered
- Asked: 2026-11-26
- Question: ¿Activo roadmap: true con docs/roadmap.md para que R1 use roadmap.py? (retro P3)
- Recommendation: Sí, al empezar 0.1
- Answer: ok
- Answered: 2026-11-26

## Q-21
- Refs: F0
- Status: answered
- Asked: 2026-11-26
- Question: ¿Añado ci-local.py --validate al check que lista AGENTS.md? (retro P4)
- Recommendation: Sí, una línea en este PR
- Answer: ok
- Answered: 2026-11-26

## Q-22
- Refs: F0
- Status: answered
- Asked: 2026-11-26
- Question: ¿Te vale el reparto en versiones de docs/roadmap.md (R2 en gimg antes de 0.1; 0.1=R1 en 5 pasos; 0.2-0.5=R3-R6; 1.0 lo decides tú)?
- Recommendation: Sí
- Answer: ok
- Answered: 2026-11-26

## Q-23
- Refs: 0.4
- Status: answered
- Asked: 2026-11-27
- Question: 0.4 · ¿Qué leves de queue.py barro primero? Son 6: stop_batch con True==1, enqueue con generadores, _number acepta inf, poda por llegada, checks que devuelve "", items recorrido dos veces. ¿Entran todos?
- Recommendation: Sí, los 6: son pequeños, comparten archivo y cada uno lleva test rojo sin arreglo.
- Answer: sí, los 6
- Answered: 2026-11-27

## Q-24
- Refs: 0.4
- Status: answered
- Asked: 2026-11-27
- Question: 0.4 · ¿Entran también los leves de machine_lock.py (busy() con EACCES, hold() no reentrante) y fsutil.held() (ENOLCK)?
- Recommendation: Sí, después de queue.py y como segundo commit: son los de peor consecuencia (EACCES = «libre», ENOLCK = worker vivo para siempre).
- Answer: sí, segundo commit
- Answered: 2026-11-27

## Q-25
- Refs: 0.4
- Status: answered
- Asked: 2026-11-27
- Question: 0.4 · ¿Tras el barrido sigo con R5 del roadmap (protocolo grun.lock/1, D-13, y turno de Ollama, D-3)?
- Recommendation: Sí: el roadmap lo marca como 0.4 (R5, protocolo grun.lock/1 y flock en ollamaQueue.ts de WMF); empezar por el protocolo en este repo, WMF lo integra la persona o su sesión.
- Answer: sí, protocolo en este repo
- Answered: 2026-11-27

## Q-26
- Refs: R3.1
- Status: open
- Asked: 2026-11-28
- Question: T1: ¿apunto la medida en gw-opt-tokens.md y corrijo el arranque fijo (~82 k → ~22 k)? ¿Quitaste ya los conectores/MCP sin uso (para borrar ese pendiente)?
- Recommendation: ok: aplicarla

## Q-27
- Refs: R3.1
- Status: open
- Asked: 2026-11-28
- Question: P1-P3 (gancho Stop sin CI en commits del ledger, aviso de main por delante en recover.py, Refs automático en merge-main.py): ¿las mando al flujo?
- Recommendation: ok: al apartado For Galivelop-workflow
