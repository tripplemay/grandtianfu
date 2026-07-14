# decor-b2 验收报告 — Web 域（F005）

- **批次**：decor-b2　**阶段**：verifying（首轮）
- **域**：Web（方案页配饰呈现 + brief 配饰偏好字段，含前端 + 后端持久化端到端）
- **Evaluator**：local/evaluator-subagent（fresh context，隔离验收）
- **日期**：2026-07-13
- **分支**：feat/decor-b2 @ 06ec7bb
- **结论**：**F005 PASS**

---

## 1. 验收范围

| Feature | 标题 | executor | verdict |
|---|---|---|---|
| F005 | 方案页配饰呈现 + brief 配饰偏好字段 | generator | **PASS** |

> F001–F004/F006（floorplan_core / AIGC / 评测集域）与 F007（AI+第7步实拍对抗）不在本域，由其它域 Evaluator 负责。

---

## 2. 实测证据

### 2.1 前端三门（Node 22 / v22.22.0，PATH 显式前置 nvm v22 规避 Homebrew node v25）

| 门 | 命令 | 结果 |
|---|---|---|
| tsc | `npx tsc --noEmit` | **PASS**（exit 0，无输出） |
| lint | `yarn lint` | **PASS**（仅 7 条 `useViewport.ts` react-hooks/exhaustive-deps 历史 warning，非本批次文件，按约定不计；F005 触碰文件零告警） |
| build | `yarn build` | **PASS**（Done in 17.09s；`/studio/projects/[id]/scheme` 路由正常产出 12.4 kB） |

> 环境记账：本机 `which node` = `/opt/homebrew/bin/node`（v25.7.0）抢占 PATH，`nvm use 22` 在非交互 shell 未生效。已用 `export PATH="$HOME/.nvm/versions/node/v22.22.0/bin:$PATH"` 强制 Node 22（CI 版本）后重跑 lint/tsc/build，三门均在 Node 22 下绿。tsc 在 Node 25 下亦绿（互证）。

### 2.2 后端持久化 + 编译测试

```
PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest \
  apps/api/tests/test_schemes_api.py \
  packages/floorplan_core/tests/test_brief_prompt.py -q
→ 21 passed in 0.44s
```

关键用例 `test_patch_scheme_brief_persists_decor_preferences`（test_schemes_api.py:208）：
PATCH `{"brief":{"decor_preferences":["少量挂画","绿植点缀","  "]}}` → 返回体 `brief == {"decor_preferences":["少量挂画","绿植点缀"]}`（去空白），且**独立 GET 复读**同值 → **证明落盘往返，不被 `_normalize_brief` 白名单静默丢弃**（原缺口已修复）。

---

## 3. 对抗核查

### 3.1 配饰摘要计数（countSchemeDecor）— PASS

`apps/web/src/lib/floorplan/decorAttach.ts:73-86`：

```
countSchemeDecor(furniture) =
  Σ [ (it.t ∈ {wall_art,curtain,plant} ? 1 : 0)   // 独立件计数
    + (Array.isArray(it.decor) ? it.decor.length : 0) ]  // 附着件子列表长度之和
```

- ✅ = 独立件(wall_art/curtain/plant)计数 + 所有件 decor 子列表长度之和，与 acceptance 语义一致。
- ✅ `STANDALONE_DECOR_TYPES = ['wall_art','curtain','plant']`（decorAttach.ts:69）**与后端 `layout.place_decor_standalone` 支持的落位类型逐字一致**（layout.py:515-523 分支恰为 wall_art/curtain/plant）。
- ✅ 无重复计数风险：独立件（wall_art/curtain/plant）均非 DECOR_ATTACH 宿主，不会自带 decor 子列表；附着件只存于宿主 `decor`，两集不相交。
- ✅ badge **>0 才显示**：`page.tsx:914` `(decorCounts[scheme.id] ?? 0) > 0 &&`。
- ✅ **复用公共 Badge 组件**（`page.tsx:915` `<Badge tone="gray" icon={<MdLocalFlorist/>}>配饰 N 项</Badge>`），未手写卡片/徽章。
- 计数来源：方案 summary 只带家具总数，故 effect 逐方案 `fetchFurniture` 计数，`Promise.all` 并行，per-scheme 失败降级为 0，effect 依赖 `[id, decorFetchKey]`（keyed on `id:updated_at`）避免无关 silent reload 抖动——设计合理且有注释。

### 3.2 brief decor_preferences 端到端（关键）— PASS

三处白名单**逐字一致**核对：

| 处 | 位置 | key |
|---|---|---|
| 前端 SchemeBriefEditor LIST_FIELDS | SchemeBriefEditor.tsx:47-51 | `decor_preferences` |
| 前端类型接口 SchemeBrief | studioApi.ts:576 | `decor_preferences?: string[]` |
| 后端持久化白名单 | schemes.py:49 `_BRIEF_LIST_KEYS` | `decor_preferences` |
| 编译白名单 | brief_prompt.py:38 `_LIST_FIELDS` | `("decor_preferences","soft furnishing preferences")` |

- ✅ PATCH 落盘：`schemes._normalize_brief` 遍历 `_BRIEF_LIST_KEYS`（含 decor_preferences），去空白后写盘；持久化往返测试硬证（§2.2）。
- ✅ 编译进 prompt：`compile_brief` 输出 `soft furnishing preferences: 少量挂画, 绿植点缀`（test_brief_prompt.py:65-68），且**缺省时不出现**（byte-safe，`test_decor_preferences_field` 断言 `"soft furnishing" not in compile_brief({"occupants":...})`，保护历史 brief 基线）。
- ✅ 前端保存链路：SchemeBriefEditor.save → `patchScheme(projectId, schemeId, { brief: next })`（studioApi.patchScheme 签名含 `brief?: SchemeBrief | null`），LIST_FIELDS 统一渲染，decor_preferences 与其余 6 个列表字段同路处理。

### 3.3 深色主题 — PASS

- ✅ badge：`tone="gray"` → `status.tsx:209` `gray: 'bg-gray-100 text-gray-500 dark:bg-navy-700 dark:text-gray-300'`，成对 dark:。
- ✅ brief 新字段：复用既有 LIST_FIELDS input 样式（`dark:border-white/10 dark:bg-navy-900 dark:text-white`，label `dark:text-gray-400`），无新硬编码浅底。
- ✅ F005 触碰的三个文件内**无未配对硬编码 bg-*-50**；scheme/page.tsx 中已有的 bg-*-50（base 选择器/下拉菜单，行 701/1012/1173/1186/1199/1208）均有成对 `dark:` 且非 F005 新增代码。

---

## 4. 观察项（非阻塞，不影响 PASS）

1. **N+1 furniture 拉取**：方案列表渲染时逐方案 `fetchFurniture` 计配饰数（Promise.all 并行 + updated_at keyed + per-scheme 错误降级）。MVP_D_ONLY 下 D 户型方案数少，可接受；若未来单户型方案数显著增长可能拖慢首屏。设计有注释权衡，建议后续如需可下沉到 summary 后端聚合（记 backlog，不阻塞本批）。
2. **前端逻辑无单测**：`countSchemeDecor` / `briefFilledCount` 为纯函数但 web 无 jest/vitest（仅 Playwright e2e），F005 acceptance 仅要求 lint/tsc/build 绿，符合。后端侧（持久化 + 编译）已有 pytest 覆盖。可选后续为纯函数补单测。

---

## 5. 铁律与边界

- ✅ Evaluator 未修改任何产品代码：`git status --short` 空（工作树干净），仅新增本报告。
- ✅ 结论基于实物：代码逐行核对 + 三门实跑输出 + pytest 实跑输出 + 持久化往返断言；未采信实现叙述。
- L2（真实外部服务/生产写入）：本域不涉及。

---

## 6. 判定

**F005 = PASS。** 方案卡配饰摘要 badge（独立件+附着件计数、>0 才显示、复用公共 Badge、深色主题成对）、brief 配饰偏好字段（三处白名单逐字一致、PATCH 落盘往返、编译进 prompt 且 byte-safe）、前端三门（tsc/lint/build，Node 22）与后端持久化测试（21 passed）全部达标。原 subagent 报告的持久化死字段缺口（schemes._BRIEF_LIST_KEYS 缺 decor_preferences）已修复并有回归断言守护。**无 issue。**
