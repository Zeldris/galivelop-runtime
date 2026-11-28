<!-- galivelop-workflow v0.9.1 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `claude/release-v0.1.0` |
| **Fase / tarea** | `0.1`-`0.4` y R5 (`grun.lock/1`) ya en `main` (PR #6, `c827879`). Esta rama solo trae el arreglo de los tests de la CLI de vendor con locale en español (R3.1) y el README al día. Presupuesto de compactaciones: 0 |
| **Último punto estable** | PR #7 fusionado en `main` (`6d2fc29`, 2026-11-28) con confirmación de la persona y CI en verde sobre `28a4905`. |
| **Siguiente paso** | Siguiente tarea del roadmap: `R6.1` (barrido de `ollama.py`, `0.5`). Llevar P1-P3 de `docs/records/retro-2026-11-28-release-v0-1-0.md` al flujo. Pendiente de la persona: `flock(1)` en `ollamaQueue.ts` de WMF y prueba en la Deck. |
| **Check** | `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`: verde (402 tests) sobre la fusión con `main`, con locale `es_ES`. |

## Autoría

Ningún commit hace referencia a Claude: antes del primer commit de cada sesión,
`git config user.name "Álvaro García Graña"` y `git config user.email` con el correo de la cuenta de GitHub de la persona (no se escribe en el repo); `agentSignatures: false`.
La rama se reescribió el 2026-11-27 (autor y firmas) con permiso de la persona; `main` no se tocó.

## Para la próxima publicación

`0.1` (R1) con los tests de las invariantes 1-12.

## Hecho (5 últimas)

1. 2026-11-28 — R6.1: barrido de 4 leves: URL de Ollama con ruta/query/fragmento rechazada, `evict` mira `should_cancel` antes de cada `unload`, `holder` ante JSON hondo, `doctor` avisa de `busy()` desconocido (`doctor.machine_busy_undetermined`).
2. 2026-11-28 — PR #7: tests de `grun vendor` con idioma fijo y README al día, fusionado en `main`.
3. 2026-11-27 — R4.1: servidor base (`grun/server.py`): Host/Origin, tabla error→HTTP con tabla de la aplicación, rutas de cola y `health`, `serve.lock`/`serve.json` (sin revisar).
4. 2026-11-27 — R3.2: alias `GVOICE_STATE_HOME` retirado (gvoice ya usa `GALIVELOP_STATE_HOME`, confirmado por la persona).
5. 2026-11-27 — R3.3: revisión de bloque, 2 medios arreglados (`export` atómico con `.grun.old-<pid>`, `profile` ante JSON hondo) y leves a pending.md.

## Pendiente

Lo pendiente está en [`docs/records/pending.md`](records/pending.md); se añade y se quita allí.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `python3 -m unittest discover -s tests`, `python3 .claude/gw/scripts/tests-after-main.py`, `python3 .claude/gw/scripts/ci-local.py --validate`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recover.py --state`.
