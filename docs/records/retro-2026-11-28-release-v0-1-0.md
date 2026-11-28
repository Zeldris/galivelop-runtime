# Retro 2026-11-28: PR de `claude/release-v0.1.0` a `main`

**Estado:** aprobada por la persona (2026-11-28): T1 aplicada; P1, P2 y P3 aprobadas para el flujo (abajo).

Sesión tras `/clear`: fusión de `origin/main` (0.2-0.4 y R5, de otra sesión) en la rama, revisión en sesión del diff
trivial (tests de `grun vendor` con idioma fijo, README), check en verde (402 tests, `es_ES`).

## Medida (gw-opt-tokens)

19 llamadas, contexto medio 55 946, 1,06 M de entrada (96 % de caché); arranque fijo ~21 667 por llamada (39 %),
frente a ~80 k en las medidas del 2026-11-27. La mayor carga arrastrada es `docs/handoff.md` (18,6 k, con el conflicto).
Unas 5 llamadas (~280 k de entrada) se fueron en esperar el CI que pedía el gancho `Stop` sobre un commit que el CI
no corre nunca.

## Propuestas

- **T1 (proyecto, `.claude/gw/gw-opt-tokens.md`):** apuntar esta medida como referencia y corregir «Arranque fijo ~82 k»:
  hoy es ~22 k. Si se quitaron los conectores, quitar también ese pendiente de la bitácora. Riesgo: ninguno.
- **P1 (flujo, gancho `Stop` / `before-stop.py`):** no pedir el CI de un HEAD que solo toca rutas de `paths-ignore` del
  workflow (aquí `docs/metrics/ledger.jsonl`): `ci-status.py` devuelve `none` para siempre. Ahorro: ~3-5 llamadas por
  sesión que suben el ledger. Riesgo: ninguno si el filtro se lee del propio `check.yml`.
- **P2 (flujo, `recover.py --state`):** decir al empezar cuántos commits lleva `origin/main` que la rama no tiene. Aquí
  la bitácora de la rama daba R3.2 y R3.3 por hacer, pero ya estaban en `main`; se vio solo al fusionar. Riesgo: ninguno.
- **P3 (flujo, `merge-main.py`):** si no hay tarea en curso, tomar el id del `Refs:` del último commit de la rama en vez
  de negarse y pedir `--refs`. Ahorro: 1 llamada. Riesgo: un `Refs:` equivocado en el commit del ledger (leve).
- **Barrido:** sin propuesta nueva. Esta rama solo cambia tests y README, y el barrido con más leves (`ollama.py`) ya
  es `R6.1` (retro de `0.4`).

## For Galivelop-workflow

P1, P2 y P3 (arriba), si la persona las aprueba.
