#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D-1 一次性迁移 (软装重构 Phase D): 把所有方案 meta.json 里遗留的 status=confirmed 归一化为
draft (砍掉 scheme 级 confirm 后, confirmed 不再是合法状态)。幂等、只改 status 字段。

用法 (在 VPS 上, DATA_DIR 指向 /opt/grandtianfu 的数据卷):
    DATA_DIR=/data python3 scripts/migrate_scheme_status.py
读路径的 normalize 也会自愈遗留 confirmed, 本脚本是显式清盘 + 审计。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schemes  # noqa: E402


def main() -> int:
    data_dir = os.environ.get("DATA_DIR", "data/projects")
    result = schemes.migrate_scheme_status(data_dir)
    print(f"[migrate_scheme_status] DATA_DIR={data_dir}")
    print(f"  confirmed -> draft: {result['count']} 个方案")
    for sid in result["changed"]:
        print(f"    - {sid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
