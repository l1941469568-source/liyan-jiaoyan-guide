#!/usr/bin/env python
"""Parse the printed table of contents into build/sections.json."""

from __future__ import annotations

import json
import re
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "build" / "manual.pdf"
OUTPUT_PATH = ROOT / "build" / "sections.json"

CHINESE_NUMBER = r"[一二三四五六七八九十]+"
DOT_LEADER = r"(?:[.．·…]\s*){3,}"
CHAPTER_RE = re.compile(
    rf"^\s*({CHINESE_NUMBER})\s*、\s*(.+?)\s*{DOT_LEADER}\s*(\d+)\s*$"
)
SECTION_RE = re.compile(
    rf"^\s*（\s*({CHINESE_NUMBER})\s*）\s*(.+?)\s*{DOT_LEADER}\s*(\d+)\s*$"
)
SUBSECTION_RE = re.compile(
    rf"^\s*(\d+)\s*[.．]\s*(.+?)\s*{DOT_LEADER}\s*(\d+)\s*$"
)

CHINESE_TO_INT = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def chinese_number_to_int(value: str) -> int:
    """Convert the small Chinese numerals used by this manual to an integer."""
    if value in CHINESE_TO_INT:
        return CHINESE_TO_INT[value]
    if value.startswith("十"):
        return 10 + CHINESE_TO_INT.get(value[1:], 0)
    if value.endswith("十"):
        return CHINESE_TO_INT[value[0]] * 10
    tens, ones = value.split("十", maxsplit=1)
    return CHINESE_TO_INT[tens] * 10 + CHINESE_TO_INT.get(ones, 0)


def normalize_line(line: str) -> str:
    return line.replace("\u3000", " ").replace("\xa0", " ").strip()


def parse_toc() -> dict:
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"找不到输入 PDF：{PDF_PATH}")

    chapters: list[dict] = []
    current_chapter: dict | None = None
    current_section: dict | None = None

    with fitz.open(PDF_PATH) as doc:
        if doc.page_count != 192:
            raise AssertionError(f"PDF 页数应为 192，实际为 {doc.page_count}")

        lines: list[str] = []
        for page_index in range(1, 7):
            lines.extend(
                normalize_line(line)
                for line in doc[page_index].get_text("text").splitlines()
                if normalize_line(line)
            )

    for line in lines:
        chapter_match = CHAPTER_RE.match(line)
        if chapter_match:
            number_text, title, start_page = chapter_match.groups()
            number = chinese_number_to_int(number_text)
            current_chapter = {
                "number": number,
                "label": f"{number_text}、{title.strip()}",
                "title": title.strip(),
                "start_page": int(start_page),
                "sections": [],
            }
            chapters.append(current_chapter)
            current_section = None
            continue

        section_match = SECTION_RE.match(line)
        if section_match:
            if current_chapter is None:
                raise ValueError(f"节出现在章之前：{line}")
            number_text, title, start_page = section_match.groups()
            section_number = chinese_number_to_int(number_text)
            current_section = {
                "id": f"{current_chapter['number']:02d}-{section_number:02d}",
                "chapter_number": current_chapter["number"],
                "section_number": section_number,
                "chapter": current_chapter["label"],
                "title": title.strip(),
                "start_page": int(start_page),
                "end_page": None,
                "subsections": [],
            }
            current_chapter["sections"].append(current_section)
            continue

        subsection_match = SUBSECTION_RE.match(line)
        if subsection_match:
            if current_section is None:
                raise ValueError(f"小节出现在节之前：{line}")
            number_text, title, start_page = subsection_match.groups()
            current_section["subsections"].append(
                {
                    "number": int(number_text),
                    "title": title.strip(),
                    "start_page": int(start_page),
                }
            )

    # 第十章在印刷目录中没有“（一）”层，站点仍需一页，故补成唯一内容节。
    for chapter in chapters:
        if not chapter["sections"]:
            chapter["sections"].append(
                {
                    "id": f"{chapter['number']:02d}-01",
                    "chapter_number": chapter["number"],
                    "section_number": 1,
                    "chapter": chapter["label"],
                    "title": chapter["title"],
                    "start_page": chapter["start_page"],
                    "end_page": None,
                    "subsections": [],
                    "synthetic": True,
                }
            )

    sections = [
        section
        for chapter in chapters
        for section in chapter["sections"]
    ]

    for index, section in enumerate(sections):
        if index + 1 < len(sections):
            next_start = sections[index + 1]["start_page"]
            # Several adjacent sections begin on the same physical PDF page.
            # Keep that shared page in both ranges; build_html.py later splits
            # the page exactly at its printed section heading.
            section["end_page"] = max(section["start_page"], next_start - 1)
        else:
            section["end_page"] = 192

    result = {
        "source": PDF_PATH.name,
        "page_count": 192,
        "chapters": chapters,
        "sections": sections,
    }
    return result


def validate(data: dict) -> None:
    chapters = data["chapters"]
    sections = data["sections"]
    starts = [section["start_page"] for section in sections]

    assert len(chapters) == 10, f"章节数应为 10，实际为 {len(chapters)}"
    assert len(sections) == 48, f"节总数应为 48，实际为 {len(sections)}"
    assert starts == sorted(starts), "start_page 未单调递增"
    assert sections[-1]["end_page"] == 192, "最后一节 end_page 应为 192"
    assert all(
        section["end_page"] >= section["start_page"] for section in sections
    ), "存在无效页码范围"

    section_lookup = {
        (section["chapter_number"], section["section_number"]): section
        for section in sections
    }
    assert section_lookup[(1, 2)]["start_page"] == 9
    assert section_lookup[(4, 1)]["start_page"] == 53


def main() -> None:
    data = parse_toc()
    validate(data)
    OUTPUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"目录解析完成：{len(data['chapters'])} 章，{len(data['sections'])} 节")
    print("抽查：01-02 起始页=9；04-01 起始页=53")
    print(f"最大 end_page={max(s['end_page'] for s in data['sections'])}")
    print(f"输出：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
