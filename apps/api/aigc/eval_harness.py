# -*- coding: utf-8 -*-
"""image2 回归评测集 (诊断报告 P2): 固定一组最小输入, 每次改 prompt/链路后横向比较。

这里只放**纯函数 + 声明式规格**, 不做任何网络调用 —— 可单测。真正驱动 provider 出图的
编排在 scripts/run_image2_eval.py (对着一个已跑起来的服务发 HTTP), 把每张 render record
喂给 metrics_row() 汇总成一行, 再 to_markdown/summarize 落报告。

自动可测的指标 (来自 record, 无需人判): provider 是否成功、请求 vs 实际尺寸是否一致、
prompt 长度、token usage、mode、风格快照。需要人判的指标 (落位/结构/风格符合度/不可接受
错误) 以空槽形式留在行里, 由评审人回填, 保证同一批输入可复现比较。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalCase:
    """一个评测输入的声明 (不含真实字节, 只描述'跑哪张')。

    kind: "axon" = 第5步整宅/单房轴测效果图; "real" = 第7步空房照实拍效果图。
    scheme: 用哪个方案 (default = 初始方案; ai = 该批新生成的 AI 方案占位, 运行时替换)。
    photo_direction: real 用, 拍摄视角 v0..v3; axon 忽略。
    """

    id: str
    kind: str
    scheme: str
    room: str | None = None
    photo_direction: str | None = None
    note: str = ""


# 固定最小评测集 (诊断报告"建立 image2 回归评测集"): 整宅轴测 2 (默认/AI 风格) +
# 客餐厅实拍 4 (四个拍摄方向) + 主卧实拍 2 + 墙面材质上下文 2。运行器按此清单逐一出图。
EVAL_CASES: tuple[EvalCase, ...] = (
    EvalCase("axon_default", "axon", "default", note="整宅轴测 · 默认方案"),
    EvalCase("axon_ai_style", "axon", "ai", note="整宅轴测 · AI 风格方案"),
    EvalCase("real_live_v0", "real", "ai", room="r_live", photo_direction="v0",
             note="客餐厅实拍 · 视角 v0"),
    EvalCase("real_live_v1", "real", "ai", room="r_live", photo_direction="v1",
             note="客餐厅实拍 · 视角 v1"),
    EvalCase("real_live_v2", "real", "ai", room="r_live", photo_direction="v2",
             note="客餐厅实拍 · 视角 v2"),
    EvalCase("real_live_v3", "real", "ai", room="r_live", photo_direction="v3",
             note="客餐厅实拍 · 视角 v3"),
    EvalCase("real_bed_v0", "real", "ai", room="r_bed", photo_direction="v0",
             note="主卧实拍 · 视角 v0"),
    EvalCase("real_bed_v1", "real", "ai", room="r_bed", photo_direction="v1",
             note="主卧实拍 · 视角 v1"),
    EvalCase("wall_ctx_a", "real", "ai", room="r_live", photo_direction="v0",
             note="墙面材质参考组 A (方案墙面贴实拍参考图后复跑)"),
    EvalCase("wall_ctx_b", "real", "ai", room="r_bed", photo_direction="v0",
             note="墙面材质参考组 B"),
)

# 需要人工回填的评分槽 (自动指标之外)。0-5 分, None = 未评。
HUMAN_SCORE_KEYS = ("placement_score", "structure_score", "style_score")

# P2-2: auto_check.fail_reasons (批1/4/5 落 record 的启发式+语义验收失败词) -> 失败类型分类,
# 使"失败类型统计"自动化 (不再纯人工)。子串匹配 acceptance/semantic_accept 的中文失败词。
_FAILURE_CATEGORIES = (
    ("漏画", "未见家具"),
    ("彩盒残留", "未被替换"),
    ("重取景", "重新取景"),
    ("结构改动", "新结构"),
    ("材质漂移", "材质被改"),
    ("盒内类别错", "不是预期家具"),
)


def classify_failures(fail_reasons: object) -> list[str]:
    """把一组 auto_check 失败词映射为失败类型标签 (去重, 稳定序); 未匹配的归 '其他'。"""
    if not isinstance(fail_reasons, list) or not fail_reasons:
        return []
    joined = " ".join(str(r) for r in fail_reasons)
    out: list[str] = []
    for label, needle in _FAILURE_CATEGORIES:
        if needle in joined and label not in out:
            out.append(label)
    matched_any = bool(out)
    # 有失败词但没匹配到已知类别 -> 记 '其他' (防新失败类型被静默漏统计)。
    if fail_reasons and not matched_any:
        out.append("其他")
    return out
# 不可接受错误清单 (任一命中即该张判废): 改墙/改窗/错房间/家具漂浮/出现人物或文字/水印。
UNACCEPTABLE_KEYS = (
    "moved_walls",
    "changed_windows",
    "wrong_room",
    "floating_furniture",
    "people_or_text",
    "watermark",
)


def parse_size(size: str | None) -> tuple[int, int] | None:
    """'1536x1024' -> (1536, 1024); 非法/缺失 -> None。"""
    if not isinstance(size, str) or "x" not in size:
        return None
    a, _, b = size.partition("x")
    try:
        return int(a), int(b)
    except ValueError:
        return None


def size_verdict(record: dict) -> str:
    """请求档 vs provider 实际返回尺寸: 'match' / 'mismatch' / 'unknown'。

    优先用 record 的 requested_size/actual_size (批3 新增); 老 record 只有 size 时无法判 -> unknown。
    """
    requested = parse_size(record.get("requested_size") or record.get("size"))
    actual = parse_size(record.get("actual_size"))
    if requested is None or actual is None:
        return "unknown"
    return "match" if requested == actual else "mismatch"


def _usage_total(usage: object) -> int | None:
    if not isinstance(usage, dict):
        return None
    val = usage.get("total_tokens")
    return int(val) if isinstance(val, (int, float)) else None


def metrics_row(case_id: str, record: dict | None) -> dict:
    """把一张 render record 归一化为一行评测指标 (自动部分); 人工评分槽留空。

    record=None 表示该 case 出图失败/未产出 -> provider_ok=False, 其余自动指标为 None。
    """
    if not record:
        auto = {
            "provider_ok": False,
            "mode": None,
            "method": None,
            "edit_backend": None,
            "requested_size": None,
            "actual_size": None,
            "size_verdict": "unknown",
            "prompt_len": None,
            "total_tokens": None,
            "style_snapshot": None,
            "auto_check_ok": None,
            "auto_check_score": None,
            "failure_types": [],
        }
    else:
        prompt = record.get("prompt")
        # auto_check (批1 落 record; 批5 语义并入): 自动质量判定 + 失败类型 (P2-2 自动化)。
        auto_check = record.get("auto_check") if isinstance(record.get("auto_check"), dict) else {}
        auto = {
            "provider_ok": True,
            "mode": record.get("mode"),
            "method": record.get("method"),
            "edit_backend": record.get("edit_backend"),
            "requested_size": record.get("requested_size") or record.get("size"),
            "actual_size": record.get("actual_size"),
            "size_verdict": size_verdict(record),
            "prompt_len": len(prompt) if isinstance(prompt, str) else None,
            "total_tokens": _usage_total(record.get("usage")),
            "style_snapshot": record.get("style_snapshot"),
            "auto_check_ok": auto_check.get("ok"),
            "auto_check_score": auto_check.get("score"),
            "failure_types": classify_failures(auto_check.get("fail_reasons")),
        }
    row = {"case_id": case_id, **auto}
    # 人工评分槽 (评审回填); 不可接受错误默认 False。
    for k in HUMAN_SCORE_KEYS:
        row[k] = None
    for k in UNACCEPTABLE_KEYS:
        row[k] = False
    return row


def has_unacceptable(row: dict) -> bool:
    """任一不可接受错误命中 -> 该张判废。"""
    return any(bool(row.get(k)) for k in UNACCEPTABLE_KEYS)


def summarize(rows: list[dict]) -> dict:
    """一批评测行的聚合: 成功数 / 尺寸错配数 / 判废数 / 平均 token / 自动验收通过率 / 失败类型分布。"""
    total = len(rows)
    ok = sum(1 for r in rows if r.get("provider_ok"))
    mismatch = sum(1 for r in rows if r.get("size_verdict") == "mismatch")
    rejected = sum(1 for r in rows if has_unacceptable(r))
    tokens = [r["total_tokens"] for r in rows if isinstance(r.get("total_tokens"), int)]
    avg_tokens = round(sum(tokens) / len(tokens)) if tokens else None
    # P2-2 自动指标: 自动验收 (auto_check) 通过率 —— 有 auto_check 判定的记录中 ok 的占比,
    # 作为"人工可接受率"的自动代理 (人工评分仍可回填); 失败类型分布从 fail_reasons 自动统计。
    judged = [r for r in rows if r.get("auto_check_ok") is not None]
    auto_ok = sum(1 for r in judged if r.get("auto_check_ok"))
    failure_tally: dict[str, int] = {}
    for r in rows:
        for ft in r.get("failure_types") or []:
            failure_tally[ft] = failure_tally.get(ft, 0) + 1
    return {
        "total": total,
        "provider_ok": ok,
        "provider_failed": total - ok,
        "size_mismatch": mismatch,
        "rejected": rejected,
        "avg_total_tokens": avg_tokens,
        "auto_check_judged": len(judged),
        "auto_check_pass": auto_ok,
        "auto_check_pass_rate": round(auto_ok / len(judged), 3) if judged else None,
        "failure_type_counts": failure_tally,
    }


_MD_COLUMNS = (
    ("case_id", "用例"),
    ("provider_ok", "出图"),
    ("mode", "模式"),
    ("requested_size", "请求尺寸"),
    ("actual_size", "实际尺寸"),
    ("size_verdict", "尺寸"),
    ("prompt_len", "prompt 字数"),
    ("total_tokens", "tokens"),
)


def _cell(value: object) -> str:
    if value is True:
        return "✅"
    if value is False:
        return "❌"
    if value is None:
        return "—"
    return str(value)


def to_markdown(rows: list[dict], summary: dict | None = None) -> str:
    """评测行 -> markdown 表 (自动指标)。summary 缺省时现算。"""
    summary = summary or summarize(rows)
    head = "| " + " | ".join(label for _k, label in _MD_COLUMNS) + " |"
    sep = "| " + " | ".join("---" for _ in _MD_COLUMNS) + " |"
    body = [
        "| " + " | ".join(_cell(r.get(key)) for key, _label in _MD_COLUMNS) + " |"
        for r in rows
    ]
    summary_line = (
        f"\n合计 {summary['total']} · 出图成功 {summary['provider_ok']} · "
        f"尺寸错配 {summary['size_mismatch']} · 判废 {summary['rejected']} · "
        f"平均 tokens {_cell(summary['avg_total_tokens'])}"
    )
    return "\n".join([head, sep, *body]) + "\n" + summary_line
