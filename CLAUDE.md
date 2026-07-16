# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Harness 规则（最高优先级）
读取并严格遵守 @harness-rules.md 中的所有规则。

**每次会话启动必须执行：**
1. SessionStart hook 会自动注入当前状态机 status（`.claude/hooks/session-start.sh`）；据此进入对应角色入口
2. 读取 `.auto-memory/MEMORY.md`（项目记忆索引），按 T0/T1/T2 分层加载记忆文件
3. 阶段角色入口：`/plan`（new / planning / done）、`/build`（building / fixing）、`/verify`（verifying / reverifying，编排隔离 evaluator subagent）

**独立性铁则：** 验收必须在隔离上下文中进行（`.claude/agents/evaluator.md`），结论原样落盘。任何人不得评估自己的工作。

**⚠️ 分支规则（本项目覆盖 harness 默认）：** 本项目 **push `main` = 部署生产（deploysvr）**。因此 harness 工作一律走 **branch → PR → squash-merge**（见下方 §Deploy & git workflow）；**绝不自动 push `main`**。harness 角色文件里"push origin main 触发 CI"的措辞，在本项目一律理解为"push 到工作分支 + 开 PR"。部署由用户手动。

**⚠️ 自主模式（/autodrive）：** 机件已安装但**本项目禁止开启**——push main=部署生产，无人值守自主循环会误触生产。若将来要开，必须先在 `.claude/autonomous/settings.autodrive.json` deny-list 里挡死 push-to-main 与部署工具，再由人建 `autonomy-policy.json`。

**进度看板：** 阶段边界可 `/dashboard` 刷新图形化看板（Artifact 快照，URL 存 `progress.json.dashboard_url`）。

**规格文档分级：** 新功能批次须有 `docs/specs/` 下的规格文档（硬性）；Bug 修复批次可省略（软性）。

**编排：** 并行实现、fan-out 验收、后台 CI、/loop 场景见 `orchestration-patterns.md`（同会话快车道为默认）。

**何时升档编排（ultracode / Workflow）：** 日常功能 / 修 bug / 小重构用**普通模式**——快车道默认，harness 会在 ≥4 features 或多验收维度时自动升 fan-out，**不需常开 ultracode**（小批次为主，常开=为小事付大成本，且绕过 harness 的右尺寸判断）。仅在**高风险任务对该任务单独升档**（可临时"用 workflow 做这次 X"，跑完即回普通节奏）：
- 上线前**生产审计**（碰 deploysvr / 真实 data 前）
- **大型迁移 / 跨多文件重构**
- **难缠 bug**（需广搜代码 / 多假设并行）
- **floorplan_core 几何/渲染正确性验证**（渲染错隐蔽，值得对抗验证）

原则：**编排力度跟任务风险走，不按会话一刀切。**

**记忆分层：** `.auto-memory/`（git-tracked）是跨会话共享记忆源。本机用户偏好存储在 `~/.claude/` 中，不入 git。

**生产红线：** 任何生产 / 部署 / DNS / 数据 / 回滚操作前，必读 `docs/生产环境交接.md`（详见下方原项目说明）。L2 / 生产写入 / 计费类验收需用户明确授权。

---

阅天府 studio — interior-design workflow monorepo. Three parts, **no repo-wide task runner** (commands are run ad hoc):
- `apps/api` — FastAPI backend (plain `pip` + venv; **not** a package — just a source dir + `requirements.txt`). **Production and CI run Python 3.12** (`apps/api/Dockerfile` = `python:3.12-slim`); this machine's `python3` is **3.9.6** → code must stay 3.9-compatible for local runs (keep `from __future__ import annotations`).
- `packages/floorplan_core` — pure-stdlib Python geometry/render engine (installed editable into the api venv)
- `apps/web` — Next.js 15 frontend (Yarn 1, TypeScript, static export)

## Python: tests & running

No pytest config exists; tests live in two dirs and require `PYTHONPATH`:

```
PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q
PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q
```

- **CI DOES run pytest** (`.github/workflows/pytest.yml`, added in #57 — the same commit that first wrote this file, which is why this line used to claim the opposite). It runs **both** suites on PRs and pushes to `main`, on **Python 3.12**, with `librsvg2-bin` + `fonts-noto-cjk` installed so the render tests actually execute instead of `skipif`-skipping.
- **Two holes remain, so still run the suites locally before pushing** (or use `/test`):
  1. CI **excludes the byte-for-byte golden test** (`-k 'not render_string_matches_baseline_byte_for_byte'`) because `.phase0-baseline/` is gitignored → **the golden byte comparison only ever runs locally**.
  2. A red pytest **does not block deploy** — `deploy.yml` triggers independently on push to `main`, so a broken Python change still ships. pytest CI is a signal, not a gate.
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

- File store, no DB. The **production source of truth** is `deploysvr:/opt/grandtianfu/data/{projects,artifacts,uploads}`; repository `data/projects/` is only a seed/snapshot and may diverge from production. Never overwrite production from the repository. Writes are atomic (tmp + fsync + `os.replace`, keeps `.bak`).
- `data/uploads/` is gitignored (PIPL-sensitive user photos) — never commit it.
- **`GEOM_READONLY`**: when set, `/save-geometry` returns 403 (guards live data during tests/smoke). Production leaves it empty/writable.
- api runs **`--workers 1`** deliberately (OOM guard, 1g mem during render peaks) — don't bump workers without capacity planning.
- **AI is optional**: missing `OPENAI_API_KEY`/`OPENAI_BASE_URL` → `ai_enabled=False`, AI endpoints return 503, core geometry/render unaffected. AI errors map to HTTP: budget→402, provider→502.

## Deploy & git workflow

- **Read `docs/生产环境交接.md` before any production operation.** Production is `Cloudflare DNS-only -> dmitsvr -> WireGuard -> deploysvr`; old host `kolmatrix` is only a frozen rollback point.
- **Push to `main` deploys to `deploysvr`.** GitHub Actions builds `api`+`web` images → GHCR; the VPS pulls (never builds) via its host-local `/opt/grandtianfu/scripts/deploy.sh`. Host `.env`/Compose/scripts/Nginx/systemd are not synchronized by CI; the active remote deploy script currently differs from the repository version, so read the handoff before relying on a gate or rollback behavior.
- Work on a branch → PR → **squash-merge** to `main`. Commit messages: conventional (`feat:`/`fix:`/`docs:`…). **No AI attribution / `Co-Authored-By` trailer** (disabled by convention; repo history has none).
- Project knowledge base is `docs/*.md` (~40 Chinese design/audit docs); current backlog is `docs/backlog-核对-20260708.md`.
