# ops-cleanup-b1 · verifying 域报告（api 域 / F001·F002·F004）

- **批次**：ops-cleanup-b1
- **阶段**：verifying（首轮，fix_rounds=0）
- **验收域**：api（`F001` rsvg 可诊断降级 503 / `F002` 缩略图 kind 入注册表 / `F004` project_lock 改 flock 消 TOCTOU）
- **验收人**：local/evaluator-subagent（隔离上下文，fresh context；不继承实现叙述）
- **日期**：2026-07-13
- **取证基底**：commits `782c826`(F001) / `60ff27a`(F002) / `4fb13ff`(F004)；api diff `git diff 97c33a4..HEAD -- apps/api packages/floorplan_core`
- **环境**：macOS/darwin，Python 3.9.6，pytest 8.4.2；`rsvg-convert` **实际存在**（`/opt/homebrew/bin/rsvg-convert`），`os.fork` 可用
- **L2**：本批 api 域**无 L2**（无生产/staging/计费/DNS 写入；AI provider 在测试中被 mock，无真实调用）。全部 L1 本地。

---

## 1. 结论

**F001 = PASS · F002 = PASS · F004 = PASS。**

三条 feature 的 acceptance 逐项在代码层与测试运行输出双重满足。api 全套 pytest **301 passed**，engine 套件 **131 passed**，F001/F002/F004 定向 15 case 全绿；ruff `--select F`(pyflakes) 对全部改动文件 0 错。除既有测试外，另做 3 组独立对抗探针（异常码 MRO 映射 / flock inode 保持 / 跨 OFD 竞争），结论一致。架构红线（不引入替代渲染器出图）未被触碰。

---

## 2. F001 — rsvg 缺失可诊断降级（DependencyUnavailable→503，非裸 500）

### Acceptance 逐条核对

| # | acceptance 项 | 判定 | 证据 |
|---|---|---|---|
| 1 | 新增 `DependencyUnavailable(AIError)` | **PASS** | `aigc/errors.py:23-30`；含 docstring 说明 503 语义（区别于 AIError 500 / ProviderError 502） |
| 2 | `raster.py` 缺 rsvg 时抛之 + 可诊断消息 | **PASS** | `aigc/raster.py:17-24`：`shutil.which("rsvg-convert")` 为空即 `raise DependencyUnavailable(...)`，消息含 `rsvg-convert` / `librsvg2-bin` / apt + brew 安装指引 + "核心几何与编辑不受影响"。`svg_to_png_canvas`(`raster.py:81`) 委托 `svg_to_png`，AI/实拍路径同样受益 |
| 3 | `main.py` 注册处理器 → 503（实测非落 AIError 500） | **PASS** | 应用级 `@app.exception_handler(DependencyUnavailable)`(`main.py:106-109`)→503；渲染端点宽 `except Exception` 另加 `_dependency_error_response`(`main.py:180-188`) 助手在三处（`_render_house_response` `main.py:1198`、`_render_ai_response` `main.py:1850`、`_render_real_response` `main.py:2744`）显式返 503——否则宽 except 会吞成 500。**对抗探针实测**：DependencyUnavailable→503 且 AIError→500 无回归（见 §5.1） |
| 4 | 生产零回归（rsvg 恒在，分支不触发） | **PASS** | 缺失分支仅在 `which()` 为空时进入；本机 rsvg 存在下 `test_svg_to_png_returns_png_bytes` / `test_svg_to_png_accepts_bytes` 正常出 PNG，正常渲染路径无改动 |
| 5 | 单测 mock `shutil.which`→None 断言 503（无 rsvg 环境可跑） | **PASS** | `test_raster.py::test_svg_to_png_raises_dependency_unavailable_when_rsvg_missing`（mock which=None→断言 DependencyUnavailable + 消息含关键词）；`test_render_dependency.py::test_render_png_returns_503_when_rsvg_missing`（端点级 503）。mock 使测试**与真实 rsvg 存在与否无关**——本机 rsvg 存在，这两测仍 PASS，证明可在无 rsvg 环境跑 |
| — | 架构红线：不得引入替代渲染器兜底出图 | **PASS** | `raster.py` 仅抛异常，无 resvg/任何替代栅格器兜底；"降级" = 错误可诊断，非降质出图 |

**补充观察（非阻塞）**：`suggest_view` 端点（`main.py:1455` 调 `svg_to_png`）的宽 except 将异常吞成 `{"suggested": None, "reason": "prep_failed: ..."}`（200，AI 尽力而为建议路径）。此为既有优雅降级、非本批引入，且不在 F001 acceptance（渲染端点）范围——不构成裸 500，不降级。记为 O-1。

**F001 判定：PASS。**

---

## 3. F002 — 缩略图 kind 收入 modes.py RENDER_MODES 注册表

### Acceptance 逐条核对

| # | acceptance 项 | 判定 | 证据 |
|---|---|---|---|
| 1 | 两 mode 各增 `thumb_kind`（axon-photoreal→ai-thumb / real-photo→real-thumb） | **PASS** | `aigc/modes.py:13-14`：`AXON_PHOTOREAL.thumb_kind="ai-thumb"`、`REAL_PHOTO.thumb_kind="real-thumb"` |
| 2 | 三处渲染缩略图 kind 改从注册表取值，消除硬编码 | **PASS** | `main.py:1904` `kind=RENDER_MODES[AXON_PHOTOREAL]["thumb_kind"]`；`main.py:2497`、`main.py:2797` `kind=RENDER_MODES[REAL_PHOTO]["thumb_kind"]`（原 1881/2474/2771，因 F001 增行位移）。**全仓 grep**：`"ai-thumb"`/`"real-thumb"` 字面仅存于 `modes.py` 注册表，渲染路径 0 残留硬编码 |
| 3 | `empty-thumb`(上传域) 不入表，保持原样 | **PASS** | `main.py:787` `kind="empty-thumb"` 字面不变；`RENDER_MODES` 中无 empty-thumb 条目（上传域非渲染 mode） |
| 4 | 写盘 kind 字面不变（ai-thumb/real-thumb），读取零影响 | **PASS** | 注册表值与历史字面完全一致，`renders.json`/artifact 读侧不涉改；`test_modes.py::test_render_modes_thumb_kind_values` 断言精确字面 |
| 5 | 断言测试 | **PASS** | `test_modes.py`（新增）：`test_render_modes_have_all_kind_fields`（三类 kind 齐备）+ `test_render_modes_thumb_kind_values`（值精确） |

**F002 判定：PASS。**

---

## 4. F004 — project_lock 改 fcntl.flock，消除破锁 TOCTOU

### Acceptance 逐条核对

| # | acceptance 项 | 判定 | 证据 |
|---|---|---|---|
| 1 | 改用 `fcntl.flock`（LOCK_EX\|NB + poll 保 timeout 语义），删除 mtime 陈旧检测 + unlink 破锁 | **PASS** | `baselines.py:191-200`：持久 fd 上 `fcntl.flock(fd, LOCK_EX\|LOCK_NB)` + poll 循环，超时抛 BaselineConflict。旧 `stat(mtime)+unlink` 破锁块整段删除；**全仓 grep `stale_s` = 0 命中**（参数与逻辑均已消除） |
| 2 | 保留公开契约：`@contextmanager` 签名 / yield / 超时抛 BaselineConflict；10+ 调用点零改动 | **PASS** | `baselines.py:170` `@contextmanager` 仍在，签名仅去 `stale_s`(spec 要求)，`Iterator[Path]` 返回、`yield lock_path`(`:208`)、超时 `raise BaselineConflict`(`:199`) 均保留。10 处调用（`:498/659/679/707/725/756/797/835/948/1153`）全未改；**grep 确认无一调用传 `stale_s`**——去参安全 |
| 3 | 不 unlink lock 文件（持久句柄，消删除竞态） | **PASS** | finally 仅 `flock(LOCK_UN)+os.close`(`:209-213`)，无 unlink。**独立探针**：锁文件 inode 跨 acquire/release 保持不变（60292817→60292817），证明未 unlink+recreate（见 §5.2） |
| 4 | POSIX-only 注释 | **PASS** | `baselines.py:185` docstring 明注 "POSIX-only (Linux 生产 + macOS dev)" + flock OFD 语义说明 |
| 5a | 持锁时第二次获取在 timeout_s 内抛 BaselineConflict | **PASS** | `test_baselines_migration.py::test_project_lock_rejects_concurrent_acquire`（timeout_s=0 立抛）；fork 测试父进程 timeout_s=0 亦抛 |
| 5b | 释放后可再获取 | **PASS** | 同上测试后半段 `with project_lock(...timeout_s=1)` 成功；`test_project_lock_released_when_holder_dies` 亦覆盖 |
| 5c | 模拟持锁进程终止→锁自动可用（无需 stale 等待） | **PASS** | `test_project_lock_released_when_holder_dies`（`os.fork` 子进程持锁→管道同步→父进程 SIGKILL 子进程→内核释放 flock→父进程立即获取）。fork 可用，**该测未 skip**、实跑 PASS。较 acceptance "关 fd" 更贴 F004 立项动机（"kill -9 残留"），为超集验证 |
| — | 崩溃残留锁文件不阻塞 | **PASS** | `test_project_lock_leftover_file_does_not_block`（预置陈旧 pid 的残留文件，无进程持 flock→不阻塞获取，无需 stale 等待） |

**F004 判定：PASS。**

---

## 5. 独立对抗探针（超出既有测试的 fresh-context 验证）

### 5.1 异常码 MRO 映射（F001 核心疑点：非落 AIError 500）
向 `main.app` 临时挂 4 条抛异常的探针路由，TestClient 实测：

```
/__probe_dep     -> 503 (expect 503) OK   # DependencyUnavailable
/__probe_aierr   -> 500 (expect 500) OK   # AIError（基类，无回归）
/__probe_prov    -> 502 (expect 502) OK   # ProviderError
/__probe_budget  -> 402 (expect 402) OK   # BudgetExceeded
MRO: ['DependencyUnavailable', 'AIError', 'Exception']  issubclass(.., AIError)=True
```

结论：`DependencyUnavailable` 虽为 `AIError` 子类，Starlette 按 MRO 命中更具体 handler→503，且**不破坏基类 AIError→500 及兄弟 402/502 映射**。团队关注的 "503 非 500" 得双向确证。

### 5.2 flock 真锁性 + inode 保持（F004 核心疑点：TOCTOU 消除）
```
acquire#1 held, inode = 60292817
  OK: 持锁期间另开独立 fd 的 flock 阻塞（真 advisory lock，跨 OFD 竞争，非内存标志）
after release, lock file exists: True   # 不 unlink
acquire#2 held, inode = 60292817
INODE PRESERVED across acquire/release: True -> TOCTOU unlink race eliminated
```

结论：锁文件不被删除+重建（inode 恒定）→ 旧 "stat/unlink 之间误删他人新鲜锁" 的删除竞态从根上消除；跨 OFD 竞争证明是真咨询锁。

---

## 6. 测试输出摘要

| 套件 / 命令 | 结果 |
|---|---|
| `PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q` | **301 passed** in 15.58s |
| `PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q` | **131 passed** in 0.47s |
| 定向：test_raster / test_render_dependency / test_modes / test_baselines_migration | **15 passed**（含 fork+SIGKILL 自动释放测，未 skip） |
| `ruff check --select F`（pyflakes）改动 9 文件 | **All checks passed**（exit 0） |

**lint 说明**：本机 ruff 0.15.20 + `ruff.toml` 缺 `known-first-party` → `I001`(import 分组) 对全仓所有文件皆报，属已知假阳性（session_notes + 团队指令确认），不据此判 FAIL；`--select F` 真错为 0。

---

## 7. 观察项（非阻塞，不降级）

- **O-1**：`suggest_view`(`main.py:1455`) 缺 rsvg 时吞成 `{"suggested": None}`（200），既有优雅降级、非 F001 引入、非裸 500，不在 acceptance 范围。记录备查，不处理。
- **O-2**：F004 finally 中 `flock(LOCK_UN)` 后 `os.close` 释放，其中 close 本身即触发内核释放，显式 UN 冗余但无害且更明确——非缺陷。
- **O-3**：F004 写 pid 元数据块 `except OSError: pass`（`:206-207`）：pid 记录仅供 ops 排查、不参与锁语义，其失败不影响锁正确性（flock 已先成功）——设计正确。

以上均不影响 PASS 判定，无需 Generator 处理。

---

## 8. 判定汇总

| feature | 域 | 结果 |
|---|---|---|
| F001 rsvg 缺失可诊断降级（503） | api | **PASS** |
| F002 缩略图 kind 入 RENDER_MODES 注册表 | api | **PASS** |
| F004 project_lock 改 flock 消 TOCTOU | api | **PASS** |

api 域首轮 verifying：**3 PASS / 0 PARTIAL / 0 FAIL**。

> 注：本报告仅覆盖 api 域（F001/F002/F004）。web 域（F003/F005）与 doc 域（F006）由并行 evaluator 分域出具；批次总签收由编排者机械合并三域结论后决定。本 evaluator 不写 progress.json / features.json / signoff。
