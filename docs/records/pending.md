# Pendiente

Lo que queda abierto; la bitácora solo apunta aquí. Se añade y se quita en este archivo.

## Pendiente

- Prioridades en la cola, entre aplicaciones: las decide galivelop-forge (DDD D-4).
- grun.trace/0: decidir con GVE en R6 (DDD D-16).
- R3 (`0.2`, GR-1): `grun` lee `GALIVELOP_LANG`, `GALIVELOP_MEMINFO` y `GALIVELOP_PROC_STATUS` sin alias de `GVOICE_*`; al vendorizar, gvoice pasa `lang` explícito o se añaden alias como el de `state_dir`.
- R3 (`0.2`, GR-1): el registro de `grun` usa `app.*` donde gvoice escribía `app.voice.*`; los registros antiguos de gvoice no valen para `estimate` sin convertirlos o leer los dos.
