# 运维长尾 + 前端死控件清理批 — 规格（ops-cleanup-b1）

> 批次类型：清理 / 修复（普通批次，全部 `executor:generator`）。来源：`docs/backlog-核对-20260708.md` §D.2「运维长尾 + 前端死控件清理批」。
> 立项日期：2026-07-13。所有条目已逐项 grep 实物核对（file:line 见下），确认 2026-07-08 后仍未做。

## 背景与目标

harness 接入后的第一个开发批次。选一批「小改无争议、无产品依赖」的运维长尾与前端死代码，合成一批：既清理真实技术债，又作为快车道 fan-out 验收的首次演练。

**非目标（本批明确不做）：**
- **Horizon 模板 demo 子树完整移除**（backlog 原 F006）——实测 `routes.tsx` 被 `app/rtl` / `components/auth/variants/*` / `NavbarAuth` / `components/sidebar/RTL` 等一整片模板脚手架共用，blast radius 大，需独立可达性追溯。已转入 backlog（见 `backlog.json`）。
- 任何触及 `floorplan_core` 几何/渲染**字节输出**的改动（本批 6 项均不改渲染字节，无需 golden 重冻）。
- 任何生产/部署/凭据操作。

## 车道与编排决策

- **快车道**（单机 `myId=local`，单会话）；`role_assignments=null`，Evaluator 走隔离 subagent。
- **building**：主上下文实现，每 feature 独立 commit（tag `feat(ops-cleanup-F00N):`）。后端簇（F001/F002/F004）与前端簇（F003/F005）文件集不重叠，可轻量并行；F006 为纯文档。
- **verifying**：6 features ≥4 → 隔离 evaluator **fan-out 分域验收**（api / web / doc 三域）。

## 功能范围（6 条）

---

### F001 — rsvg 缺失时可诊断降级（非裸 500）· medium

**现状**（`apps/api/aigc/raster.py:16-19`）：
```python
def svg_to_png(svg: str | bytes, *, width: int = 1536, timeout_s: float = 60.0) -> bytes:
    exe = shutil.which("rsvg-convert")
    if not exe:
        raise AIError("rsvg-convert 不可用 (需 librsvg2-bin)")
```
`AIError` 基类经 `main.py:106-108` 统一映射为 **HTTP 500**（`errors.py`：base→500 / ProviderError→502 / BudgetExceeded→402）。本机 dev（macOS 无 librsvg）跑轴测渲染链即撞裸 500，看起来像代码崩溃而非环境缺依赖。

**架构红线（不可违反）：** 不得引入替代渲染器兜底出图（`raster.py:5` 明示 resvg 会静默丢辉光/滤镜）。「降级」= 让错误**可诊断**，不是降质量出图。

**目标 + acceptance：**
1. 新增 `DependencyUnavailable(AIError)` 异常（`aigc/errors.py`），语义=运行时系统依赖缺失。
2. `raster.py` 缺 `rsvg-convert` 时改抛 `DependencyUnavailable`，消息含可诊断指引（缺 `librsvg2-bin`，dev 安装提示）。
3. `main.py` 注册 `DependencyUnavailable` 异常处理器 → **HTTP 503** + `{"error": "<可诊断消息>"}`（FastAPI 按 MRO 命中更具体处理器，需实测确认 503 而非落到 AIError 500）。
4. 生产行为不回归：rsvg 恒在 → 该分支不触发，正常渲染路径零变更。
5. 单测：mock `shutil.which` 返 None → 断言抛 `DependencyUnavailable` + 端点返 503（不依赖真实 rsvg，可在无 rsvg 的 CI/dev 跑）。

---

### F002 — 缩略图 kind 收入 modes.py 注册表 · low

**现状**：渲染端点缩略图 kind 为散落硬编码串——
- `main.py:1881` `kind="ai-thumb"`（轴测 AI 效果图缩略图，配 `axon-photoreal`）
- `main.py:2474` / `main.py:2771` `kind="real-thumb"`（实拍效果图缩略图，配 `real-photo`）
- `main.py:770` `kind="empty-thumb"`（**上传**空房照缩略图，非渲染 mode）

`aigc/modes.py` 的 `RENDER_MODES` 目前只登记 `artifact_kind` / `base_kind`，缩略图 kind 不在表内——新增 mode 时缩略图 kind 易漏配/写错。

**目标 + acceptance：**
1. `RENDER_MODES` 两条 mode 条目各增 `thumb_kind` 字段：`axon-photoreal.thumb_kind="ai-thumb"`、`real-photo.thumb_kind="real-thumb"`。
2. `main.py:1881/2474/2771` 三处渲染缩略图 `kind=` 改为从 `RENDER_MODES[mode]["thumb_kind"]` 取值，消除硬编码串。
3. `empty-thumb`（`main.py:770`，上传域非渲染 mode）**不纳入** `RENDER_MODES`，保持原样（可加一行注释说明其为上传缩略图、有意不入渲染注册表）。
4. 产物 kind 实际写盘值不变（`ai-thumb`/`real-thumb` 字面不变），仅来源集中化；既有 `renders.json` / artifact 读取零影响。
5. 单测：断言 `RENDER_MODES` 含 `thumb_kind` 且值符合预期。

---

### F003 — real-render 角标显中文房名（非裸 room_id）· medium

**现状**（`apps/web/src/app/studio/projects/[id]/real-render/page.tsx`）：
- `:703` `{photo.room_id || '未标注房间'}` — 角标直显 `r_live` / `r_foyer` 等裸机器 id
- `:863` `{selectedObj.room_id || '未标注'}` — 同上
- `:683` `title={photo.note || photo.room_id || '空房照片'}` — tooltip 同源

**真源已确认存在**：几何 `rooms[].label.zh` 携带中文房名（如 `{"zh":"客厅"}`、`r_guest2→"次卧(二)"`，见 `svg2geometry.py:100-103`、`test_wall_material.py:16`）。前端 `ROOM_LABEL`（`RoomsLayer.tsx`）是颜色常量，非房名映射。

**目标 + acceptance：**
1. real-render 页构建 `room_id → label.zh` 映射（来源：几何 `rooms[].label.zh`；Generator 选取加载路径——复用页面已有几何加载 / studioApi，pre-impl 确认）。
2. `:703`、`:863` 两处角标改显中文房名；回退链：`label.zh` → `room_id` → `'未标注房间'`（映射缺失时不崩、优雅回退）。
3. `:683` tooltip 同步优化（nice-to-have，同一映射复用）。
4. 未标注房间（`room_id` 空）行为不变（仍显"未标注房间" + amber 徽标）。
5. 无对应几何房间时回退到 `room_id`（不吞错、不显空白）。

**关键设计决策：** 房名解析在前端做（几何已在前端可得），不改后端 photo 数据结构。

---

### F004 — project_lock 破锁改 flock，消除 TOCTOU · medium

**现状**（`apps/api/baselines.py:169-219`）：`project_lock` 用 `O_CREAT|O_EXCL` 原子创建 `.project.lock`（锁获取本身无竞态），但**陈旧锁自愈**走非原子路径：
```python
except FileExistsError as exc:
    try:
        age = time.time() - lock_path.stat().st_mtime   # :199 读 mtime
    except OSError:
        age = 0.0
    if age > stale_s:
        try:
            lock_path.unlink()                            # :204 破锁 — 与另一 worker 重建之间存在 TOCTOU
        except FileNotFoundError:
            pass
        continue
```
`stat(mtime)` 与 `unlink()` 之间，另一 worker 可能已破锁+重建持有新锁，本 `unlink` 会误删他人**新鲜锁**。被 10+ 关键区复用（`baselines.py:504/665/685/713/731/762/803/841/954/1159`）。

**目标 + acceptance：**
1. 改用 `fcntl.flock` 咨询锁：持久 lock 文件 fd 上 `LOCK_EX|LOCK_NB` + poll 循环（保留现 `timeout_s`/`poll_s` 语义），内核在进程死亡时自动释放 → **删除整套 mtime 陈旧检测 + unlink 破锁逻辑**（`kill -9` 残留问题由内核自动释放消解）。
2. **保留公开契约不变**：`@contextmanager` 签名、`yield` 语义、超时抛 `BaselineConflict`；10+ 调用点零改动。
3. 不 `unlink` lock 文件（持久句柄，消除删除竞态）；文件残留是良性的（下次 flock 复用）。
4. 平台：`fcntl` POSIX（Linux 生产 + macOS dev 均支持）；文件顶注 POSIX-only。
5. **并发测试（Evaluator 重点）：** (a) 持锁时第二次获取在 `timeout_s` 内抛 `BaselineConflict`；(b) 释放后可再获取；(c) 模拟持锁进程终止（关 fd）→ 锁自动可用（无需 stale_s 等待）。

**关键设计决策：** flock 咨询锁的正确性建立在「同主机所有 worker 同用此路径」——匹配当前单主机部署（`--workers 1`，锁为未来多 worker 预留）。NFS/跨主机不在支持范围（数据盘为 deploysvr 本地盘）。

---

### F005 — comingSoon 死代码清理 · low

**现状**：`studioRoutes.tsx:44` 声明 `comingSoon?: boolean;`，但**全仓无任一路由对象设 `comingSoon: true`**（grep 仅命中类型声明 + `:38` 注释）。`StudioSidebar.tsx:183` 注释明示「Phase 5：comingSoon 项改为可点达」——字段与其 UI 分支（`StudioSidebar.tsx:199/218/246/267`）已成死代码。

**目标 + acceptance：**
1. 移除 `studioRoutes.tsx` 的 `comingSoon` 字段声明 + `:38` 过时注释。
2. 移除 `StudioSidebar.tsx` 中所有 `comingSoon` 相关分支（`disabled`、`即将上线` 徽标/tooltip、`:199/218/246/267`）。
3. 侧栏渲染行为不变：所有项皆可点达（本就无 `true` 项，视觉零回归）。
4. `yarn lint` + `yarn build` 绿；无 `comingSoon` 残留引用。

---

### F006 — 编辑器升级计划文档状态列回填 · low

**现状**（`docs/编辑器升级计划-20260703.md:19-28`）：状态列过时——P1/P3/P4/P5/P6 多标「待做」，但 `docs/backlog-核对-20260708.md` §A/B 已核实 P3（merge 组/canvas-S 系列）、P5（门批次/材质）、P6（底图描摹 `underlay` + 第二批 7 类家具，CATALOG=46，`test_p6_furniture`）大部已上线。

**目标 + acceptance：**
1. 逐阶段（P1–P7）核对 main 实况（交叉 `backlog-核对-20260708.md` + 代码 grep），更新状态列为准确值（✅上线 / 🟡大部 / 待做）。
2. 每处状态变更在行内或随附注明依据（commit / 文件 / backlog 条目），不空口改字。
3. 仅改状态列/依据备注，不改选型决策与阶段内容正文。
4. 纯文档，无代码/测试影响。

## 测试要求

- Python（F001/F002/F004）：本地跑两套 pytest（`PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q` 与 engine 套件）。F001 单测须在**无 rsvg** 环境可跑（mock `shutil.which`）。CI 不跑 pytest，本地为唯一门。
- Web（F003/F005）：`yarn lint` + `yarn build`（静态导出）绿；F003 手测角标显中文名。
- F006：文档，无自动化测试。
- 无 golden 字节变更 → 不触发 golden 重冻门。
