---
name: project-status
description: 项目当前状态快照（覆盖写，≤30 行）— 当前批次、计划、决策、遗留问题
type: project
---
## 当前批次
- **calib-z-b1 🔨 planning 完成 → building（未开工）**（2026-07-15）：标定世界 z 轴符号未约束
  - 根因：`calibrate()` 的 z 列 = `cross(sx·ex, sy·ey)` 是 x/y 符号副产品；两条打分约束只用**地面**锚点（生产 5/5 锚点 z 全为 0）→ z 列恒乘 0、对打分零贡献 → **z 方向从未被物理约束钉过**
  - 生产实测 **3/5 反转**（相机中心 z = −2427 / −1382 / −156，物理不可能）→ 家具盒朝地下拉伸、贴墙件画在地板 → 模型无视错盒把画挂墙 → `auto_check` 持续误报「盒区外出现新结构」
  - 判别式：`C = -Rᵀt` 的 `C[2] > 0`（相机在地板上方）—— 生产 5/5 完美分离，无需调参
  - 3 features：F001 根治 / F002 存量 3 份自愈重跑（免用户重标）/ F003 evaluator 对抗验收
  - **⚠ F001 开工前须先提交 pre-impl 审计等 Planner 裁决**（spec §5）—— z 符号判错会让 2/5 正确的反而变错
  - spec 自包含（`docs/specs/calib-z-b1-spec.md`），**新会话直接读它接手**
- **render-fix-b1 ✅ 已上线生产**（2026-07-15，`d9c2b35`）：第7步引导图退化致家具落位错
  - 用户报：户型 v7/胡桃石韵轻奢 效果图餐桌位置错。生产实物实证**两个独立 bug**：
    - F001(P0 主因)：curtain 盒越相机平面，`_box_polys` 无近平面守卫→投影炸开糊死全画幅，餐桌盒 **0% 可见**。修：相机系 Sutherland–Hodgman 近平面裁剪(NEAR_MM=10)。curtain 覆盖 92.05%→1.66%，餐桌恢复 1.46%；byte-safe 对照真 main 逐字节成立(75 件 64 等价/11 件确跨平面)
    - F002(P1)：ANNO_PALETTE 8 色静默回绕→purple 同时=餐桌+绿植。修：扩 14 色(前 8 冻结)+耗尽即 raise+legend 单射断言+跳 entry_door。生产 30/30 单射(修前 4/30 撞色)
    - F003：引导图健全性前置门禁(画幅内覆盖率>0.9 拦，7ms 不调 AI)→409+code，堵住 auto_check 0.967 静默放行的失败面
  - 三轮隔离验收：首轮 F003 PARTIAL(409 落 500 + 缺阈值边界用例) → 复验1 两条闭合但发现 R4(测试泄漏后台 job 写穿 git-tracked data/projects) → **复验2 全 PASS**（阳性对照差分实证污染已止 + 排空语义结构性证明）
  - L1：154+334 全绿、0 skip、golden 5 条实跑；产品代码 fix_round2 零改动
  - signoff：`docs/test-reports/render-fix-b1-signoff-2026-07-15.md`
  - 已 squash-merge main + CI 部署成功（run 29398965562）；分支已清理
  - **[L2] 未验**：真实 AI 出图（无 key+需授权计费）→ **⏳ 待用户重新生成一张 v7 实拍图目检**（原始报障的验证闭环）
- **decor-b3-fix ✅ 已上线生产**（2026-07-14，`ac98c20`）：贴墙软装轴测校验误判修复

## 项目概况
- 阅天府 studio monorepo：`apps/api`(FastAPI/Py3.9) + `packages/floorplan_core`(纯 stdlib) + `apps/web`(Next15/Yarn1)

## 关键约束
- **push `main` = 部署生产** → branch→PR→squash，**禁止自动 push main**；/autodrive 禁开
- **⚠ deploy.yml 无 paths-ignore** → 任何 push main 都触发 build+deploy；状态/记忆文件应随批次 PR 一起走
- **ruff 格式坑**：本机 ruff 与仓库基线不一致 → 编辑 Python 手工匹配风格，只用 `ruff check` 查真错
- **测试红线**：`data/projects/` 是 git-tracked 种子快照，测试绝不可写入（monkeypatch 沙箱 + 后台 job 会写穿，见 render-fix-b1 R4）

## 待办 / 遗留
- （z 轴问题已立批 calib-z-b1，见上）**生产实证闭环**：render-fix-b1 上线后 2026-07-15 08:12/08:14 两张新图**餐桌位置已正确且可复现**；但 auto_check 仍 ok:false 0.85「盒区外出现新结构」= z 轴 bug 下游症状
- render-fix-b1 soft-watch（详见 signoff §Soft-watch）：S1 无 en 静默 continue / S2 cyan-teal ΔE=28 / S3 `_INPUT_GATE_CODES_409` 人工登记表 / S4+S5 `_wait` 靠约定非机制（建议 fixture 改 yield+teardown 排空）/ S7 box_usability 与 _box_polys 判的不是同一个盒
- backlog：BL-decor-b2-L2-realphoto(high) / BL-horizon-template-removal(medium) / BL-useviewport-hook-deps(low) / BL-tv-mirror-wall-clearance(low) + docs/backlog-核对-20260708(30 项)
- proposed-learnings：v1.0.4 已沉淀 8 条；机件改动 3 条待办；**render-fix-b1 新提案 6 条已入队待确认**（阳性对照要求/排空vs掩盖判据/会后 stderr warning 陷阱/monkeypatch+后台job写穿沙箱/跨层模式易复发自查/集合式修法≠机制化）（阳性对照要求 / 排空 vs 掩盖判据 / 会后 stderr warning 陷阱 / monkeypatch+后台 job 写穿沙箱）
