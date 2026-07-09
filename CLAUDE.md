# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

阅天府 studio — interior-design workflow monorepo. Three parts, **no repo-wide task runner** (commands are run ad hoc):
- `apps/api` — FastAPI backend (Python 3.9, plain `pip` + venv; **not** a package — just a source dir + `requirements.txt`)
- `packages/floorplan_core` — pure-stdlib Python geometry/render engine (installed editable into the api venv)
- `apps/web` — Next.js 15 frontend (Yarn 1, TypeScript, static export)

## Python: tests & running

No pytest config exists; tests live in two dirs and require `PYTHONPATH`:

```
PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q
PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q
```

- **CI does NOT run pytest** — only Playwright smoke runs in CI. Run the Python suites locally before pushing; nothing else catches a break. (Or use `/test`.)
- Render tests need `rsvg-convert` (`librsvg2-bin`) + Noto CJK fonts; without it they silently `skipif`-skip — treat skips as "not run," not "passed."
- Run the api locally: from `apps/api`, `PYTHONPATH=packages/floorplan_core uvicorn main:app` (or use the editable install in `apps/api/.venv`).
- Lint/format Python with **ruff** (`ruff format . && ruff check --fix .`); config in root `ruff.toml`.

## Web (`apps/web`)

- Yarn 1 (`yarn@1.22.22`), Node 22 (pinned only in Dockerfile/CI — use 22 locally). `.npmrc` sets `legacy-peer-deps`.
- Scripts: `yarn dev` / `yarn build` / `yarn lint` / `yarn e2e`. **No `format` script** — run `prettier --write` manually (config: `singleQuote`, `trailingComma: all`).
- Prod is a **static export** (`yarn build:export`, `output: 'export'`) → only project `D`'s routes are pre-rendered; non-`D` deep links 404.
- **`MVP_D_ONLY = true`** (`src/app/studio/projects/page.tsx`) hides project create/delete and filters the list to house `D`. Don't flip it without adding multi-project SSR support.
- e2e (Playwright, `e2e/*.spec.ts`) runs on offset ports **web 3100 / api 8010** and copies live data into `.e2e-sandbox/` — **e2e never writes `data/projects`**. Keep it that way.

## Data & red lines

- File store, no DB: `data/projects/{house}/{geometry,furniture,project}.json` (only house `D` exists) are the **tracked live source of truth** — edit deliberately. Writes are atomic (tmp + fsync + `os.replace`, keeps `.bak`).
- `data/uploads/` is gitignored (PIPL-sensitive user photos) — never commit it.
- **`GEOM_READONLY`**: when set, `/save-geometry` returns 403 (guards live data during tests/smoke). Production leaves it empty/writable.
- api runs **`--workers 1`** deliberately (OOM guard, 1g mem during render peaks) — don't bump workers without capacity planning.
- **AI is optional**: missing `OPENAI_API_KEY`/`OPENAI_BASE_URL` → `ai_enabled=False`, AI endpoints return 503, core geometry/render unaffected. AI errors map to HTTP: budget→402, provider→502.

## Deploy & git workflow

- **Push to `main` deploys.** GitHub Actions builds `api`+`web` images → GHCR; the VPS pulls (never builds) via `deploy/scripts/deploy.sh` (health gate + default-scene `validation.ok` gate + auto-rollback to `.last_good_tag`).
- Work on a branch → PR → **squash-merge** to `main`. Commit messages: conventional (`feat:`/`fix:`/`docs:`…). **No AI attribution / `Co-Authored-By` trailer** (disabled by convention; repo history has none).
- Project knowledge base is `docs/*.md` (~40 Chinese design/audit docs); current backlog is `docs/backlog-核对-20260708.md`.
