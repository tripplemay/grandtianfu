# render-note-b1 — 效果图唯一标识显示 + 单条可编辑备注

> 批次类型：新功能批次（硬性 spec）。车道：快车道（同会话）。
> Planner 确认于 2026-07-16，用户「开工」授权 spec lock。

## 1. 背景与目标

**问题：** 用户在实拍效果图页面（`real-render`）评估一张张出图、给出优化意见时，缺两样东西：

1. **无法精确指代某张图** —— 每条 render 记录其实早有唯一 `id`（32 位 hex，如 `f4dab9bcf714495c90bbdcaf6e4d8ebb`），但页面上**只用于下载文件名 / alt 文本，从不显示**。用户口头说"那张沙发偏大的图"无法和 agent 对齐到具体记录。
2. **意见留不下来** —— 现有反馈只有 `status`(accepted/rejected) + `feedback_reason`（枚举驳回原因），是**验收态**，不是自由文本意见。用户想对某张图写一句"沙发偏大、窗帘要落地"，没有承载。

**目标：** 在实拍效果图页显示每张图的唯一标识（可一键复制），并为每张图提供**单条可编辑备注**。备注持久化进**生产 `renders.json`**，形成闭环——下一轮优化时 agent 可直接读取用户对每张图的意见，做针对性修改。

**用户决策（2026-07-16）：**
- 评论形态 = **单条可编辑备注**（每张图一个备注框，随时覆盖编辑，只保留最新一句；不是多条时间线）。
- 适用范围 = **仅实拍效果图页**（`real-render`；不含轴测 `render` 页）。

**非目标：** 不做多条留言 / agent 回帖 / 权限 / @提及；不动轴测效果图页；不改验收 `status`/`feedback_reason` 语义（备注与验收态**完全正交**，独立读写）。

## 2. 功能范围

| # | 功能 | executor | 层 |
|---|---|---|---|
| F001 | 后端：render 记录 `comment` 字段持久化 + PATCH 端点扩展 | generator | apps/api |
| F002 | 前端：`RenderRecord.comment` 类型 + `setRenderComment` API 客户端 | generator | apps/web |
| F003 | 前端：唯一标识显示（短 id + 一键复制完整 id） | generator | apps/web |
| F004 | 前端：单条可编辑备注 UI | generator | apps/web |

全部 `executor:generator` → 普通批次，`planning → building → verifying → done`。

## 3. 关键设计决策

### D1. `comment` 存进 render 记录本身，复用现成加锁账本（不新增存储）
`renders.json` 是文件存储（列表，最新在前），已有一套**加锁读-改-写 + 原子落盘（tmp+os.replace）**：
- 方案级：`schemes.set_render_status`（`apps/api/schemes.py:828`，持 `_RENDERS_LOCK`，按 `id` 命中、回退 `url`，允许改历史/归档记录）
- legacy 账本：`RenderLog.set_status`（`apps/api/aigc/records.py:46`，持 `_LOCK`；`default` 方案老出图经 `_list_default_renders` 合并此账本，改状态须双账本回退）

`comment` **镜像这两个函数**新增 `set_render_comment` / `RenderLog.set_comment`，不发明新存储路径。`comment` 不在 `_RECORD_HEAVY_KEYS=("scene_manifest","usage","prompt")`（`main.py:2943`）中 → GET `/renders` 列表读侧**自动透出**，无需改 `_shape_render_records`。

### D2. PATCH 端点扩展为「偏更新」，`status` 与 `comment` 正交独立
现有 `PATCH /api/projects/{house}/schemes/{scheme_id}/renders/{render_id}`（`main.py:3037`）目前**强制** `status: str`。改为**偏更新（partial update）**语义：
- payload 含 `status` → 走**原路径**（`set_render_status`，词表校验 + default 双账本回退），**逐字节不改动，零回归**。
- payload 含 `comment` → 走**新路径**（`set_render_comment`，default 双账本回退）。
- 两者可同时出现（各自独立应用，返回最终记录）；两者都无 → 400。
- **兼容铁律：** 既有 `setRenderStatus` 客户端只发 `{status}` / `{status, feedback_reason}`，其行为必须**逐字不变**（现有 pytest 保持绿）。

`comment` 值语义：
- `str` → `strip()` 后写入；**空串 `""` → 存 `None`（= 清除备注）**（与 `feedback_reason` 的 `strip() or None` 一致，`schemes.py:862`）。
- `None` → 清除备注。
- 非 `str`/非 `None` → 400（`"comment 必须为字符串或 null"`）。
- 长度上限：**2000 字符**（防滥用/超大载荷；超限 400）。

### D3. 唯一标识：短 id 展示 + 点击复制完整 id
- 展示 **短 id = 完整 id 前 8 位**，等宽字体，配一个复制动作。
- 点击复制**完整 32 位 id** 到剪贴板（`navigator.clipboard.writeText`），成功给一次轻反馈（复用现成 Toast/临时"已复制"态）。`navigator.clipboard` 在非安全上下文不可用 → **必须 try/catch 兜底**（失败不抛未捕获错误；生产是 https，正常可用）。
- 位置：**「最新实拍效果图」大图块** + **历史缩略图卡**都显示（用户在两处都可能想指代某张图）。

### D4. 备注 UI：最新大图块可编辑，历史卡只读标记
- **「最新实拍效果图」大图块**下方加**备注区**：`<textarea>`（预填该记录现有 `comment`）+「保存」+「清除」。保存调 `setRenderComment`，**乐观更新** `renders`/`latest` 本地状态（immutable 复制，不原地改），失败 `catch` 给可见错误（不静默吞——对齐 `real-render` 既有 `patchBaselinePhoto` 曾静默吞的教训注释，`page.tsx:186-188`）。空态 placeholder：「写下你对这张图的意见，方便下一轮针对性修改」。
- **历史缩略图卡**：有备注 → 显示 📝 标记（只读）；点缩略图会「设为大图查看」（既有交互 `page.tsx:1188-1192`），在大图块编辑。（用户决策：历史卡不直接可编辑。）

### D5. 复用设计系统组件，不手写（记忆红线）
参见 `.auto-memory` [[grandtianfu-reuse-design-system]]：
- 卡片 `StudioCard`（`components/studio/ui/primitives`）、按钮 `Button`（`components/studio/ui/buttons`，用 `variant`，禁手写按钮 class）、徽章 `Badge`（`components/studio/ui/status`）。
- 备注 `<textarea>` 复用 `inputCls`（`lib/floorplan/fieldStyles`，`fields.tsx` 已用）；**若在 `fields.tsx` 加一个 `Textarea`/`CommentField` 组件更内聚，可加**（reuse `inputCls`）。
- **禁**硬编码浅底 `bg-*-50`；**禁**缺成对 `dark:`。深浅主题都须验。
- **无 `design-draft/` 原型**（已 `ls` 确认目录不存在）→ 本批不需要同步设计稿（Planner §2.5 检查通过：additive UI，非页面架构变更）。

## 4. 接口 / 数据模型

### 4.1 render 记录新增字段
```jsonc
{
  "id": "f4dab9bcf714495c90bbdcaf6e4d8ebb",
  "url": "/api/artifacts/...",
  "status": "accepted",            // 既有：验收态（正交）
  "feedback_reason": null,          // 既有：驳回原因（正交）
  "comment": "沙发偏大，窗帘要落地"   // 新增：单条可编辑备注（str | null；缺省视为无备注）
}
```

### 4.2 PATCH（偏更新）
`PATCH /api/projects/{house}/schemes/{scheme_id}/renders/{render_id}`
```jsonc
// 备注写入 / 更新
{ "comment": "沙发偏大，窗帘要落地" }
// 备注清除
{ "comment": "" }      // 或 { "comment": null }
// 验收态（既有，行为不变）
{ "status": "accepted" }
```
返回：更新后的完整 render 记录（200）；未命中 render_id → 404；非法 payload → 400。

### 4.3 前端类型 + 客户端（`apps/web/src/lib/studioApi.ts`）
```ts
export interface RenderRecord {
  // ...既有字段
  comment?: string | null;   // 新增
}

// 镜像 setRenderStatus（studioApi.ts:1007）
export async function setRenderComment(
  projectId: string, schemeId: string, renderId: string,
  comment: string,                // 空串 = 清除
): Promise<RenderRecord>;          // PATCH { comment }
```

## 5. 车道与编排（Planner §6.5）

- **车道 = 快车道（同会话）**：单会话承载，无跨机 `role_assignments`、不跨多日。
- **building 编排 = 主上下文顺序实现**：F001→F002→F003/F004。F003/F004 同文件（`real-render/page.tsx`），不并行 worktree（会冲突）；批次小，顺序即可。
- **verifying = 隔离 evaluator subagent**（fresh context，无自评铁律）。4 features 但高度内聚（一个前端页 + 一个后端字段），单 evaluator 分维度即可，不强制 fan-out。
- **红线：** 不单推 `main`（= 部署生产）；走 branch `feat/render-note-b1` → PR → squash。测试产物随 PR 走。

## 6. 验收要点（Evaluator 展开）

1. **F001 持久化**：pytest 覆盖 set / update / clear（空串→None）/ 404 / `default` 双账本回退 / 非法类型 400 / 超长 400 / `comment` 出现在 GET `/renders` 返回；**既有 `set_render_status` / PATCH status 路径测试全绿（零回归）**。
2. **F001 并发安全**：`set_render_comment` 复用同一把锁（`_RENDERS_LOCK` / `_LOCK`），不与 append 竞争。
3. **F002**：`tsc` 绿；`setRenderComment` 签名与后端契合。
4. **F003**：页面显示短 id；点击复制得到完整 32 位 id；`clipboard` 失败有兜底不崩；深浅色都不突兀。
5. **F004**：写 / 改 / 清备注均持久化（**刷新页面后仍在** = 真落盘，非仅本地态）；失败有可见反馈；历史卡 📝 标记正确；用设计系统组件、成对 `dark:`、不手写。
6. **全局**：两套 pytest + golden 实跑全绿 0 skip；`yarn lint` + `tsc` 绿；未写 `data/projects/`。
