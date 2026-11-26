# Pendiente

Lo que queda abierto; la bitácora solo apunta aquí. Se añade y se quita en este archivo.

## Pendiente

- Prioridades en la cola, entre aplicaciones: las decide galivelop-forge (DDD D-4).
- grun.trace/0: decidir con GVE en R6 (DDD D-16).
- R3 (`0.2`, GR-1): `grun` lee `GALIVELOP_LANG`, `GALIVELOP_MEMINFO` y `GALIVELOP_PROC_STATUS` sin alias de `GVOICE_*`; al vendorizar, gvoice pasa `lang` explícito o se añaden alias como el de `state_dir`.
- R3 (`0.2`, GR-1): el registro de `grun` usa `app.*` donde gvoice escribía `app.voice.*`; los registros antiguos de gvoice no valen para `estimate` sin convertirlos o leer los dos.
- Revisión de bloque GR-1, hallazgos leves: `fsutil.write_json` sin `fsync` del directorio tras `replace`; `log._lines` lanza `UnicodeDecodeError` con una línea cortada; `log.append` no repone el `\n` final; `fsutil.honour_umask` cambia la máscara del proceso entero (hilos); `i18n.t` no normaliza un `lang` explícito (`es_ES`); `i18n.t` sin protección ante un parámetro que falta; `tests/test_stdlib_only.py` exige 3.10 sin la lista propia que pide la ficha; `paths.data_dir` no valida `app`; el test de códigos usados solo ve literales tras `Error(`; la tabla de la invariante 6 no debe decir que las filas con `GALIVELOP_STATE_HOME` coinciden con gvoice.
