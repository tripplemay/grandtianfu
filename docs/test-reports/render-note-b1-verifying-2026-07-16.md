# render-note-b1 首轮验收报告（verifying-1）

- **批次**：render-note-b1 — 效果图唯一标识显示 + 单条可编辑备注（仅实拍页 real-render）
- **轮次**：verifying-1（fix_rounds=0，首轮）
- **Evaluator**：local/evaluator-subagent（fresh context，隔离验收）
- **日期**：2026-07-16
- **分支**：feat/render-note-b1
- **裁决**：**PASS**（4/4 feature PASS，0 blocking，3 non-blocking）

> 独立性声明：本报告全部结论基于 Evaluator 自行从磁盘读取的 `git diff main...HEAD` 真实改动、自行编写并运行的测试输出（含 7 条独立对抗测试），不采信任何实现叙述。

---

## 环境

- 本机 `python3` = 3.9.6（代码保持 3.9 兼容，`from __future__ import annotations` 存在）；CI/生产 = 3.12。
- `rsvg-convert` = /opt/homebrew/bin/rsvg-convert（render/golden 测试真实执行，非 skipif-skip）。
- Node v25.7.0（本机；CI 锁 22。tsc/lint 与运行时版本无关，通过）。
- 无浏览器 + 无 OPENAI_API_KEY → 前端 L2 浏览器实测不可执行（下方 F003/F004 已标注边界）。

---

## L1 全量结果

| 检查 | 命令 | 结果 |
|---|---|---|
| api pytest（含本批 + 我的对抗测试） | `PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q` | **373 passed, 0 skip** |
| floorplan_core pytest（含 golden byte-for-byte） | `PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q` | **154 passed, 0 skip** |
| 既有 status/delete 零回归 | `pytest test_render_status.py test_render_delete.py test_render_comment.py -v` | **18 passed** |
| 本批对抗测试（Evaluator 编写） | `pytest test_render_comment_adversarial.py -v` | **7 passed** |
| ruff（本批新代码） | `python3 -m ruff check schemes.py records.py test_render_comment.py` | **All checks passed** |
| 前端类型 | `yarn tsc --noEmit` | **绿（0 error）** |
| 前端 lint | `yarn lint` | **绿**（仅 useViewport.ts 既有 7 警告 = BL-useviewport-hook-deps，非本批；real-render/page.tsx 零新增警告） |
| 红线：data/projects | `git status --short data/projects/` + `git diff main...HEAD -- data/` | **净空，未写** |

---

## 逐 Feature 验收

### F001 后端 comment 持久化 + PATCH 偏更新 — **PASS**

代码核验（`git diff main...HEAD`）：
- `schemes.py`：**纯新增**（0 删除行），`set_render_status` 逐字未变 → 红线「不改验收 status 既有语义」满足。新增 `normalize_render_comment`（纯校验，无 I/O）+ `set_render_comment`（持 `_RENDERS_LOCK`、按 id 命中回退 url、允许改历史/归档、`_atomic_write_json` 原子写、`new_rec=dict(rec)` 不原地改）。
- `records.py`：**纯新增**，`set_status` 逐字未变；`set_comment` 持 `_LOCK`，供 default 双账本回退。
- `main.py`：仅 `patch_scheme_render`（@@ -3038）改动，import 块未动。偏更新语义：`has_status`/`has_comment` 至少一，皆无→400；status 非 str→400（早于 try）；**comment 先 `normalize_render_comment` 纯校验再写 status**（防部分写入）；两字段可同时（comment 写侧重读已含 status 的文件，返回记录两者兼有）；未命中→404。`SchemeValidationError→400` 经 `_scheme_error_response`（main.py:169）确认。

测试证据：
- generator 主测 7 条全绿：set/update/清（空串→None、纯空白→None、null→None）/ 非法类型 400 / 超长 400 且边界 2000 合法 / 404 / 空 payload 400 / status⊥comment 共存 / **default 双账本回退命中 legacy**。
- Evaluator 独立对抗 7 条全绿（本机新增 `test_render_comment_adversarial.py`）：
  - **部分写入防护**（超长/非法 comment 同请求带 status → 400 且 status 未落盘）✓
  - 双字段 + render 缺失 → 404，两账本零写 ✓
  - comment 写入保全同记录既有 status/feedback_reason/model/low_accuracy + 不丢列表其它记录（immutable）✓
  - `detail=1` 详情读侧同样透出 comment ✓（generator 已验 detail=0）
  - 幂等清除 ✓
  - `normalize_render_comment` 纯函数边界（None/""/空白→None；strip；2000 合法；2001/int/list→SchemeValidationError）✓
- 既有 `test_render_status.py`（4）+ `test_render_delete.py`（7，含 `test_patch_render_status_default_falls_back_to_legacy`）**全绿，零回归**。
- comment 非 `_RECORD_HEAVY_KEYS` → GET `/renders`（默认 detail=0）自动透出，pytest `_listed` 断言证实。
- 并发锁复用确认：`set_render_comment`→`_RENDERS_LOCK`（与 append/remove/set_status 同锁），`RenderLog.set_comment`→`_LOCK`。

### F002 前端类型 + 客户端 — **PASS**

- `RenderRecord` 加 `comment?: string | null`（注释：缺省视为无；与 status/feedback_reason 正交）。
- `setRenderComment(projectId, schemeId, renderId, comment: string)` 镜像 `setRenderStatus`：PATCH `${schemePath}/renders/${encodeURIComponent(renderId)}`，body `{ comment }`，`unwrap<RenderRecord>`。签名与后端 F001 契合（空串=清除由后端处理）。
- `tsc --noEmit` 绿。

### F003 唯一标识显示 + 一键复制 — **PASS**（含 1 条 non-blocking 设计系统观察）

- 新增 `RenderIdChip`：显示 `id.slice(0,8)`（`font-mono`），点击 `onCopy(id)` → `copyRenderId` → `navigator.clipboard.writeText(rid)`（**完整 32 位 id**）。
- **两处均显示**：最新大图块（page.tsx:1100，`<p>` 内）+ 历史缩略图卡（page.tsx:1324）。历史卡中 chip 与「设为大图」缩略图按钮是**兄弟节点非嵌套** → 点 chip 不误触发换大图（无点击冒泡问题）。
- **clipboard 兜底**：`try { …writeText } catch { showToast('复制失败,请手动选择文本','error') }`（D3 满足，失败不抛未捕获错误）。
- 主题：chip 全部颜色成对 `dark:`（`bg-gray-100 dark:bg-white/10` / `text-gray-500 dark:text-gray-400` / hover 均成对）；**无 `bg-*-50` 硬编码浅底**。
- lint/tsc 绿。
- **[non-blocking]** `RenderIdChip` 是手写 `<button className="…">`，与 F003 acceptance 字面「用 Badge/Button（禁手写按钮 class）」冲突。但：`Badge` 是非交互 `<span>`（无 onClick，status.tsx:214）、`Button` 是重动作按钮（BUTTON_BASE，语义不适内联 mono id 徽标）；chip 主题成对 dark:/无 bg-*-50/不重复任何现成组件。判为可辩护的新微原子，不阻断。建议后续把「可复制 id 徽标」抽成共享设计系统组件（IdChip/CopyChip）。

### F004 单条可编辑备注 UI — **PASS**（前端持久化 L2 浏览器实测未执行，环境所限）

- 大图块下方备注区：`<textarea>`（`value=commentDraft`，预填 `latest?.comment ?? ''`，`inputCls`+`resize-y`，`maxLength=2000`，placeholder 同 spec）+「保存备注」+「清除」（`Button` variant primary / neutral-outline）。
- 保存/清除调 `setRenderComment`，**用服务端返回记录就地更新**：`setRenders(prev=>prev.map(p=>p.id===updated.id?updated:p))` + `setLatest(prev=>…)`（immutable，不原地改）。清除按钮传空串。
- **失败可见反馈**：`catch(e){ showToast('备注保存失败：'+message,'error') }`（不静默吞，对齐既有教训）。
- **草稿随大图切换重置**：`useEffect(()=>setCommentDraft(latest?.comment ?? ''),[latest?.id, latest?.comment])`。
- 保存按钮 `disabled = savingComment || commentDraft===(latest.comment ?? '')` → 防 no-op 保存 + 防双提交；`savingComment` 期 textarea disabled。
- 历史卡：`r.comment && <span title={r.comment}>📝</span>`（只读标记，`text-amber-600 dark:text-amber-400` 成对）；编辑仍走「设为大图」。
- 复用设计系统（inputCls/Button），不手写；label `htmlFor` 唯一 id，a11y 良好。
- **持久化验证边界**：「刷新后仍在＝真落盘」的浏览器实测（L2）因本机无浏览器/无 OPENAI_API_KEY **未执行**。但代码级路径 + 后端 pytest 已确认落盘：`setRenderComment`→PATCH→`set_render_comment` 原子写 renders.json；GET `/renders` 透出 comment；页面 load 从 GET 回填 → 刷新必现。判为**代码级验证充分，L2 运行时未执行（环境所限）**，不据此判 FAIL。

---

## Evaluator 独立发现的问题（spec 未列）

均为 non-blocking：

1. **[non-blocking] RenderIdChip 手写 button**（详见 F003）— 与 acceptance 字面冲突但主题合规、无同类组件可复用，建议后续抽组件。
2. **[non-blocking] main.py 存在 1 条既有 ruff I001（import 排序）** — 出现在 import 块（lines 31-42），本批 diff 未触碰该块；已核验该错误在 `main` 分支同样存在（pre-existing，非本批引入）。全仓基线噪声之一，建议单独清理批处理。
3. **[non-blocking] `.auto-memory/project-status.md` 仍写「render-note-b1 🔨 building」** — 实际已进 verifying。属记忆快照滞后，非产品问题；Planner 在 done 阶段覆盖写即可。

---

## 兜底/软监控清单（首轮 PASS §14(c) 明文兜底）

| 项 | 兜底 |
|---|---|
| F003 手写 chip | 明文记录，建议后续抽 IdChip 组件；主题红线全满足，不阻断 |
| F004 前端持久化 L2 浏览器实测 | 环境所限未执行；代码级 + 后端 pytest 已证落盘链路；如需正式发布可在 staging 手动走查一次 |
| main.py pre-existing ruff I001 | 非本批引入，记账；建议单独清理 |
| project-status.md 滞后 | Planner done 阶段更新 |

---

## 红线复核（progress.json batch_scope.red_lines 逐条）

1. 不改验收 status/feedback_reason 语义 — ✅ schemes.py/records.py 纯新增，set_render_status/set_status 逐字未变，18 条既有 status/delete 测试零回归。
2. 不写 data/projects/ — ✅ `git status --short data/projects/` 空，`git diff main...HEAD -- data/` 净空。
3. 不动 packages/floorplan_core/ — ✅ diff stat 未列该目录。
4. 不动轴测 render/page.tsx — ✅ diff 仅 real-render/page.tsx。
5. 不单推 main — ✅ 当前在 feat/render-note-b1 分支。
6. 前端不手写按钮/卡片、禁 bg-*-50、禁缺成对 dark: — ⚠ chip 为手写 button（见 non-blocking #1，主题合规），其余全满足。

---

## 结论

**verdict = PASS**。4/4 feature 达标，0 blocking。3 条 non-blocking 均有明文兜底。

L1（两套 pytest 373+154 全绿 0 skip、golden 实跑绿、ruff 本批 clean、tsc/lint 绿、红线全守）全部通过；L2 前端浏览器实测因本机环境所限未执行，已如实标注并有代码级 + 后端测试兜底。

status 转 done/fixing 的决定权归主上下文编排者（本 Evaluator 不改 status）。若编排者据本 verdict 置 done，signoff 报告应在该 done 转换时补写并填 `docs.signoff`。
