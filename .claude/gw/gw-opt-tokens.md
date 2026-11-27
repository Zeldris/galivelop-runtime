<!-- galivelop-workflow v0.9.1 -->
# gw-opt-tokens — notas del proyecto

Las lee la skill `gw-opt-tokens` antes de proponer nada, y se actualizan cuando la persona aprueba un cambio. El flujo
las crea una vez; desde entonces son del proyecto.

## Herramientas que ya ahorran

<!-- Una línea cada una, con cómo se corre. -->
- `python3 .claude/gw/scripts/recover.py --state` y `--search "<texto>"`: recuperar lo que se llevó una
  compactación.
- `gw-orchestrate-dealer`: el trabajo de más de un paso, repartido a subagentes de contexto limpio.

## Costes conocidos

<!-- Lo que se ha visto que cuesta mucho en este proyecto (archivos grandes leídos enteros, salidas largas...). -->

## Ajustes en vigor

- Ventana de compactación automática: `CLAUDE_CODE_AUTO_COMPACT_WINDOW` en `.claude/settings.json`.

## Referencias medidas

<!-- Cifras medidas con las que comparar: fecha, sesión, contexto medio, llamadas, total. -->
- 2026-11-26, F0 (roadmap y revisión, tras `/clear`): 16 llamadas, contexto medio 100 491, 1,61 M de entrada (97 % de
  caché); arranque fijo ~80 950 por llamada (81 %). Revisor `gw-reviewer` (sonnet): 4 llamadas, 117 k.

- 2026-11-27, R3.1 (tras `/clear`): 31 llamadas, contexto medio 112 063, 3,47 M de entrada (98 % de caché); arranque
  fijo ~80 341 por llamada (72 %). Revisor `gw-reviewer` (sonnet): 4 llamadas, 131 k. El roadmap se leyó 3 veces con
  `sed`: usar `roadmap.py show|list|done`.

- 2026-11-27, cierre de `0.2` (tras `/clear`): 6 llamadas, contexto medio 90 671, 544 k de entrada (96 % de caché);
  arranque fijo ~80 171 por llamada (88 %). Sin lecturas repetidas ni subagentes.

## Costes conocidos que no se pueden quitar

- El arranque fijo de los conectores (`Claude_Docs`, `github`, `claude-code-remote`): en Claude cloud no se pueden
  desactivar (retro F0, P1 rechazada). Solo baja haciendo menos llamadas.
