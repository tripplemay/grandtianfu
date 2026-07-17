---
name: project-status
description: 项目当前状态快照（覆盖写，≤30 行）— 当前批次、计划、决策、遗留问题
type: project
---
## 当前批次
- **calib-cure-b1 ✅ done+已上线生产（2026-07-17，PR#87 squash `b8344f1`，用户指示合并部署；F004/F005 门禁生产实测生效——798 病例出图 409/2353.4px）**：标定根治 A 预览/B 硬门禁/C 特征点对齐 + L1 简模引导 spike
  - 12/12 PASS（11 generator 经 fan-out 隔离验收 + F012 spike 重跑）；CI 双绿；signoff `docs/test-reports/calib-cure-b1-verifying-2026-07-17.md`
  - 源起：生产两张带评论效果图落位全错 → 根因=标定输入易错+零门禁（三份核查文档已入库）
  - 关键落地：assess 单一真源硬门(保存400/渲染409/dry-run)、≥3锚点+语义校验、标定即预览两步提交、特征点 PnP 模式(往返<2px)、DELETE 标定、guide 聚合出画拦截、spike 工具
  - **spike 结论 GO(带条件)**：弱后端 fal 上 L0 复现"书柜窄条"生产失败模式、L1 修复为满墙(直接实证)；relay 上 L0 已达标(L1=跨后端保险)；灰体穿帮 0/4；auto_check 实证形体盲不能作形体裁决器；条件=①S1 量化 relay 边际收益 ②配 VLM/人工形体评分 ③扩样本+好标定客餐厅 ④curtain 简模改半透明
- **用户待办**：L2 走查（生产已可做：标定预览+重标两张病例照片，重标后即可重新出图验证落位）

## 关键约束
- **push `main` = 部署生产** → branch→PR→squash；⚠ deploy.yml 无 paths-ignore
- **测试红线**：data/projects/ 种子快照——回退路径测试必须 `_drain_render_job` 排空 job（calib-cure-b1 实证写穿竞态并根治）
- **两个 z 世界**：perspective=真实毫米(2700) vs axon=压扁(1450)；**合成相机 fixture 必须物理一致构造**（镜像相机=case-A 活标本，calib-cure-b1 已订正）
- **ruff**：本机 `python3 -m ruff`；main.py/baselines.py 各 1 条既有 I001 基线噪声
- **并行 worktree agent**：派发 prompt 必含 `git reset --hard origin/<批次分支>` 前置（4/4 初始基不对实证）

## 待办 / 遗留
- 下一批次候选：3D 化 S1 原型验证（spike GO 条件展开）/ backlog 余 6 条
- framework proposed-learnings 6 条新候选待用户确认（calib-cure-b1 沉淀）
