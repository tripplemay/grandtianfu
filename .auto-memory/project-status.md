---
name: project-status
description: 项目当前状态快照（覆盖写，≤30 行）— 当前批次、计划、决策、遗留问题
type: project
---
## 当前批次
- **render-fix-b1 ✅ 验收通过（fix_rounds=2，未部署）**（2026-07-15）：第7步实拍引导图退化致家具落位错
  - 用户报：户型 v7/胡桃石韵轻奢 效果图餐桌位置错。生产实物实证**两个独立 bug**：
    - F001(P0 主因)：curtain 盒越相机平面，`_box_polys` 无近平面守卫→投影炸开糊死全画幅，餐桌盒 **0% 可见**。修：相机系 Sutherland–Hodgman 近平面裁剪(NEAR_MM=10)。curtain 覆盖 92.05%→1.66%，餐桌恢复 1.46%；byte-safe 对照真 main 逐字节成立(75 件 64 等价/11 件确跨平面)
    - F002(P1)：ANNO_PALETTE 8 色静默回绕→purple 同时=餐桌+绿植。修：扩 14 色(前 8 冻结)+耗尽即 raise+legend 单射断言+跳 entry_door。生产 30/30 单射(修前 4/30 撞色)
    - F003：引导图健全性前置门禁(画幅内覆盖率>0.9 拦，7ms 不调 AI)→409+code，堵住 auto_check 0.967 静默放行的失败面
  - 三轮隔离验收：首轮 F003 PARTIAL(409 落 500 + 缺阈值边界用例) → 复验1 两条闭合但发现 R4(测试泄漏后台 job 写穿 git-tracked data/projects) → **复验2 全 PASS**（阳性对照差分实证污染已止 + 排空语义结构性证明）
  - L1：154+334 全绿、0 skip、golden 5 条实跑；产品代码 fix_round2 零改动
  - signoff：`docs/test-reports/render-fix-b1-signoff-2026-07-15.md`
  - **⏳ 待用户决定部署**（分支 `fix/render-guide-degeneracy`，未 push）→ 走 PR→squash-merge（push main = 部署生产）
  - **[L2] 未验**：真实 AI 出图（无 key+需授权计费）→ **部署后建议人工目检首张实拍图**（用户原始报障的验证闭环）
- **decor-b3-fix ✅ 已上线生产**（2026-07-14，`ac98c20`）：贴墙软装轴测校验误判修复

## 项目概况
- 阅天府 studio monorepo：`apps/api`(FastAPI/Py3.9) + `packages/floorplan_core`(纯 stdlib) + `apps/web`(Next15/Yarn1)

## 关键约束
- **push `main` = 部署生产** → branch→PR→squash，**禁止自动 push main**；/autodrive 禁开
- **⚠ deploy.yml 无 paths-ignore** → 任何 push main 都触发 build+deploy；状态/记忆文件应随批次 PR 一起走
- **ruff 格式坑**：本机 ruff 与仓库基线不一致 → 编辑 Python 手工匹配风格，只用 `ruff check` 查真错
- **测试红线**：`data/projects/` 是 git-tracked 种子快照，测试绝不可写入（monkeypatch 沙箱 + 后台 job 会写穿，见 render-fix-b1 R4）

## 待办 / 遗留
- **⚠ HIGH 待立批**：`calibrate()` 世界 z 轴符号未约束 → 3/5 生产标定 z 朝下，家具盒朝**地下**拉伸（wall_art 被画在地板上）。与用户报障同源，render-fix-b1 只修了 footprint，**垂直体积引导对 3/5 照片仍错**
- render-fix-b1 soft-watch（详见 signoff §Soft-watch）：S1 无 en 静默 continue / S2 cyan-teal ΔE=28 / S3 `_INPUT_GATE_CODES_409` 人工登记表 / S4+S5 `_wait` 靠约定非机制（建议 fixture 改 yield+teardown 排空）/ S7 box_usability 与 _box_polys 判的不是同一个盒
- backlog：BL-decor-b2-L2-realphoto(high) / BL-horizon-template-removal(medium) / BL-useviewport-hook-deps(low) / BL-tv-mirror-wall-clearance(low) + docs/backlog-核对-20260708(30 项)
- proposed-learnings：v1.0.4 已沉淀 8 条；机件改动 3 条裁决为待办（留 harness 机件重构轮）；render-fix-b1 新提案见 signoff §Framework Learnings（阳性对照要求 / 排空 vs 掩盖判据 / 会后 stderr warning 陷阱 / monkeypatch+后台 job 写穿沙箱）
