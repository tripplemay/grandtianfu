# Workflow Bridge — harness 与 Claude Workflow 引擎的定位与映射

> v1.0 沉淀（单工具契合度评估）。当编码阶段用 Claude dynamic Workflow 编排时，本文件说明
> harness 相对引擎的定位、角色 ⇄ Workflow stage 映射，以及哪些规则由引擎结构性强制、
> 哪些仍是散文护栏。触发：把阶段内部编排交给 Workflow 时读。

## 定位：引擎之上的薄契约纪律 + 持久骨架层

Claude Workflow 引擎提供编排的**形状**（fan-out / pipeline / loop / parallel / 判据）。harness 不复刻这层，而是坐在其上提供引擎**给不了**的四样：

| harness 承载 | 引擎是否有 | 说明 |
|---|---|---|
| **常设默认强制** | ✗ | 引擎每次要显式写编排；harness 把"无自评 / 隔离验收 / 阶段闸门"设成常设默认 |
| **约束载荷** | ✗ | Evaluator 受限工具集、只认实物、误报预检、测试设计权——引擎的 `agent()` 不带这些约束 |
| **用户闸门** | 部分 | 引擎 loop-until-done 会自主推进；harness 在 →verifying / →done 强制停下等用户 |
| **抗压缩骨架** | ✗ | progress.json / features.json 持久状态文件，压缩 / 崩溃后无损续接 |

**一句话：** 引擎拥有"阶段内部怎么跑"，harness 拥有"跨阶段的真相、流转闸门、约束纪律、持久骨架"。

## 角色 ⇄ Workflow stage 映射

| harness 角色 | Workflow 承载形态 | 引擎结构性强制 / 散文护栏 |
|---|---|---|
| Planner | 主上下文（一般不进 Workflow） | 散文护栏（spec 源码核查、裁决、误报预检） |
| Generator | 主上下文；并行 building = `parallel` + worktree 隔离 | 引擎强制并发隔离；spec-lock 仍散文护栏 |
| Evaluator | fan-out 验收 = `pipeline` / `parallel` + 隔离 subagent | 引擎强制 fresh context + 受限工具集（`agentType`）；结论原样落盘仍散文护栏（铁律 12） |

## 哪些仍是散文护栏（引擎不结构性强制）

诚实清单——这些当前**只活在文件里**，靠模型自觉而非工具链强制：无自评的"结论不洗白"、done 门的"signoff 非空"、裁决的"不循环论证"、spec 的"源码核查"、commit tag ⇄ features.json 映射。机制化硬阻断当前只覆盖 progress.json / features.json 的 **JSON 语法**（`validate-state-json.sh`），不覆盖上述语义门（见 `harness-rules.md §机制化守门` 诚实边界）。

## 阶段内部交给 Workflow 的契约

见 `orchestration-patterns.md §8`：引擎只跑阶段内部、**绝不 flip status 跨阶段**；每步结果落持久文件；崩溃逐条对账；验收工件必须持久化回喂沉淀（否则 `proposed-learnings.md` 因无 emitter 而静默饿死）。

来源：2026-07-12 单工具 + dynamic Workflow 契合度评估（三视角 + 红队对抗复核）。
