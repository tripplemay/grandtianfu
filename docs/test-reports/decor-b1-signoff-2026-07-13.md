# decor-b1 批次签收报告（verifying → done）

- **批次**：decor-b1（软装配饰 · 引擎 + 编辑器基座）
- **spec**：docs/specs/decor-b1-spec.md
- **阶段**：verifying 首轮全 PASS → done（fix_rounds=0）
- **验收形态**：快车道三域 fan-out，各域独立 fresh-context evaluator subagent（无自评铁则）
- **日期**：2026-07-13
- **分支**：feat/decor-b1（未 push main；push main = 部署生产，合并时机由用户定）

## 聚合结论：9 PASS / 0 PARTIAL / 0 FAIL

本报告为编排者对三域独立 evaluator 结论的**聚合索引**，不改写、不软化任一域判定（harness 铁律 12）。各域 verdict 原文见对应域报告。

| Feature | 域 | Verdict | 域报告 |
|---|---|---|---|
| F001 目录新增 wall_art/curtain + noshadow 目录化 | 引擎/API | PASS | engine-api |
| F002 3D/2D 渲染 + scene 贴墙豁免 | 引擎/API | PASS | engine-api |
| F003 附着配饰机制 + furnish 换件透传 | 引擎/API | PASS | engine-api |
| F004 prompt_gen 配饰贯通 | 引擎/API | PASS | engine-api |
| F005 API 出参 + decor 结构校验 | 引擎/API | PASS | engine-api |
| F006 前端独立配饰摆放 + 换件透传 | Web | PASS | web |
| F007 前端附着配饰编辑（SidePanel 配饰分节） | Web | PASS | web |
| F008 第7步隔离兜底（D10） | 引擎/API | PASS | engine-api |
| F009 轴测渲染正确性对抗验收 | 渲染对抗 | PASS | render |

## 域报告

- 引擎/API 域（F001-F005, F008）：`decor-b1-verifying-engine-api-2026-07-13.md` — 6 PASS/0 FAIL；引擎 pytest 145 + api pytest 309 全绿(0 skip)、golden 字节快照真跑真绿、mount_z↔模型顶面对齐核验、第7步全链路配饰隔离核验
- Web 域（F006/F007）：`decor-b1-verifying-web-2026-07-13.md` — 2 PASS；tsc/lint/build 三门绿、前后端 DECOR_ATTACH hosts 逐类一致 5/5
- 渲染对抗（F009）：`decor-b1-verifying-render-2026-07-13.md` — PASS；含全部配饰的轴测 SVG 逐图元几何目检、换件透传实测、golden 零回归；样本 `decor-b1-render-sample-2026-07-13.svg`

## Soft-watch（非 FAIL，明文兜底）

1. **S1**（render）wall_art/curtain 默认 footprint 面向水平墙，竖直墙需转置 w/h——与既有 mirror 行为一致，非新缺陷 → 归 BL-decor-b2（b2 auto-place 随墙轴转置）
2. **S2**（render）窗帘 vplane 与外墙块 painter 深度键近似的理论 z-fighting 余地——本样例无遮挡；观察项，b2 可给贴墙件深度键微偏置
3. **web-observations** web 无纯函数单测（acceptance 只要求三门+冒烟）→ 建议 b2 补；手动编辑器冒烟建议签收前人工做一次
4. **F009-L2** 第5步真实出图因 AI 未配置降级为 SVG 几何目检并记账（[L2] 环境限制/未授权，不算 FAIL）；配饰进渲染管线可见已在 SVG 层获硬证

## 交付边界（预期，非缺陷）

- b1 配饰**不进第7步实拍**（D10 只隔离兜底，未接入 prompt/allowed）→ 实拍图里配饰不会主动出现。属 spec §7 明文 b1/b2 边界。
- decor-b2（AI 自动配饰 + 第7步完整接入 + 方案页配饰 UI + 回归评测集）已入 backlog.json（BL-decor-b2，high）。
