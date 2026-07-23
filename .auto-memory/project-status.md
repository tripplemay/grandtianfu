---
name: project-status
description: 项目当前状态快照（覆盖写，≤30 行）— 当前批次、计划、决策、遗留问题
type: project
---
## 当前批次
- **calib-cure-b2（解算根治）收口 done（2026-07-19，未推 main，分支 feat/calib-cure-b2）**：通用 PnP + 异面特征点 + 精修 + 退化守门 + 稳健 reproj + 前端多高度点选 + 专家降级
  - F001-F007 隔离 evaluator **L1 全 PASS**（合成往返<2px、σ=8px 稳、门未放宽；signoff `docs/test-reports/calib-cure-b2-verifying-2026-07-18.md`）——代码正确有价值，应保留
  - **F008 L2 关键发现（诚实）**：solver 修复**必要但不充分**。真实病例 r_guest2（书房 472015c4）正确对应下仍退化（dry-run 实证：北墙 4 角→相机高 64mm/hfov160°/reproj952px）；根因=**正对一面墙拍→可见特征全共面→几何退化**，非 solver/门/点选问题
  - **⚠ 用户最初报障（大量图片标不成功）对"正对墙拍"类照片仍未解**——病灶转移到**拍摄几何/构图**
- **calib-cure-b3（下一批，规划中）**：拍摄/构图引导 + 退化早拦（标定前提示重拍角落机位）+ 窗几何失配（落地窗 vs 齐腰窗）；含"per-photo 手工标定 vs 3D 引导路线（b1 spike）"权衡

## 关键约束
- **push `main` = 部署生产** → branch→PR→squash；⚠ deploy.yml 无 paths-ignore
- **两个 z 世界**：perspective=真实毫米(2700) vs axon=压扁(1450)；异面点层高用 `_REAL_CEILING_MM=2700`
- **标定几何铁律**：正对墙拍→特征共面→PnP 退化（相机高/hfov 崩）；须角落机位（两面墙+地面纵深）才有非共面特征
- **ruff**：本机 `python3 -m ruff`；main.py 1 条既有 I001 基线噪声；.venv 缺 numpy→用系统 python3 跑
- **本地 L2**：DATA_DIR/UPLOADS_DIR 指沙箱 + 假 OPENAI 凭据解锁页面；PIPL 照片只读拉沙箱、用完即删、绝不入 git

## 待办 / 遗留
- b2 未推 main：解算改进是真收益、可独立合并；用户决定何时 PR/部署
- backlog：BL-calib-exif-focal-prior(low, EXIF 上传被剥不可行) + 余 6 条；framework proposed-learnings 6 条待确认
