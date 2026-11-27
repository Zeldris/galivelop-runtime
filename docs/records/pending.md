# Pendiente

Lo que queda abierto; la bitácora solo apunta aquí. Se añade y se quita en este archivo.

## Pendiente

- Prioridades en la cola, entre aplicaciones: las decide galivelop-forge (DDD D-4).
- grun.trace/0: decidir con GVE en R6 (DDD D-16).
- R1.1, decisiones del agente por confirmar con la persona: `GALIVELOP_LANG` con alias `GVOICE_LANG` (hasta R3); variables de prueba `GRUN_MEMINFO`/`GRUN_PROC_STATUS` sin alias; una variable vacía cuenta como no puesta (también `GALIVELOP_STATE_HOME=""`).
- R1.1: el código va a Python ≥ 3.8 y el DDD dice ≥ 3.10; fijar uno (`requires-python`) al empaquetar.
- Revisión de bloque R1.1 (leves): `i18n.t()` no normaliza un `lang` explícito (`es_ES` cae a inglés); `GrunError` no sobrevive a pickle (pierde `params`; un parámetro `code` es imposible); `paths.inside()` acepta `.` y devuelve la raíz: decidir si es destino válido; `locales/es.json`: comillas ASCII en `error.queue.bad_state` y «trabajador»/«worker» mezclados.
- Proceso: el commit de R1.1 (`d5b2b12`) no llevó la bitácora; en adelante, la bitácora en el mismo commit que el trabajo.
