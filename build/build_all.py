#!/usr/bin/env python
"""Run Tasks 1-6 as one reproducible full build."""

from __future__ import annotations

import build_html
import extract
import parse_toc


def main() -> None:
    print("=== Task 1：解析目录 ===")
    parse_toc.main()
    print("\n=== Task 2：提取正文与图片 ===")
    extract.main()
    print("\n=== Task 3-6：生成站点并执行完整性检查 ===")
    build_html.main()
    print("\n完整构建：通过")


if __name__ == "__main__":
    main()
