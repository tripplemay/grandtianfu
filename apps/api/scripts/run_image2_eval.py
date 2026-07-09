#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""image2 回归评测运行器 (诊断报告 P2): 对着一个已跑起来的服务, 按固定评测集逐一出图,
把每张 render record 归一化为指标行, 落 summary.json + report.md 供横向比较。

这是**手动工具**, 需要真实 provider 与已配好的服务 (会真实消耗额度), 因此不进 CI、不在
测试里跑; 纯指标逻辑在 aigc/eval_harness.py 里单测。

用法:
    # 1) 起服务 (已配 OPENAI_API_KEY/OPENAI_BASE_URL), 上传并标注好评测用空房照。
    # 2) 写一个 config.json 把评测集用例映射到该环境的具体 scheme_id/photo_id:
    #    {
    #      "axon_default":  {"scheme_id": "default"},
    #      "axon_ai_style": {"scheme_id": "scheme_ai_..."},
    #      "real_live_v0":  {"scheme_id": "scheme_ai_...", "photo_id": "..."},
    #      ...
    #    }
    # 3) 运行:
    EVAL_API_BASE=http://127.0.0.1:8000 \
      python3 scripts/run_image2_eval.py --project D --config config.json --out artifacts/image2-eval-手动跑

config 里只需填你要跑的用例; 未填的用例记为 skipped, 不出图。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

from aigc.eval_harness import EVAL_CASES, metrics_row, summarize, to_markdown  # noqa: E402


def _poll_job(client: httpx.Client, base: str, job_id: str, timeout_s: float) -> dict | None:
    """轮询异步出图 job 到 done/error; 返回 record (done) 或 None (error/超时)。"""
    end = time.time() + timeout_s
    while time.time() < end:
        resp = client.get(f"{base}/api/ai/jobs/{job_id}")
        resp.raise_for_status()
        job = resp.json()
        if job.get("status") == "done":
            return job.get("result")
        if job.get("status") == "error":
            print(f"    job {job_id} 失败: {job.get('error')}")
            return None
        time.sleep(2.0)
    print(f"    job {job_id} 超时")
    return None


def _run_case(client: httpx.Client, base: str, project: str, case, cfg: dict, timeout_s: float):
    """跑一个用例 -> render record 或 None (失败/跳过)。"""
    scheme_id = cfg.get("scheme_id")
    if not scheme_id:
        print(f"  [skip] {case.id}: config 未提供 scheme_id")
        return None
    if case.kind == "axon":
        url = f"{base}/api/projects/{project}/schemes/{scheme_id}/render-ai"
        resp = client.post(url, json={})
    else:  # real
        photo_id = cfg.get("photo_id")
        if not photo_id:
            print(f"  [skip] {case.id}: config 未提供 photo_id")
            return None
        url = f"{base}/api/projects/{project}/schemes/{scheme_id}/render-real"
        resp = client.post(url, json={"photo_id": photo_id})
    if resp.status_code != 200:
        print(f"  [fail] {case.id}: HTTP {resp.status_code} {resp.text[:200]}")
        return None
    job_id = resp.json().get("job_id")
    print(f"  [run ] {case.id}: job {job_id}")
    return _poll_job(client, base, job_id, timeout_s)


def main() -> int:
    ap = argparse.ArgumentParser(description="image2 回归评测运行器 (P2)")
    ap.add_argument("--project", default="D")
    ap.add_argument("--config", required=True, help="用例 -> {scheme_id, photo_id} 映射 JSON")
    ap.add_argument("--out", required=True, help="输出目录 (写 summary.json / report.md)")
    ap.add_argument("--timeout", type=float, default=360.0, help="单张出图轮询超时秒")
    args = ap.parse_args()

    base = os.environ.get("EVAL_API_BASE", "http://127.0.0.1:8000").rstrip("/")
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    with httpx.Client(timeout=args.timeout + 30) as client:
        for case in EVAL_CASES:
            cfg = config.get(case.id) or {}
            record = _run_case(client, base, args.project, case, cfg, args.timeout)
            rows.append(metrics_row(case.id, record))

    summary = summarize(rows)
    (out_dir / "summary.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "report.md").write_text(to_markdown(rows, summary), encoding="utf-8")
    print(f"\n评测完成 -> {out_dir}/report.md")
    print(
        f"合计 {summary['total']} · 成功 {summary['provider_ok']} · "
        f"尺寸错配 {summary['size_mismatch']} · 判废 {summary['rejected']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
