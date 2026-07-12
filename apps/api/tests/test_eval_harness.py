# -*- coding: utf-8 -*-
"""image2 回归评测集纯函数 (P2): 指标提取 / 尺寸判定 / 聚合 / markdown。"""
from aigc.eval_harness import (
    EVAL_CASES,
    HUMAN_SCORE_KEYS,
    UNACCEPTABLE_KEYS,
    has_unacceptable,
    metrics_row,
    parse_size,
    size_verdict,
    summarize,
    to_markdown,
)


def test_eval_cases_cover_report_min_set():
    """诊断报告最小集: 整宅轴测 2 + 客餐厅实拍 4 + 主卧实拍 2 + 墙材 2 = 10。"""
    assert len(EVAL_CASES) == 10
    axon = [c for c in EVAL_CASES if c.kind == "axon"]
    real_live = [c for c in EVAL_CASES if c.kind == "real" and c.room == "r_live"]
    assert len(axon) == 2
    assert len(real_live) >= 4  # 四个拍摄方向 + 墙材上下文复用
    # id 唯一。
    assert len({c.id for c in EVAL_CASES}) == len(EVAL_CASES)


def test_parse_size():
    assert parse_size("1536x1024") == (1536, 1024)
    assert parse_size("bad") is None
    assert parse_size(None) is None


def test_size_verdict_match_mismatch_unknown():
    assert size_verdict({"requested_size": "1536x1024", "actual_size": "1536x1024"}) == "match"
    # 报告实测: 请求 1536x1024 -> 返回 1677x938。
    assert size_verdict({"requested_size": "1536x1024", "actual_size": "1677x938"}) == "mismatch"
    # 老 record 只有 size, 无 actual_size -> 无法判。
    assert size_verdict({"size": "1536x1024"}) == "unknown"


def test_metrics_row_from_record():
    record = {
        "mode": "real-photo",
        "size": "1536x1024",
        "requested_size": "1536x1024",
        "actual_size": "1677x938",
        "prompt": "一段实拍提示词",
        "usage": {"total_tokens": 3473},
        "style_snapshot": "现代轻奢",
    }
    row = metrics_row("real_live_v0", record)
    assert row["case_id"] == "real_live_v0"
    assert row["provider_ok"] is True
    assert row["mode"] == "real-photo"
    assert row["size_verdict"] == "mismatch"
    assert row["prompt_len"] == len("一段实拍提示词")
    assert row["total_tokens"] == 3473
    assert row["style_snapshot"] == "现代轻奢"
    # 人工评分槽默认空, 不可接受错误默认 False。
    for k in HUMAN_SCORE_KEYS:
        assert row[k] is None
    for k in UNACCEPTABLE_KEYS:
        assert row[k] is False


def test_metrics_row_none_record_is_failure():
    row = metrics_row("real_bed_v0", None)
    assert row["provider_ok"] is False
    assert row["size_verdict"] == "unknown"
    assert row["prompt_len"] is None


def test_has_unacceptable():
    row = metrics_row("x", {"size": "1x1", "actual_size": "1x1"})
    assert has_unacceptable(row) is False
    row["moved_walls"] = True
    assert has_unacceptable(row) is True


def test_summarize_counts():
    rows = [
        metrics_row("a", {"requested_size": "1536x1024", "actual_size": "1536x1024",
                          "usage": {"total_tokens": 100}, "prompt": "p"}),
        metrics_row("b", {"requested_size": "1536x1024", "actual_size": "1677x938",
                          "usage": {"total_tokens": 200}, "prompt": "pp"}),
        metrics_row("c", None),
    ]
    rows[1]["wrong_room"] = True  # 判废
    s = summarize(rows)
    assert s["total"] == 3
    assert s["provider_ok"] == 2
    assert s["provider_failed"] == 1
    assert s["size_mismatch"] == 1
    assert s["rejected"] == 1
    assert s["avg_total_tokens"] == 150


def test_to_markdown_renders_table_and_summary():
    rows = [metrics_row("a", {"requested_size": "1536x1024", "actual_size": "1677x938",
                              "usage": {"total_tokens": 100}, "prompt": "p", "mode": "real-photo"})]
    md = to_markdown(rows)
    assert "| 用例 |" in md
    assert "real-photo" in md
    assert "合计 1" in md
    assert "尺寸错配 1" in md


def test_classify_failures_maps_known_reasons():
    """P2-2: auto_check 失败词 -> 失败类型标签 (启发式 + 语义)。"""
    from aigc.eval_harness import classify_failures

    assert classify_failures(["media 盒区未见家具 (盒内改动 7)"]) == ["漏画"]
    assert classify_failures(["盒区外结构/材质被改：地面变木地板"]) == ["材质漂移"]
    assert classify_failures(["酒柜 盒区画的是「书架」不是预期家具"]) == ["盒内类别错"]
    assert classify_failures([]) == []
    assert classify_failures(["某种全新失败措辞"]) == ["其他"]  # 未知失败词不静默漏统计


def test_metrics_row_extracts_auto_check():
    """P2-2: metrics_row 从 record.auto_check 提取 ok/score/失败类型 (自动, 非人工)。"""
    from aigc.eval_harness import metrics_row

    rec = {
        "mode": "real-photo",
        "method": "geometry-lock",
        "edit_backend": "relay",
        "auto_check": {"ok": False, "score": 0.6, "fail_reasons": ["sofa 盒区未见家具 (盒内改动 3)"]},
    }
    row = metrics_row("c1", rec)
    assert row["auto_check_ok"] is False
    assert row["auto_check_score"] == 0.6
    assert row["failure_types"] == ["漏画"]
    assert row["method"] == "geometry-lock" and row["edit_backend"] == "relay"


def test_summarize_auto_acceptance_and_failure_tally():
    """P2-2: summarize 自动出验收通过率 + 失败类型分布 (代理人工可接受率)。"""
    from aigc.eval_harness import metrics_row, summarize

    rows = [
        metrics_row("a", {"auto_check": {"ok": True, "score": 1.0, "fail_reasons": []}}),
        metrics_row("b", {"auto_check": {"ok": False, "score": 0.5, "fail_reasons": ["x 盒区未见家具"]}}),
        metrics_row("c", {"auto_check": {"ok": False, "score": 0.4, "fail_reasons": ["盒区外结构/材质被改"]}}),
        metrics_row("d", None),  # 出图失败, 无 auto_check -> 不计入判定
    ]
    s = summarize(rows)
    assert s["auto_check_judged"] == 3
    assert s["auto_check_pass"] == 1
    assert s["auto_check_pass_rate"] == round(1 / 3, 3)
    assert s["failure_type_counts"] == {"漏画": 1, "材质漂移": 1}
