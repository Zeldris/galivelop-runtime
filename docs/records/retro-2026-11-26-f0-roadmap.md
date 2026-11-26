# Retro F0: roadmap y revisión del bloque (2026-11-26)

**Estado:** decidida el 2026-11-26: P2 y P4 aprobadas y aplicadas; P3 aprobada y aplazada al empezar `0.1`; P1 rechazada (en Claude cloud no se pueden desactivar los conectores).

Sesión tras el `/clear` del cierre de F-1: roadmap de versiones (`docs/roadmap.md`), revisión del bloque desde
`origin/main` (0 hallazgos graves o medios, 1 leve), `gw-opt-tokens` y esta retro.

## Medidas (`gw-opt-tokens`)

- Sesión principal: 16 llamadas, contexto medio 100 491, sin compactaciones; 1,61 M de entrada (97 % de caché).
- **Arranque fijo: ~80 950 tokens por llamada, el 81 % de la entrada.** Lo del proyecto es el 19 % restante.
- Revisor (`gw-reviewer`, sonnet): 4 llamadas, 116 554 de entrada.
- Una llamada se repitió: el `commit-msg` rechazó `Findings: 0` porque iba en un párrafo aparte de `Siguiente:`.

## Propuestas

1. **Apagar los conectores que este proyecto no usa** (del proyecto, lo hace la persona). El arranque fijo (81 %) lo
   llenan el sistema y los MCP: `Claude_Docs`, `github` y `claude-code-remote`. Este repo no usa `Claude_Docs`.
   Apagarlo en el entorno ahorra su parte en cada llamada, incluidas las de los subagentes; `/context` dice cuánto
   pesa. Riesgo: ninguno mientras el proyecto no haga documentos de Claude Docs.
2. **Apuntar la referencia medida** en `.claude/gw/gw-opt-tokens.md` (del proyecto): la fila de arriba, para comparar
   las sesiones de R1. Coste: una línea. Riesgo: ninguno.
3. **Activar `roadmap: true` con `roadmapFiles: ["docs/roadmap.md"]` al empezar `0.1`** (del proyecto). Así las
   sesiones de R1 marcan y leen los pasos con `roadmap.py show|done|list` en vez de leer el archivo entero. Hay que
   pasar la tabla al formato de `roadmap.py`. Riesgo: ninguno; si el formato no casa, `doctor.py` lo dice.
4. **Barrido de leves:** no hay ningún script con dos o más leves abiertos. El único es el de `AGENTS.md`, que no lista
   `ci-local.py --validate`, y se arregla con una línea en este mismo PR.

## Para Galivelop-workflow

- El `commit-msg` que rechaza un trailer suelto podría mostrar el bloque final ya montado (`Findings:`, `Siguiente:`
  y las firmas juntos) para copiarlo, en vez de solo pedir que se mueva. Hoy cuesta una llamada más con todo el
  contexto.
