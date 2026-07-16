# 跨层语义一致性检查（框架沉淀）

> 触发：给某类型/实体新增"豁免归一化 / 自愈 / 放宽某约束"的语义时，或反向新增一条硬约束时。
> 主要读者：Generator（实装前 grep）/ Planner（spec 起草）。

## 核心规律：豁免/约束必须在所有 enforcement 点成对实现

当你给某类型加"豁免某几何/结构约束"的语义时（例："贴墙件豁免内缩离墙"），**必须同步在该约束的所有 enforcement 点加对应豁免**。否则一侧放行、另一侧硬拦，产生"上游看起来对、下游却被拦"的分裂——且分裂常被某一层的显示过滤恰好隐藏，用户无从察觉。

### 反面案例（decor-b3-fix, 2026-07-14）

阅天府 `floorplan_core`：decor-b1 给贴墙软装（挂画/窗帘，`NOSHADOW_TYPES`）在 `build_scene` 的 **归一化层**（D13）加了"豁免 inner-clearance 内缩"（它们本该贴墙），但 **校验层** `_validate_items` 的 AXON 路径漏加同一豁免：

- 归一化层放行 → 贴墙件保持贴墙（正确）
- 校验层没豁免 → 这些"正确贴墙"的件被判 `AXON_OUTSIDE_ROOM_BBOX` / `AXON_WALL_THICKNESS_COLLISION` = **ERROR** → `validation.ok=False` → 三处 AI 出图入口全阻断
- 前端编辑器恰好 `filter(!code.startsWith('AXON_'))` → 用户在编辑器只看到 WARN，**看不到**这些 ERROR

结果：用户手工检查无错，出图却被拦，现象与根因隔了一层，排查成本高。

### 实装 / spec 前的 checklist

新增"某类型应违反 / 豁免某约束"时：

1. `grep` 该约束的**所有 enforcement 点**——不止一处。典型三类：
   - **归一化 / 自愈层**（把越界件夹回合法区，如 `_adjust_rect_to_inner_clearance` / `_adjust_rect_away_from_wall_bboxes`）
   - **校验 / 门禁层**（判 ERROR/WARN、决定 `validation.ok` 是否阻断，如 `_validate_items`）
   - **lint / 质量层**（软提示，如 `lint.py`）
2. 确认豁免/约束在**每一层**同步生效，且用**同一个判据来源**（如 `NOSHADOW_TYPES` 单一真源），避免各层各写一份类型集导致漂移。
3. 补对照测试：既测豁免类型降级/放行，又用**非豁免类型**同几何反证约束仍生效（防止把整道门关掉）。

### 次生坑：可自愈件端到端做不出干净反例

归一化层会把"可归一化"的件自愈夹回合法区，因此走完整管线（如 `build_scene`）时，可归一化的非豁免件不会触发校验 ERROR——自愈掩盖了校验门。**类型限定的反证（"非豁免件仍 ERROR"）只能在校验层直接注入构造几何来做**，端到端管线做不出。（decor-b3-fix Evaluator 实测：超大 sofa 走 `build_scene` 被 D13 自愈缩放回房内，反而 `ok=True`。）

来源：decor-b3-fix（贴墙软装轴测校验误判阻断出图 —— D13 归一化豁免未在校验门同步）。

---

## 自查条：新增 raise / 信号时，所有消费点是被机制保证认识它，还是被纪律？（v1.0.6 — render-fix-b1 沉淀）

**本条的分量在于它的来源：修跨层一致性 bug 的那个批次，自己引入了同类缺口。** 这个模式**极易复发**，包括在读过本文件的人手里。

render-fix-b1 的病灶正是本文件的核心规律 ——「守卫在一处存在、兄弟点不知情」（`box_usability` 检测到退化，而 `annotate_boxes` 照画）。而它的 **fix_round1 又引入了同构缺口**：新增 `DEGENERATE_GUIDE` raise 时在 raise 点带了 `code`，但 `except` 段**不认识**它 → 结构化载荷被字符串化 → 落 500 而非预期的 409。

**实装 / 验收自查：** 新增一个 raise / 错误码 / 信号时，逐一列出它的**消费点**（except 段、错误码登记表、前端解析、日志分类），并问：**它们认识这个新信号，是靠机制（类型系统 / 构造函数 / 单一真源）保证的，还是靠「我记得去登记」？** 后者 = 下一个人必忘。

---

## 「集合式修法」是把知情自律往后挪一格，不等于机制化关死（v1.0.6 — render-fix-b1 沉淀）

**背景：** 上一条的修法是把散落的 `if` 收敛成单一命名锚点 `_INPUT_GATE_CODES_409`。这是**客观改进**（真源唯一、可 grep、可穷举核对），但它**仍是一张人工登记表** —— 新增门禁 raise 时忘了登记，照样静默落 500。**坑只是往后挪了一格。**

**两档判据（验收时必须显式区分）：**

| 档位 | 特征 | 例 |
|---|---|---|
| **更整洁的自律** | 不变量集中、可核对，但**违反它在语法上是合法的** | `_INPUT_GATE_CODES_409` 集合；「每条测试自觉写 `_wait`」 |
| **机制化关死** | 违反不变量**在语法上不可能** | `class InputGateError(ValueError)` 携带 `status`/`payload` → `except InputGateError as e: return JSONResponse(e.status, e.payload)`，code 与状态码**同生**，无处可忘 |

**处理规则：** Evaluator **不得把「更整洁的自律」记为「已机制化」**。两者都可接受，但结论必须写对档位 —— 记错档 = 后人以为这道门已经关死，不再设防。呼应 `harness-rules.md` §机制化守门 的「诚实边界」注（机制化比宣传的薄）。

**落项：** `BL-input-gate-error-class`（medium）—— 用 `InputGateError` 让 code 与 HTTP 状态码同生，替代人工登记表。

**来源：** render-fix-b1 三轮验收（Evaluator 判为改进项而非缺陷、不阻断该批，但要求档位写实）。
