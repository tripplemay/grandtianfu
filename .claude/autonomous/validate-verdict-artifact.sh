#!/usr/bin/env bash
# autonomous-mode.md 机件 #3：验收工件内容校验（fail-closed）。
# 两用：(a) /autodrive 步骤 6 的 verdict 工件断言（内容校验，非仅存在）；
#        (b) PostToolUse Write|Edit 到 docs/test-reports/*-verdict.json 的兜底 hook。
# 核心：存在≠真实——每 feature 的 evidence / steps_to_reproduce 必须非空，机械拒收空壳。
# fail：退出 2；对 /autodrive 意味着「重跑该 verify 步上限 1 次，仍不过 → evaluator_cannot_verify 硬停」。

set -euo pipefail
ARTIFACT="${1:?用法: validate-verdict-artifact.sh <docs/test-reports/BL-XXX-verdict.json>}"

if [ ! -f "$ARTIFACT" ]; then
  echo "[autodrive] ⛔ verdict 工件缺失：$ARTIFACT → 沉淀无来源，验收不成立。"
  exit 2
fi

python3 - "$ARTIFACT" <<'PY'
import json, sys
path = sys.argv[1]
try:
    v = json.load(open(path))
except Exception as e:
    print(f"[autodrive] ⛔ verdict 工件 JSON 非法（{e}）。"); sys.exit(2)

errs = []
for k in ("batch_id", "fix_round", "created_at", "verdicts"):
    if k not in v:
        errs.append(f"缺顶层字段 {k}")

verdicts = v.get("verdicts")
if not isinstance(verdicts, list) or len(verdicts) == 0:
    errs.append("verdicts 必须为非空数组")
else:
    for i, item in enumerate(verdicts):
        tag = item.get("feature_id", f"#{i}")
        if item.get("result") not in ("PASS", "PARTIAL", "FAIL"):
            errs.append(f"[{tag}] result 非法：{item.get('result')}")
        # 机件 #3 核心：证据非空，拒收空壳
        for field in ("evidence", "steps_to_reproduce"):
            val = item.get(field)
            if not isinstance(val, str) or not val.strip():
                errs.append(f"[{tag}] {field} 为空 → 空壳验收，拒收")

if errs:
    print(f"[autodrive] ⛔ verdict 工件校验失败（{path}）：")
    for e in errs:
        print("   -", e)
    sys.exit(2)
print(f"[autodrive] ✓ verdict 工件合法（batch={v.get('batch_id')}, fix_round={v.get('fix_round')}, {len(verdicts)} 条，证据齐全）。")
PY
