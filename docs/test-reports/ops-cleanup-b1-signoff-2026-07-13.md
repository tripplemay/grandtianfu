# ops-cleanup-b1 Signoff 2026-07-13

> 状态：**验收通过，可置 done**（首轮 verifying，fix_rounds=0）
> 触发：harness 接入后首个开发批次——运维长尾 + 前端死控件清理，快车道 fan-out 三域验收全 PASS。
> 本 signoff = 机械聚合三域已落盘的 verbatim 结论，**不重新判定**。

---

## 变更背景

harness 接入本项目后的第一个开发批次。选一批「小改无争议、无产品依赖」的运维长尾与前端死代码合批（来源 `docs/backlog-核对-20260708.md` §D.2），既清理真实技术债，又作为快车道 fan-out 验收的首次演练。6 features 均不改 `floorplan_core` 渲染字节输出，无 golden 重冻门；无生产/部署/凭据操作。

验收编排：6 features ≥4 → 隔离 evaluator **fan-out 分域**（api / web / doc 三域并行，各出域报告；本 signoff 汇总）。

---

## 六 Feature 判定表（verbatim 聚合）

| Feature | 标题 | 域 | Executor | 判定 | 域报告（据） |
|---|---|---|---|---|---|
| F001 | rsvg 缺失可诊断降级（DependencyUnavailable→503，非裸 500） | api | generator | **PASS** | `ops-cleanup-b1-verifying-api-2026-07-13.md` §2 |
| F002 | 缩略图 kind 收入 modes.py RENDER_MODES 注册表 | api | generator | **PASS** | 同上 §3 |
| F004 | project_lock 改 fcntl.flock，消除破锁 TOCTOU | api | generator | **PASS** | 同上 §4 |
| F003 | real-render 角标显中文房名（rooms[].label.zh，非裸 room_id） | web | generator | **PASS** | `ops-cleanup-b1-verifying-web-2026-07-13.md` §F003 |
| F005 | comingSoon 死代码清理（字段 + StudioSidebar UI 分支） | web | generator | **PASS** | 同上 §F005 |
| F006 | 编辑器升级计划文档状态列回填 | doc | generator | **PASS** | `ops-cleanup-b1-verifying-doc-2026-07-13.md` §1 |

**批次总计：6 PASS / 0 PARTIAL / 0 FAIL。**

---

## §14 首轮 verifying PASS（fix_rounds=0）3 硬条件逐条核对

> 依据项目根 `evaluator.md` §14：首轮跳过 fixing/reverifying 直接 done，须**同时**满足 (a)(b)(c)。

### (a) Acceptance 全代码层 PASS + 硬性测试文件存在 ✅

| Feature | acceptance 代码层 | 硬性测试文件 | 存在性 |
|---|---|---|---|
| F001 | errors.py 新异常 / raster.py 抛之 / main.py 双路径映射 503 / 生产零回归 | `test_raster.py`(mock which=None) + `test_render_dependency.py`(端点 503) | ✅ 存在且跑通 |
| F002 | RENDER_MODES 两 mode 增 thumb_kind / 三处取注册表 / empty-thumb 不入表 | `test_modes.py`（新增） | ✅ 存在且跑通 |
| F004 | flock 咨询锁 / 删 mtime+unlink 破锁 / 契约保留 / 10 调用点零改 | `test_baselines_migration.py`（并发三态 + fork+SIGKILL） | ✅ 存在且跑通 |
| F003 | room_id→label.zh 映射 / 两角标 + tooltip 中文名 / 优雅回退 | 无单测要求（spec 定 tsc+lint+build + 手测）；真实 geometry.json 仿真 20 房无裸 id | ✅ 满足 spec |
| F005 | 移除字段声明 + 4 UI 分支 / 零残留引用 | 无单测要求；grep 零残留 + fresh `.next` 零命中 | ✅ 满足 spec |
| F006 | P1–P7 状态列交叉核对 + 依据备注 / 不改选型正文 | 纯文档无测试 | ✅ 满足 spec |

spec §测试要求全数落实：F001 单测在**有 rsvg 的本机**仍靠 mock `shutil.which=None` 跑通（证明无 rsvg 环境可跑）；F004 fork+SIGKILL 自动释放测**未 skip、实跑 PASS**。

### (b) L1 全绿 / L2 本批无 ✅

| 门 | 命令 | 结果 |
|---|---|---|
| api pytest | `PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q` | **301 passed** |
| engine pytest | `PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q` | **131 passed** |
| ruff（pyflakes） | `ruff check --select F`（api 改动 9 文件） | **0 error** |
| web tsc | `npx tsc --noEmit` | **exit 0，0 error** |
| web lint | `yarn lint` | **exit 0，0 error / 7 warning**（全在未触碰的 useViewport.ts，见 Soft-watch S1） |
| web build | `yarn build`（`next build`） | **exit 0**，real-render 成功预渲染（house D，12.3 kB） |

**L2**：本批**无 L2**——无生产/staging 部署、无计费/DNS/数据写入；AI provider 在测试中被 mock，无真实调用。分支仍 `chore/harness-onboarding` 未 push（push main=部署生产，留用户闸门）。详见下「L2 实测记录」。

### (c) 每条 soft-watch 有明文兜底 ✅

| soft-watch | 明文兜底 | 满足 |
|---|---|---|
| S1 useViewport.ts 7 条 exhaustive-deps warning | `backlog.json` `BL-useviewport-hook-deps`(low) 已立项 | ✅ |
| O-1 suggest_view 缺 rsvg 吞成 `{suggested:null}` | 既有优雅降级、非本批引入、超出 F001 范围、非裸 500 → 正确行为，signoff 记账无需动作 | ✅ |

3 硬条件全部满足 → **首轮 PASS 成立，可直接 done。**

---

## 各 Feature 改动摘要（据域报告，未改写判定）

### F001 · api · generator · PASS
- **文件**：`aigc/errors.py`（+`DependencyUnavailable(AIError)`，:23-30）、`aigc/raster.py`（:17-24 缺 rsvg 抛之 + 诊断消息）、`main.py`（:106-109 app 级 handler→503；:180-188 `_dependency_error_response` 助手；三渲染端点 :1198/1850/2744 宽 except 内调用）。
- **核心确证**：对抗探针实测 **DependencyUnavailable→503 且 AIError→500 无回归**（MRO 命中更具体 handler）；`svg_to_png_canvas` 委托 `svg_to_png` 使 AI/实拍路径同受益；架构红线（不引入替代渲染器出图）守住。

### F002 · api · generator · PASS
- **文件**：`aigc/modes.py`（:13-14 两 mode 各增 `thumb_kind`）、`main.py`（:1904/2497/2797 三处缩略图 kind 改取注册表）。
- **核心确证**：全仓 grep `"ai-thumb"`/`"real-thumb"` 字面仅存注册表、渲染路径 0 硬编码残留；`empty-thumb`(`main.py:787`) 上传域字面不变且不入表；写盘值不变 → `renders.json`/artifact 读侧零影响。

### F004 · api · generator · PASS
- **文件**：`baselines.py`（:170 `@contextmanager` 保留；:191-200 flock LOCK_EX|NB+poll；:208-213 finally 仅 UN+close 不 unlink）。
- **核心确证**：全仓 grep `stale_s`=0 命中（mtime+unlink 破锁全删）；独立探针证锁文件 **inode 跨 acquire/release 恒定**（不 unlink+recreate → 删除竞态消除）+ 跨 OFD 真竞争；`test_project_lock_released_when_holder_dies`（fork+SIGKILL）实跑 PASS 证内核自动释放；10 调用点零改、无一传 stale_s（去参安全）。

### F003 · web · generator · PASS
- **文件**：`apps/web/src/app/studio/projects/[id]/real-render/page.tsx`（唯一产品文件）。
- **核心确证**：复用 `fetchBaselineGeometry`+`roomById`+`roomDisplayName` 构 `room_id→label.zh` 映射；:719/:879 角标 + :698 tooltip 显中文名；对真实 `data/projects/D/geometry.json` 仿真 20 房**无一显裸 id**；几何拉取失败 `.catch(()=>null)` 不阻断主流程、优雅回退裸 id；不改后端 photo 结构。

### F005 · web · generator · PASS
- **文件**：`apps/web/src/lib/studioRoutes.tsx`、`apps/web/src/components/studio/shell/StudioSidebar.tsx`。
- **核心确证**：`comingSoon` 字段声明 + 4 处 UI 分支（disabled/徽标/tooltip）+ Badge import 全移除；前置态 `git grep 'comingSoon:\s*true'` 历史 SHA→NONE（本无 true 项，视觉零回归）；fresh `.next` chunks 零 `comingSoon` 残留（陈旧 `out/` 假阳性已排除）。

### F006 · doc · generator · PASS
- **文件**：`docs/编辑器升级计划-20260703.md`（:19-28 状态列）。
- **核心确证**：P1/P3/P4/P5/P6 五处状态变更逐格交叉 `backlog-核对-20260708.md` + 代码 grep/ls 核对无冲突、每处注明依据；P0/P2/P7 正确保持不变；仅改状态列 + 1 行方法说明，选型决策表/内容列/正文零触碰。

---

## 未变更范围

| 事项 | 说明 |
|---|---|
| Horizon 模板 demo 子树移除（backlog 原 F006） | 实测 blast radius 过大（`routes.tsx` 被 rtl/auth variants/NavbarAuth/RTL sidebar 一整片脚手架共用），需独立可达性追溯 → 拆入 `backlog.json` `BL-horizon-template-removal`(medium) |
| `floorplan_core` 几何/渲染字节输出 | 本批 6 项均不改渲染字节，无 golden 重冻 |
| 后端 photo 数据结构（F003） | 房名解析在前端做（几何前端可得），不改后端 |
| `empty-thumb` 上传缩略图（F002） | 上传域非渲染 mode，有意不入 RENDER_MODES |
| 生产 / 部署 / 凭据 | 本批明确不做 |

---

## 预期影响

| 项目 | 改动前 | 改动后 |
|---|---|---|
| 缺 rsvg 时渲染端点 | 裸 HTTP 500（像代码崩溃） | HTTP 503 + 可诊断消息（环境依赖缺失，可修复） |
| 缩略图 kind 来源 | 三处散落硬编码串 | 单一真源 `RENDER_MODES[mode].thumb_kind` |
| project_lock 陈旧锁自愈 | mtime+unlink 破锁（TOCTOU 误删他人新鲜锁） | fcntl.flock 内核自动释放（无删除竞态） |
| real-render 角标 | 裸 `r_live`/`r_foyer` 机器 id | 中文房名（客厅/主卧睡眠区…），优雅回退 |
| comingSoon 死代码 | 字段声明 + 4 UI 死分支 | 全清除，零残留 |
| 编辑器升级计划文档状态列 | P1/P3/P4/P5/P6 多标「待做」（过时） | 与 main 实况一致（✅/🟡/待做）+ 依据 |

---

## 类型检查 / CI

```
# api（本地唯一门，CI 不跑 pytest）
apps/api/tests      : 301 passed in 15.58s
floorplan_core/tests: 131 passed in 0.47s
ruff --select F     : All checks passed (9 changed files)

# web
npx tsc --noEmit    : exit 0, 0 error
yarn lint           : exit 0, 0 error / 7 warning（useViewport.ts 既有，见 S1）
yarn build          : exit 0, Done in 11.40s（real-render 预渲染 house D）

# CI：分支 chore/harness-onboarding 未 push（push main=部署生产，留用户闸门）
```

---

## L2 实测记录

**无 staging 影响 — N/A。** 本批无生产/staging 部署、无真实外部调用、无计费/DNS/数据写入；AI provider 在测试中被 mock。全部为 L1 本地验收。

---

## Ops 副作用记录

**本批次无数据库 ops。** 项目为文件存储无 DB；本批无任何 prod/staging 数据写入或 SQL 操作。

---

## Harness 说明

本批改动经 Harness 状态机快车道流程（planning → building → verifying）交付，首轮 verifying 全 PASS（fix_rounds=0）。fan-out 三域验收由隔离 evaluator subagent 在 fresh context 完成，结论 verbatim 落三份域报告 + 本 signoff。

> `progress.json` 的 `status: "done"` 与 `docs.signoff` 由编排者置（本 evaluator 不写 progress.json / features.json）。

---

## Soft-watch（不阻塞 done，需后续跟进）

| ID | 描述 | 风险等级 | 建议处置 |
|---|---|---|---|
| S1 | `apps/web/src/components/studio/editor/hooks/useViewport.ts` 7 条 `react-hooks/exhaustive-deps` warning（行 126/145/158/177/260/305/308，缺 svgRef/setVp 依赖）。**既有、非 ops-cleanup-b1 引入、本批未触碰该文件。** | low | 已立 `backlog.json` `BL-useviewport-hook-deps`(low)：下个前端小批逐条判断（真缺依赖则补 / 有意省略则 eslint-disable + 理由）。<br>**§15 矩阵说明**：此为 `exhaustive-deps`（非 unused-import 类）warning，若**本批引入**按 §15 应切 fixing；但其为既有且文件未触碰，强令本批 Generator 修无关旧警告属 scope creep → 正解为 soft-watch + backlog 兜底，不阻断本批。 |
| S2 | `suggest_view`(`main.py:1455`) 缺 rsvg 时吞成 `{"suggested": null, "reason": "prep_failed"}`（200）。 | info | 既有 AI 尽力而为优雅降级、非本批引入、超出 F001（渲染端点）acceptance 范围、非裸 500 → **正确行为**，仅记账无需动作。 |

---

## Framework Learnings

### 新坑（候选，待 Planner 于 done 阶段消化）
- **本机 ruff 0.15.20 与仓库格式基线不一致**：`ruff.toml` 缺 `[lint.isort] known-first-party`（`main`/`aigc`/`baselines`/`furnish`/`schemes`/`floorplan_core`），致 `ruff format .` / `ruff check --fix .`（CLAUDE.md 文档命令）会对**全仓所有文件**重排 import 分组、`I001` 假阳性对全仓皆报；且 CI 不跑 ruff。
  - 来源：ops-cleanup-b1 building（session_notes 已标）+ api 域验收（`--select F` pyflakes 才是真错门）。
  - 建议处置：Planner 于 done 阶段确认后，或补 `ruff.toml` `known-first-party`，或在 CLAUDE.md 显式标注「本机 ruff 只用 `--select F` 报告态查真错，勿全仓 `--fix`」。已在 api 域报告 §6 记账。

> 以上为 signoff 内提案，Planner 在 done 阶段与用户确认后决定是否写入 `framework/` / `ruff.toml` / CLAUDE.md。本 evaluator 不改 framework 基线文件。
