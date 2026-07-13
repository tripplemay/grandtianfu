# ops-cleanup-b1 · verifying · web 域验收报告

- **批次**：ops-cleanup-b1
- **域**：web（F003 / F005），fan-out 三域之一（api=F001/F002/F004，doc=F006 另评）
- **阶段**：verifying（首轮，fix_rounds=0）
- **验收人**：local/evaluator-subagent（隔离上下文）
- **日期**：2026-07-13
- **取证基底**：`git diff 97c33a4..HEAD -- apps/web`，commits `782c826..d0d8c2a`
- **判定依据**：实际代码 + tsc/lint/build 输出 + 对 `data/projects/D/geometry.json` 的真实数据仿真。忽略任何"已实现/已测试"叙述。
- **L2**：本域无 L2（纯前端展示 / 死代码清理，无生产/计费/写入）。全部 L1 本地。

---

## 工具门（L1）输出摘要

| 命令 | 结果 | 备注 |
|---|---|---|
| `npx tsc --noEmit` | **exit 0**，零错误 | Node v25.7.0（CLAUDE.md 建议 22；tsc 不受影响） |
| `yarn lint` (`next lint`) | **exit 0**，0 error / 7 warning | 7 条 warning 全在 `src/components/studio/editor/hooks/useViewport.ts`（`react-hooks/exhaustive-deps`），**本批未触碰该文件、非本批引入**。本域三个改动文件（page.tsx / StudioSidebar.tsx / studioRoutes.tsx）**零 warning** |
| `yarn build` (`next build`) | **exit 0**，`Done in 11.40s` | `/studio/projects/[id]/real-render` 成功预渲染（house D，12.3 kB） |

> **环境澄清（避免误报）：** `yarn build` = `next build`，**不**生成静态导出 `out/`（那需 `yarn build:export` = `NEXT_OUTPUT_EXPORT=1 next build`）。仓库内 `out/` 是 **2026-07-09 的陈旧产物**（layout chunk mtime `2026-07-09 01:21`，早于 F005），其中残留 `comingSoon`×4 属陈旧假阳性。以**本会话 fresh `.next`**（`BUILD_ID` mtime `2026-07-13 11:28`）为准：`grep -rl comingSoon .next/static/chunks/` → **NONE**。

---

## F003 — real-render 角标显中文房名（非裸 room_id）· medium · **PASS**

**改动文件**：`apps/web/src/app/studio/projects/[id]/real-render/page.tsx`（唯一产品文件，commit `7d896b3`）

### Acceptance 逐条核对

| # | Acceptance | 结果 | 证据 |
|---|---|---|---|
| 1 | 构建 `room_id → label.zh` 映射（复用页面已有几何加载） | ✅ | `page.tsx:23` 引 `fetchBaselineGeometry`；`:40-41` 引 `roomById`(`lib/floorplan/geometry`)、`roomDisplayName`(`lib/floorplan/merge`)；`:386` 在既有 `reload()` 的 `Promise.all` 中并行拉几何；`:340-344` `roomName()` helper 组织映射 |
| 2 | `:703`/`:863` 两角标改中文名（现 `:719`/`:879`）；回退链 `label.zh → room_id → '未标注房间'` | ✅ | 徽标 `:719` `{roomName(photo.room_id) \|\| '未标注房间'}`；详情"房间"字段 `:879` `{roomName(selectedObj.room_id) \|\| '未标注'}`。仿真见下表 |
| 3 | `:683` tooltip 同步复用映射（现 `:698`，nice-to-have） | ✅ | `:698` `title={photo.note \|\| roomName(photo.room_id) \|\| '空房照片'}` |
| 4 | 未标注房间（room_id 空）行为不变（仍显"未标注房间" + amber 徽标） | ✅ | `roomName(null)` 返 `''` → `\|\| '未标注房间'`；`tone={photo.room_id ? 'green' : 'amber'}`（`:716`）未改，amber 徽标保留 |
| 5 | 无对应几何房间时回退 `room_id`（不吞错、不空白） | ✅ | `roomName` 内（`:343`）`room && geometry ? roomDisplayName(...) : roomId`；仿真 `r_ghost → 'r_ghost'` |
| — | 几何拉取失败不阻断主流程 | ✅ | `:386` `fetchBaselineGeometry(...).catch(() => null)`；`:396` `setGeometry(geo ? ... : null)`；失败时几何为 null → 裸 id 回退，status/photos/renders 正常 |
| — | 不改后端 photo 数据结构 | ✅ | F003 commit 仅动 `real-render/page.tsx`（+ 状态文件），零后端改动 |

### 房名解析真实仿真（对 `data/projects/D/geometry.json`，忠实移植 `roomName()`+`roomDisplayName()`）

20 个房间：**18 个由 `label.zh` 直出中文名**（`r_live→餐厅区`、`r_master→主卧睡眠区`、`r_guest2→次卧(二)` …）；2 个 `label.zh=None` 的房（`r_foyer`、`r_corr_pl`）经 `roomDisplayName` 的 space 标签回退，仍得**中文名**（`r_foyer→客厅·餐厅·厨房`、`r_corr_pl→次卧套房`），**无一显示裸 id**。

边界：`room_id=None → '未标注房间'`；`room_id='r_ghost'（无匹配）→ 'r_ghost'`；`几何拉取失败 → 'r_live'（裸 id）`。全部优雅回退，不崩不空白。

### 说明（非缺陷）

- 复用的 `roomDisplayName`（`merge.ts:22`）实际回退链为 `label.zh → spaces[space].label → room.id`，比 spec 字面 `label.zh → room_id` 多一层 **space 标签**中间态。此中间态只在房无 `label.zh` 时触发，且产出仍是中文名（非裸 id），**严格强化** F003 目标"非裸 room_id"，且正是 spec/编排要求"复用 roomById+roomDisplayName"的既有行为 → 不判偏差。
- `fetchBaselineGeometry` 返回 studioApi 的 opaque `Geometry`（`{meta; [k]:unknown}`），故 `geo as unknown as FpGeometry` 双 cast 桥接到结构化 floorplan 类型；tsc 通过，运行时按真实 geometry.json 形状（`rooms[].id/label.zh/space` + `spaces[k].label`）正确读取 → 合理最小桥接，非 code smell。

**判定：PASS**

---

## F005 — comingSoon 死代码清理 · low · **PASS**

**改动文件**：`apps/web/src/lib/studioRoutes.tsx`、`apps/web/src/components/studio/shell/StudioSidebar.tsx`（commit `aa3da06`）

### Acceptance 逐条核对

| # | Acceptance | 结果 | 证据 |
|---|---|---|---|
| 1 | 移除 `studioRoutes.tsx` `comingSoon` 字段声明 + `:38` 过时注释 | ✅ | diff 删除 `comingSoon?: boolean;`（原 `:44`）+ `:35` 注释；`grep comingSoon studioRoutes.tsx` → NONE |
| 2 | 移除 `StudioSidebar.tsx` 所有 comingSoon 分支（disabled/即将/下一阶段徽标/tooltip，`:199/218/246/267`） | ✅ | diff 删 4 处分支 + `disabled` 变量 + `Badge` import（`:20`）；`grep Badge StudioSidebar.tsx` → NONE |
| 3 | 侧栏渲染零回归（本无 `true` 项，视觉零回归） | ✅ | 前置态 `git grep 'comingSoon:\s*true' 97c33a4 -- apps/web/src` → **NONE**：从无任一路由设 `comingSoon:true`，所有项本就可点达，删除死分支无行为影响 |
| 4 | `yarn lint` + `yarn build` 绿；无 comingSoon 残留引用 | ✅ | lint/build exit 0；`grep -rn comingSoon apps/web/src` → NONE；fresh `.next` chunks → NONE |

### 说明（环境假阳性已排除）

`grep comingSoon out/` 曾命中陈旧 `out/`（2026-07-09，`yarn build` 不重建 `out/`）——非产品残留。fresh `.next` 权威结果为零残留；唯一 `即将上线` 命中在 `src/app/studio/settings/page.tsx:15,19`（设置页正文 "设置 · 即将上线"），与侧栏 comingSoon 无关，非 F005 范围。

**判定：PASS**

---

## 汇总

| Feature | 域 | 判定 |
|---|---|---|
| F003 | web | **PASS** |
| F005 | web | **PASS** |

- pass=2 / partial=0 / fail=0（本域）
- L1（tsc / lint / build）全绿；本域改动文件零 lint warning
- **Soft-watch（不阻断，出域外记账）**：`useViewport.ts` 7 条 `react-hooks/exhaustive-deps` warning 为**既有、非本批引入、本批未触碰该文件** → 非 F003/F005 责任；建议后续独立小批清理，不阻断本批。

> 本报告仅覆盖 web 域（F003/F005）。批次整体 done / signoff 需 api 域（F001/F002/F004）+ doc 域（F006）三域汇总后由编排者裁决。本 subagent 不写 progress.json / features.json / signoff。
