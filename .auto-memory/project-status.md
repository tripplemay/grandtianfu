---
name: project-status
description: 项目当前状态快照（覆盖写，≤30 行）— 当前批次、计划、决策、遗留问题
type: project
---
## 当前批次
- **calib-cure-b1 verifying（2026-07-17，分支 feat/calib-cure-b1 未合并）**：标定根治 A 预览/B 硬门禁/C 特征点对齐 + L1 简模引导 spike
  - 源起：生产两张带评论效果图（798 书房"书柜位置错"/f4d 客餐厅"沙发酒柜位置错"）根因=标定输入易错+零门禁；三份核查文档随批入库（根因链/19 项缺陷+数值实验/3D 化评估）
  - building 11/11：dry-run 预览+两步提交(F001/F002)、assess 单一真源硬门+InputGateError(F003)、语义校验+≥3锚点(F004)、渲染 409 硬拦(F005)、guide 聚合出画+矛盾话术禁止(F006)、DELETE 标定(F007)、特征点池+PnP+points 端点(F008)、特征点 UI(F009)、动态文案+direction 门(F010)、spike 工具(F011)
  - F012 spike A/B（executor:evaluator）在 verifying 执行；用户已授权 relay+fal ~¥20-30
  - 测试 425+154 全绿；tsc/lint/prettier 绿；每 feature 独立 commit
- **裁决记录**：backlog 收编 3 条（min-3-anchors/input-gate-error-class/decor-b2-L2）；存量坏标定渲染硬拦；离房检查降软信号(1500mm)；direction 门只拦 >135° 反向

## 关键约束
- **push `main` = 部署生产** → branch→PR→squash；⚠ deploy.yml 无 paths-ignore
- **测试红线**：data/projects/ 种子快照——回退路径测试必须 _drain_render_job 排空 job（本批实证竞态并根治）
- **两个 z 世界**：perspective=真实毫米(2700) vs axon=压扁(1450)，数字不得互借
- **ruff**：本机 `python3 -m ruff`；main.py/baselines.py 各 1 条既有 I001 基线噪声

## 待办 / 遗留
- verifying：隔离 evaluator 验收 + F012 spike → 报告 docs/test-reports/
- 用户项：L2 浏览器走查（标定预览+重标两张病例照片）；PR squash-merge（=部署）
- backlog 余 6 条（horizon-template/useviewport/tv-mirror/wall-art-orient/fixture-harden/wall-art-box）
