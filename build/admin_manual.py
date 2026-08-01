#!/usr/bin/env python
"""Build the administrator manual as an isolated static site under site/admin."""

from __future__ import annotations

import html
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import fitz

import build_html as legacy


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build" / "admin"
SITE_DIR = ROOT / "site" / "admin"
CHAPTER_DIR = SITE_DIR / "chapters"
IMAGE_DIR = SITE_DIR / "assets" / "images"
JS_DIR = SITE_DIR / "assets" / "js"
CSS_DIR = SITE_DIR / "assets" / "css"
CONTENT_PATH = BUILD_DIR / "content.json"
SECTIONS_PATH = BUILD_DIR / "sections.json"
REPORT_PATH = BUILD_DIR / "validation-report.json"
FIRST_CONTENT_PAGE = 8
LAST_CONTENT_PAGE = 175

ADMIN_CSS = """

/* Administrator manual: subsection numbers are part of the links themselves. */
.in-page-toc ol {
  padding-left: 0;
  list-style: none;
}

/* Small UI glyphs from the PDF belong inside the surrounding brackets. */
.inline-icon {
  display: inline-block;
  width: auto;
  height: 1.35em;
  max-width: 3em;
  margin: 0 0.12em;
  vertical-align: -0.28em;
  object-fit: contain;
}
"""

INLINE_ICON_TOKEN_RE = re.compile(r"@@INLINE_ICON:([^@]+)@@")

PDF_CANDIDATE = Path(
    r"D:\Desktop\20260724_刘炎参加湖南省李燕数字教研工作室网络平台材料_26秋"
    r"\1.网络平台管理材料\2.操作手册\湖南省数字教研工作室操作手册（管理员）.pdf"
)

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


def find_pdf() -> Path:
    if PDF_CANDIDATE.is_file():
        return PDF_CANDIDATE
    matches = list(Path(r"D:\Desktop").rglob("*数字教研工作室*管理员*.pdf"))
    if not matches:
        raise FileNotFoundError("找不到管理员操作手册 PDF")
    return matches[0]


def chinese_number_to_int(value: str) -> int:
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


def clean_pdf_lines(value: str) -> str:
    """Join visual PDF lines and remove extraction spaces inside Chinese words."""
    text = "".join(line.strip() for line in value.splitlines() if line.strip())
    text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text)
    text = re.sub(r"\s+([，。；：！？、）】》])", r"\1", text)
    text = re.sub(r"([（【《])\s+", r"\1", text)
    return text


def is_heading_block(block: dict, section: dict) -> bool:
    if block.get("type") != "text":
        return False
    lines = [line.strip() for line in block.get("text", "").splitlines() if line.strip()]
    if any(legacy.is_printed_heading(line, section) for line in lines):
        return True
    if not lines:
        return False
    match = legacy.SUBSECTION_RE.match(lines[0])
    if not match:
        return False
    number = int(match.group(1))
    return number in {int(item["number"]) for item in section.get("subsections", [])}


def merge_continuation_blocks(section: dict, blocks: list[dict]) -> list[dict]:
    """Merge PDF visual-line blocks that belong to one natural paragraph."""
    merged: list[dict] = []
    terminal = ("。", "！", "？", "；", ".", "!", "?", ";")
    for source_block in blocks:
        block = dict(source_block)
        if (
            block.get("type") == "text"
            and merged
            and merged[-1].get("type") == "text"
            and not is_heading_block(merged[-1], section)
            and not is_heading_block(block, section)
            and not clean_pdf_lines(merged[-1]["text"]).endswith(terminal)
        ):
            previous = merged[-1]
            previous["text"] = previous["text"].rstrip() + "\n" + block["text"].lstrip()
            previous["bbox"] = [
                min(previous["bbox"][0], block["bbox"][0]),
                min(previous["bbox"][1], block["bbox"][1]),
                max(previous["bbox"][2], block["bbox"][2]),
                max(previous["bbox"][3], block["bbox"][3]),
            ]
            continue
        merged.append(block)
    return merged


def embed_inline_icons(blocks: list[dict]) -> tuple[list[dict], int]:
    """Move small PDF UI glyphs into the nearby empty brackets or quotes."""
    prepared = [dict(block) for block in blocks]
    remove_indexes: set[int] = set()
    embedded = 0
    placeholder = re.compile(r"【\s*】|“\s*”")

    for index, block in enumerate(prepared):
        if block.get("type") != "image":
            continue
        if int(block.get("width", 0)) > 64 or int(block.get("height", 0)) > 64:
            continue

        token = f"@@INLINE_ICON:{block['src']}@@"
        target_index: int | None = None
        for candidate in (index - 1, index + 1, index - 2, index + 2):
            if candidate < 0 or candidate >= len(prepared):
                continue
            candidate_block = prepared[candidate]
            if candidate_block.get("type") != "text":
                continue
            if placeholder.search(candidate_block.get("text", "")):
                target_index = candidate
                break

        if target_index is None:
            raise AssertionError(
                f"第 {block.get('page')} 页小图标未找到相邻占位符：{block['src']}"
            )

        text = prepared[target_index]["text"]
        prepared[target_index]["text"] = placeholder.sub(
            lambda match: match.group(0)[0] + token + match.group(0)[-1],
            text,
            count=1,
        )
        remove_indexes.add(index)
        embedded += 1

    return [
        block for index, block in enumerate(prepared) if index not in remove_indexes
    ], embedded


ORIGINAL_RENDER_TEXT_BLOCK = legacy.render_text_block


def render_text_block_with_inline_icons(
    block: dict, section: dict
) -> tuple[str, int | None]:
    markup, subsection_number = ORIGINAL_RENDER_TEXT_BLOCK(block, section)

    def icon_markup(match: re.Match[str]) -> str:
        src = html.escape(match.group(1), quote=True)
        return (
            f'<img class="inline-icon" src="../assets/images/{src}" '
            'alt="操作图标" loading="lazy" decoding="async">'
        )

    return INLINE_ICON_TOKEN_RE.sub(icon_markup, markup), subsection_number


def parse_toc(pdf_path: Path) -> dict:
    chapters: list[dict] = []
    current_chapter: dict | None = None
    current_section: dict | None = None

    with fitz.open(pdf_path) as doc:
        if doc.page_count != LAST_CONTENT_PAGE:
            raise AssertionError(
                f"PDF 页数应为 {LAST_CONTENT_PAGE}，实际为 {doc.page_count}"
            )
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

    sections = [section for chapter in chapters for section in chapter["sections"]]
    for index, section in enumerate(sections):
        if index + 1 < len(sections):
            next_start = sections[index + 1]["start_page"]
            section["end_page"] = max(section["start_page"], next_start - 1)
        else:
            section["end_page"] = LAST_CONTENT_PAGE

    if len(chapters) != 14 or len(sections) != 68:
        raise AssertionError(
            f"目录解析结果异常：{len(chapters)} 章，{len(sections)} 节"
        )
    if [item["start_page"] for item in sections] != sorted(
        item["start_page"] for item in sections
    ):
        raise AssertionError("目录起始页未按顺序排列")

    return {
        "source": pdf_path.name,
        "page_count": LAST_CONTENT_PAGE,
        "chapters": chapters,
        "sections": sections,
    }


def round_bbox(bbox: tuple[float, float, float, float]) -> list[float]:
    return [round(float(value), 2) for value in bbox]


def extract_text_block(block: dict) -> dict | None:
    lines: list[str] = []
    sizes: list[float] = []
    fonts: list[str] = []
    for line in block.get("lines", []):
        text = "".join(span.get("text", "") for span in line.get("spans", [])).rstrip()
        if text:
            lines.append(text)
        for span in line.get("spans", []):
            if span.get("text", "").strip():
                sizes.append(float(span.get("size", 0)))
                fonts.append(str(span.get("font", "")))
    text = "\n".join(lines).strip()
    if not text:
        return None
    return {
        "type": "text",
        "text": text,
        "bbox": round_bbox(block["bbox"]),
        "font_size": round(max(sizes), 2) if sizes else 0,
        "font": fonts[0] if fonts else "",
    }


def extract_content(pdf_path: Path) -> dict:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    content: dict[str, list[dict]] = {}
    exported_xrefs: dict[int, str] = {}
    image_occurrences = 0

    with fitz.open(pdf_path) as doc:
        for page_number in range(FIRST_CONTENT_PAGE, LAST_CONTENT_PAGE + 1):
            page = doc[page_number - 1]
            blocks: list[dict] = []
            for raw_block in page.get_text("dict").get("blocks", []):
                if raw_block.get("type") == 0:
                    text_block = extract_text_block(raw_block)
                    if text_block:
                        blocks.append(text_block)

            image_infos = sorted(
                page.get_image_info(xrefs=True),
                key=lambda info: (float(info["bbox"][1]), float(info["bbox"][0])),
            )
            for sequence, image_info in enumerate(image_infos, start=1):
                xref = int(image_info.get("xref", 0))
                if xref <= 0:
                    raise AssertionError(f"第 {page_number} 页存在无法提取的图片")
                if xref not in exported_xrefs:
                    image_data = doc.extract_image(xref)
                    extension = image_data["ext"].lower()
                    if extension == "jpg":
                        extension = "jpeg"
                    if extension not in {"png", "jpeg"}:
                        raise AssertionError(f"不支持的图片格式：{extension}")
                    filename = f"p{page_number:03d}_{sequence}.{extension}"
                    (IMAGE_DIR / filename).write_bytes(image_data["image"])
                    exported_xrefs[xref] = filename
                blocks.append(
                    {
                        "type": "image",
                        "src": exported_xrefs[xref],
                        "bbox": round_bbox(image_info["bbox"]),
                        "xref": xref,
                        "width": int(image_info.get("width", 0)),
                        "height": int(image_info.get("height", 0)),
                    }
                )
                image_occurrences += 1

            blocks.sort(
                key=lambda block: (
                    block["bbox"][1],
                    block["bbox"][0],
                    0 if block["type"] == "text" else 1,
                )
            )
            content[str(page_number)] = blocks

    # Different PDF engines count a few shared image objects differently.
    # PyMuPDF exposes 375 placed screenshots for this document; keep all of
    # them instead of dropping objects merely to match another engine's count.
    if not 360 <= image_occurrences <= 390:
        raise AssertionError(f"图片引用数异常：{image_occurrences}")
    return {
        "source": pdf_path.name,
        "first_page": FIRST_CONTENT_PAGE,
        "last_page": LAST_CONTENT_PAGE,
        "image_occurrences": image_occurrences,
        "unique_images": len(exported_xrefs),
        "pages": content,
    }


def adminize(markup: str, *, index: bool = False) -> str:
    replacements = {
        "湖南省数字教研工作室成员操作手册离线文档站": "湖南省李燕数字教研工作室管理员手册文档站",
        "数字教研工作室用户操作手册": "数字教研工作室管理员操作手册",
        "湖南省数字教研工作室 · 成员版": "湖南省数字教研工作室 · 管理员版",
        "10 个章节": "14 个章节",
        "48 个内容页": "68 个内容页",
        "按章节浏览平台操作方法，所有内容和截图均来自原始 192 页手册，可直接双击离线阅读。": "按章节浏览平台管理操作方法，可直接离线阅读。",
        "数字教研工作室管理员操作手册 · 离线版": "数字教研工作室管理员操作手册",
        "数字教研工作室<br>用户操作手册": "数字教研工作室<br>管理员操作手册",
    }
    for old, new in replacements.items():
        markup = markup.replace(old, new)
    if index:
        old_title = "<h1>数字教研工作室管理员操作手册</h1>"
        new_title = """<div class="hero-title">
            <img class="hero-logo" src="assets/images/badge-logo.png"
              alt="湖南省李燕数字教研工作室徽章">
            <h1>湖南省李燕数字教研工作室管理员手册</h1>
          </div>"""
        markup = markup.replace(old_title, new_title, 1)
    return markup


class ReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[str] = []
        self.links: list[str] = []
        self.resources: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(str(attributes["id"]))
        if tag == "img" and attributes.get("src"):
            self.images.append(str(attributes["src"]))
        if tag == "a" and attributes.get("href"):
            self.links.append(str(attributes["href"]))
        if tag == "script" and attributes.get("src"):
            self.resources.append(str(attributes["src"]))
        if tag == "link" and attributes.get("href"):
            self.resources.append(str(attributes["href"]))


def resolve_reference(source: Path, reference: str) -> tuple[Path, str]:
    parsed = urlsplit(reference)
    target_text = unquote(parsed.path)
    target = source if not target_text else source.parent / target_text
    return target.resolve(), parsed.fragment


def validate_site(
    sections: list[dict], image_count: int, expected_inline_icons: int
) -> dict:
    html_files = sorted(SITE_DIR.rglob("*.html"))
    chapter_files = sorted(CHAPTER_DIR.glob("*.html"))
    if len(chapter_files) != 68 or len(html_files) != 69:
        raise AssertionError(
            f"页面数量异常：章节页 {len(chapter_files)}，总页面 {len(html_files)}"
        )

    missing_images: list[str] = []
    broken_links: list[str] = []
    missing_resources: list[str] = []
    hard_break_paragraphs: list[str] = []
    image_references = 0
    inline_icons = 0

    for html_path in html_files:
        source = html_path.read_text(encoding="utf-8")
        parser = ReferenceParser()
        parser.feed(source)
        image_references += len(parser.images)
        inline_icons += source.count('class="inline-icon"')
        if re.search(r"<p>[^<]*\n[^<]*</p>", source):
            hard_break_paragraphs.append(html_path.name)

        for image_ref in parser.images:
            target, _ = resolve_reference(html_path, image_ref)
            if not target.is_file():
                missing_images.append(f"{html_path.name}: {image_ref}")
        for resource_ref in parser.resources:
            parsed = urlsplit(resource_ref)
            if parsed.scheme or parsed.netloc:
                missing_resources.append(resource_ref)
                continue
            target, _ = resolve_reference(html_path, resource_ref)
            if not target.is_file():
                missing_resources.append(f"{html_path.name}: {resource_ref}")
        for link_ref in parser.links:
            parsed = urlsplit(link_ref)
            if parsed.scheme or parsed.netloc:
                continue
            target, fragment = resolve_reference(html_path, link_ref)
            if not target.is_file():
                broken_links.append(f"{html_path.name}: {link_ref}")
                continue
            if fragment and target == html_path.resolve() and fragment not in parser.ids:
                broken_links.append(f"{html_path.name}: {link_ref}（锚点缺失）")

    if missing_images or broken_links or missing_resources or hard_break_paragraphs:
        raise AssertionError(
            "站点校验失败："
            f"缺图 {len(missing_images)}，失效链接 {len(broken_links)}，"
            f"资源异常 {len(missing_resources)}，硬换行 {len(hard_break_paragraphs)}"
        )
    if inline_icons != expected_inline_icons:
        raise AssertionError(
            f"行内图标数量异常：{inline_icons}/{expected_inline_icons}"
        )

    js_source = (JS_DIR / "main.js").read_text(encoding="utf-8")
    search_source = (JS_DIR / "search-index.js").read_text(encoding="utf-8")
    index_source = (SITE_DIR / "index.html").read_text(encoding="utf-8")
    if "initSearchHighlights" not in js_source or "clearHighlights" not in js_source:
        raise AssertionError("搜索高亮及取消功能缺失")
    if "showCurrentSection" not in js_source or "sidebar-collapsed" not in js_source:
        raise AssertionError("导航标题联动或折叠功能缺失")
    if "window.SEARCH_INDEX=" not in search_source:
        raise AssertionError("管理员搜索索引缺失")
    if "湖南省李燕数字教研工作室管理员手册" not in index_source:
        raise AssertionError("管理员首页标题缺失")
    if "用户手册" in index_source or "用户操作手册" in index_source:
        raise AssertionError("管理员首页混入用户版标题")

    return {
        "chapters": 14,
        "chapter_pages": len(chapter_files),
        "html_pages": len(html_files),
        "image_files": image_count,
        "image_references": image_references,
        "missing_images": 0,
        "broken_links": 0,
        "missing_resources": 0,
        "hard_break_paragraphs": 0,
        "inline_icons": inline_icons,
        "search_entries": len(sections),
        "search_highlight_dismiss": "pass",
        "dynamic_sidebar_title": "pass",
        "sidebar_collapse": "pass",
    }


def prepare_site() -> None:
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    CHAPTER_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    JS_DIR.mkdir(parents=True, exist_ok=True)
    CSS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "site" / "assets" / "css" / "style.css", CSS_DIR / "style.css")
    with (CSS_DIR / "style.css").open("a", encoding="utf-8") as stream:
        stream.write(ADMIN_CSS)
    shutil.copy2(ROOT / "site" / "assets" / "js" / "main.js", JS_DIR / "main.js")
    shutil.copy2(
        ROOT / "site" / "assets" / "images" / "badge-logo.png",
        IMAGE_DIR / "badge-logo.png",
    )


def main() -> None:
    pdf_path = find_pdf()
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    prepare_site()

    sections_data = parse_toc(pdf_path)
    content_data = extract_content(pdf_path)
    SECTIONS_PATH.write_text(
        json.dumps(sections_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    CONTENT_PATH.write_text(
        json.dumps(content_data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    legacy.INT_TO_CHINESE.update({13: "十三", 14: "十四"})
    legacy.join_pdf_lines = clean_pdf_lines
    legacy.render_text_block = render_text_block_with_inline_icons
    chapters = sections_data["chapters"]
    sections = sections_data["sections"]
    flattened = legacy.flatten_content(content_data)
    segmented = legacy.split_sections(sections, flattened)
    inline_icon_count = 0
    prepared_segments: dict[str, list[dict]] = {}
    for section in sections:
        embedded_blocks, embedded_count = embed_inline_icons(
            segmented[section["id"]]
        )
        inline_icon_count += embedded_count
        prepared_segments[section["id"]] = merge_continuation_blocks(
            section, embedded_blocks
        )
    segmented = prepared_segments

    search_index: list[dict] = []
    subsection_warnings: list[dict] = []
    for index, section in enumerate(sections):
        markup, found_subsections = legacy.build_chapter_page(
            chapters, sections, section, index, segmented[section["id"]]
        )
        markup = adminize(markup)
        (CHAPTER_DIR / f"{section['id']}.html").write_text(markup, encoding="utf-8")

        expected = {int(item["number"]) for item in section.get("subsections", [])}
        missing = sorted(expected - found_subsections)
        if missing:
            subsection_warnings.append({"section": section["id"], "missing": missing})

        search_text = " ".join(
            INLINE_ICON_TOKEN_RE.sub(
                "图标", legacy.join_pdf_lines(block["text"])
            )
            for block in segmented[section["id"]]
            if block["type"] == "text"
        )
        search_index.append(
            {
                "id": section["id"],
                "title": section["title"],
                "chapter": section["chapter"],
                "url": f"chapters/{section['id']}.html",
                "text": search_text,
            }
        )

    manual_image_count = content_data["unique_images"]
    index_markup = adminize(
        legacy.build_index(chapters, manual_image_count), index=True
    )
    (SITE_DIR / "index.html").write_text(index_markup, encoding="utf-8")
    (JS_DIR / "search-index.js").write_text(
        "window.SEARCH_INDEX="
        + json.dumps(search_index, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )

    report = validate_site(sections, manual_image_count, inline_icon_count)
    report["image_occurrences"] = content_data["image_occurrences"]
    report["subsection_warnings"] = subsection_warnings
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        "管理员手册构建完成："
        f"{report['chapters']} 章，{report['chapter_pages']} 个内容页，"
        f"{report['image_files']} 张截图，{report['broken_links']} 个失效链接"
    )
    print(f"小节标题识别警告：{len(subsection_warnings)}")
    print(f"输出：{SITE_DIR}")


if __name__ == "__main__":
    main()
