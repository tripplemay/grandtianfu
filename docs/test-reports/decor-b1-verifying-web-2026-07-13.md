# decor-b1 验收报告 · Web 域（F006 / F007）

- **批次**：decor-b1（软装配饰 · 引擎 + 编辑器基座）
- **域**：Web（前端编辑器）—— 三域 fan-out 之一
- **阶段**：verifying（首轮）
- **验收人**：local/evaluator-subagent（隔离上下文，fresh context）
- **日期**：2026-07-13
- **方式**：静态代码取证 + 前后端一致性程序化比对 + 三门实跑（tsc / lint / build）
- **边界**：本报告仅覆盖 F006 / F007。F001–F005/F008（引擎·API 域）、F009（floorplan_core 对抗验收）由其他域独立出报告。

## 结论速览

| Feature | Verdict | 三门 | 关键证据 |
|---|---|---|---|
| F006 前端独立配饰摆放 + 换件透传 | **PASS** | 全绿 | 装饰组自动并入（非硬编码）+ swapFurnitureType D11 透传过滤 |
| F007 附着配饰编辑（SidePanel 配饰分节） | **PASS** | 全绿 | 合法宿主门控 + 专用数组 handler toggleFurnDecor + posLocked 可编辑 + 成对 dark: |

前后端 `DECOR_ATTACH.hosts` 逐类程序化比对 **完全一致**（5/5）。

---

## 一、三门输出（Node v22.22.0，`apps/web`）

> 环境：默认 `node` 为 Homebrew v25.7.0，按项目约定用 nvm node 22 跑门
> （`PATH` 前置 `~/.nvm/versions/node/v22.22.0/bin`）。yarn 1.22.22。

### 门 1 — `npx tsc --noEmit`
```
TSC_EXIT=0
```
✅ 零类型错误。

### 门 2 — `yarn lint`（next lint）
```
./src/components/studio/editor/hooks/useViewport.ts
126:6 … 145:5 … 158:5 … 177:5 … 260:5 … 305:5 … 308:73
  react-hooks/exhaustive-deps  (共 7 条 Warning)
Done in 3.55s.
```
✅ 仅 `useViewport.ts` 7 条 exhaustive-deps warning —— 即既有历史遗留
**BL-useviewport-hook-deps，非本批，按 team-lead 指令不计入**。
F006/F007 涉及文件（`decorAttach.ts` / `furniture.ts` /
`FurnitureSidePanel.tsx` / `useFurnitureEditor.ts` / `FurnitureMode.tsx`）
**零新增告警/错误**。

### 门 3 — `yarn build`（Next.js 15 静态导出）
```
├ ● /studio/projects/[id]/editor          41.8 kB         172 kB
│   └ /studio/projects/D/editor
…
Done in 14.17s.
```
✅ 构建成功，编辑器路由（承载家具编辑器）正常预渲染静态导出。

---

## 二、前后端一致性核对（decorAttach.ts ↔ catalog.DECOR_ATTACH）

程序化解析两处 hosts 白名单逐类比对（脚本比对 keys 集合，front 不含 mount_z）：

```
  bedding     match=True   [bed, bunk_bed, kids_bed]
  cushions    match=True   [armchair, bed, bunk_bed, chaise, kids_bed, sofa]
  ornament    match=True   [coffee_table, console_table, dining_table, media, side_table, sideboard]
  table_lamp  match=True   [console_table, desk, nightstand, side_table, sideboard]
  vase        match=True   [coffee_table, console_table, dining_table, media, side_table, sideboard]
ALL HOSTS CONSISTENT: True
```

- 5 类附着配饰 hosts 白名单 **逐类一致**（spec §3.3 为准）。
- 前端镜像正确 **不携带 mount_z**（纯后端渲染参数，spec §3.3 明确）——非缺陷。
- 注：后端 mount_z 部分数值与 spec 草案微调（chaise 405/kids_bed 400/desk 750），
  属引擎域 F003 范畴（spec 允许 Generator 对齐实际 3D 模型微调），不影响 web 域一致性。

---

## 三、F006 逐条对抗核查 · PASS

**acceptance（features.json / spec §5 F006）** 与实物对照：

1. **wall_art/curtain 自动并入「装饰」组（非硬编码白名单）** ✅
   - `furniture.ts:187-228` `FURN_CATEGORY_DEFS` decor 组 `types: ['plant','rug','partition','entry_door']`
     —— **不含** wall_art/curtain（未硬编码）。
   - `furniture.ts:233-256` `furnCategories()`：对未静态归类的 catalog 类型按
     `byKey.get(e.category)` 归组（`furniture.ts:243-247`）。
   - `catalog.py:189-196` wall_art/curtain `category:"decor"`；`to_public()`
     （`catalog.py:469`）下发 `category` → 前端据 category 自动落「装饰」组。
     **对抗结论：category 驱动，非白名单硬编码，符合要求。**

2. **swapFurnitureType 从头构造 next 后透传 decor 并按新宿主 hosts 过滤（D11）** ✅
   - `furniture.ts:538-576`：`next` 白名单式**从头构造**（t/id/room_id/rot/zorder/
     label/color/尺寸），最后 `furniture.ts:570-574` 显式透传 —— 非盲拷 `it.decor`。
   - 过滤：`allowed = new Set(decorTypesForHost(newType))`，
     `kept = it.decor.filter(d => allowed.has(d.t))`，`kept.length` 才落 `next.decor`。
   - 对抗推演：
     - sofa→armchair：cushions.hosts∋armchair → 保留 ✅
     - sofa→chaise：cushions/… ∋chaise → 保留 ✅
     - sofa→coffee_table：`decorTypesForHost('coffee_table')=[vase,ornament]`，
       cushions 不在 → **剥离** ✅
     - 换到圆形件（round_table/round_chair）：不在任何 hosts →
       `decorTypesForHost` 空 → **全剥**，不落 decor 键 ✅
     **符合 D11 前端侧。**

3. **换件 UI 走 swapFurnitureType** ✅
   - SidePanel `SelectRow 换件`（`FurnitureSidePanel.tsx:135-141`）→ `onSetField('t', v)`
     → `useFurnitureEditor.ts:581-588` 命中 `field==='t'` 分支 → `swapFurnitureType`。

4. **拖放/点选/贴墙吸附/换件复用既有** ✅
   - wall_art/curtain 为 `shape:rect`+`directional` → 走矩形路径。
   - `buildFurnitureAt`（`furniture.ts:439`）/ `clampToRoom`（:679）/ `snapToWall`（:715）
     皆为通用矩形逻辑，无类型白名单排除；`dropFurniture`（`useFurnitureEditor.ts:671`）通用。

5. **画布孪生渲染新薄件（2D 贴墙矩形）** ✅
   - `FurnitureItem.tsx:165-178` 非圆形件统一渲染通用 `<rect>`（无类型排除白名单）。
   - `furnColor`（`furniture.ts:173-176`）回退 `catalog.color2d`（wall_art `#e8dcc8` /
     curtain `#ded6e2`，`to_public` 由 cat2d[0] 下发）→ 新件获合理画布色。

**判定：F006 PASS。**

---

## 四、F007 逐条对抗核查 · PASS

1. **配饰分节只对合法宿主显示** ✅
   - `FurnitureSidePanel.tsx:82` `decorHosts = decorTypesForHost(item.t)`；
     `:219` `{decorHosts.length > 0 && (…)}` 门控。
   - 非宿主（wall_art / toilet / 圆形件等）→ `decorTypesForHost` 返回 `[]` → 分节隐藏 ✅。

2. **数组字段走专用 handler toggleFurnDecor（非标量 onSetFurnField 通道）** ✅
   - checkbox `onChange={() => onToggleDecor(dt)}`（`:235`）→ `FurnitureMode.tsx:192`
     `onToggleDecor={furn.toggleFurnDecor}` → `useFurnitureEditor.ts:613-632` 专用
     `toggleFurnDecor`。
   - `onSetFurnField`（:577）仅处理标量 t/w/h/orient/rot/label/color；**decor 不经标量通道**。

3. **增删走 immutable 更新 + 保存** ✅
   - `toggleFurnDecor`：`map` + 展开 `{...it}`，toggle `nextDecor`，`nextDecor.length`
     则 `next.decor=…` 否则 `delete next.decor`（空列表删键，保盘上格式干净）。
   - 走 `updateFurniture`（`:159-170`）→ 置 `dirty` → `onSaveFurn`（:829）。
   - **持久化不丢 decor**：`stripRuntimeFields`（`furniture.ts:922-928`）仅剥 `id`，
     `...rest` 保留 decor → save 往返无损。

4. **posLocked 下仍可编辑配饰** ✅
   - `toggleFurnDecor`（`useFurnitureEditor.ts:613`）**无 positionLocked 守卫**
     （对比 `nudge`:737 / `alignFurn`:793 / `onFurnItemDown`:258 皆有 lock 早返回）。
   - 配饰分节渲染不受 posLocked 影响（`:219` 仅按 decorHosts 门控）。符合「换件不挪位」场景。

5. **深色主题成对 dark:（无硬编码浅底 bg-*-50）** ✅
   - 分节容器 `border-gray-100 dark:border-white/5`（`:221`）
   - 标题 `text-gray-500 dark:text-gray-300`（`:224`）
   - 勾选项 `text-navy-700 dark:text-gray-200`（`:231`）
   - **无** 硬编码浅底 `bg-*-50`（无成对 dark: 的深色主题突兀白底）。符合项目 dark 规范。

**判定：F007 PASS。**

---

## 五、观察项（非 FAIL，硬化建议）

1. **[MINOR] web 域无自动化单测覆盖纯函数**：`decorTypesForHost` /
   `swapFurnitureType` 的 decor 过滤 / `toggleFurnDecor` 均为易测纯逻辑，但 web 项目
   仅有 Playwright e2e（无 jest/vitest runner），且无 decor 相关 e2e spec。
   acceptance 只要求 tsc/lint/build + 手动冒烟，**故不构成 FAIL**；建议 b2 补
   前端纯函数单测（换件透传矩阵 / toggle 增删 / 宿主门控）以固化回归防线。
2. **[INFO] 手动编辑器冒烟未运行时执行**：spec §6「摆挂画→轴测预览可见」属浏览器
   交互 L1，本次以静态代码路径核验（drag/drop/rect 渲染均复用已上线通用逻辑，且
   build 成功）替代，未做真实浏览器点击。建议签收前由人做一次 5 分钟编辑器冒烟
   （拖挂画贴墙 + 给沙发勾抱枕 + 沙发换贵妃榻查配饰保留 / 换茶几查剥离）。

---

## 六、签收结论（web 域）

| Feature | Verdict |
|---|---|
| **F006** 前端独立配饰摆放 + 换件透传 | **PASS** |
| **F007** 附着配饰编辑（SidePanel 配饰分节） | **PASS** |

- 三门（tsc / lint / build）全绿，仅历史 BL-useviewport-hook-deps 告警（非本批）。
- 前后端 DECOR_ATTACH.hosts 逐类一致（5/5）。
- D11 换件透传 + 按新宿主过滤、F007 专用数组通道 + posLocked 可编辑 + 成对 dark:
  均与实物一致。
- 无产品代码改动（本报告仅新增 docs/test-reports/ 产物）。
