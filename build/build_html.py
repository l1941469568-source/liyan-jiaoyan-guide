#!/usr/bin/env python
"""Build the complete offline HTML manual and validate local references."""

from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build"
SITE_DIR = ROOT / "site"
CHAPTER_DIR = SITE_DIR / "chapters"
IMAGE_DIR = SITE_DIR / "assets" / "images"
JS_DIR = SITE_DIR / "assets" / "js"
SECTIONS_PATH = BUILD_DIR / "sections.json"
CONTENT_PATH = BUILD_DIR / "content.json"
REPORT_PATH = BUILD_DIR / "validation-report.json"

SUBSECTION_RE = re.compile(r"^\s*(\d{1,2})\s*[.、．]\s*(.+?)\s*$")
CALLOUT_RE = re.compile(r"^\s*(注意|提示)\s*[：:]")
INLINE_ICON_TOKEN_RE = re.compile(r"@@INLINE_ICON:([^@]+)@@")

INT_TO_CHINESE = {
    1: "一",
    2: "二",
    3: "三",
    4: "四",
    5: "五",
    6: "六",
    7: "七",
    8: "八",
    9: "九",
    10: "十",
    11: "十一",
    12: "十二",
}


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"缺少构建输入：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_heading(value: str) -> str:
    translation = str.maketrans({"(": "（", ")": "）", "．": ".", "、": "."})
    return re.sub(r"\s+", "", value.translate(translation)).strip()


def normalize_title(value: str) -> str:
    return re.sub(r"[\s/／、，,。；;：:（）()\[\]【】]+", "", value).strip()


def join_pdf_lines(value: str) -> str:
    return "".join(line.strip() for line in value.splitlines() if line.strip())


def flatten_content(content: dict) -> list[dict]:
    flattened: list[dict] = []
    for page_number in range(content["first_page"], content["last_page"] + 1):
        for order, block in enumerate(content["pages"][str(page_number)]):
            flattened.append({**block, "page": page_number, "order": order})
    return flattened


def marker_token(section: dict) -> str:
    if section["section_number"] == 1:
        return normalize_heading(section["chapter"])
    chinese = INT_TO_CHINESE[section["section_number"]]
    return normalize_heading(f"（{chinese}）{section['title']}")


def locate_section_starts(
    sections: list[dict], blocks: list[dict]
) -> list[int]:
    starts: list[int] = []
    search_from = 0

    for section in sections:
        token = marker_token(section)
        expected_page = section["start_page"]
        found: int | None = None

        for index in range(search_from, len(blocks)):
            block = blocks[index]
            if block["page"] > expected_page + 1:
                break
            if block["page"] < expected_page - 1 or block["type"] != "text":
                continue
            if token in normalize_heading(block["text"]):
                found = index
                break

        if found is None:
            raise AssertionError(
                f"未在第 {expected_page} 页附近找到节起点："
                f"{section['id']} {section['title']}（标记 {token}）"
            )
        if starts and found <= starts[-1]:
            raise AssertionError(f"节起点顺序异常：{section['id']}")
        starts.append(found)
        search_from = found + 1

    return starts


def split_sections(
    sections: list[dict], blocks: list[dict]
) -> dict[str, list[dict]]:
    starts = locate_section_starts(sections, blocks)
    segmented: dict[str, list[dict]] = {}
    for index, section in enumerate(sections):
        end = starts[index + 1] if index + 1 < len(starts) else len(blocks)
        segmented[section["id"]] = blocks[starts[index] : end]

    assigned_count = sum(len(items) for items in segmented.values())
    leading_count = starts[0]
    assert leading_count == 0, f"第一个节标题前存在 {leading_count} 个未分配块"
    assert assigned_count == len(blocks), (
        f"块分节后数量不一致：{assigned_count}/{len(blocks)}"
    )
    return segmented


def embed_inline_icons(blocks: list[dict]) -> tuple[list[dict], int]:
    """Move small PDF UI glyphs into their nearby empty brackets or quotes."""
    prepared = [dict(block) for block in blocks]
    remove_indexes: set[int] = set()
    embedded = 0
    placeholder = re.compile(r"【\s*】|“\s*”|（\s*）")

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


def render_inline_icon_markup(markup: str) -> str:
    def icon_markup(match: re.Match[str]) -> str:
        src = html.escape(match.group(1), quote=True)
        return (
            f'<img class="inline-icon" src="../assets/images/{src}" '
            'alt="操作图标" loading="lazy" decoding="async">'
        )

    return INLINE_ICON_TOKEN_RE.sub(icon_markup, markup)


def relative_paths(depth: str) -> tuple[str, str, str]:
    if depth == "chapter":
        return "../assets/css/style.css", "../assets/js/", "../index.html"
    return "assets/css/style.css", "assets/js/", "index.html"


def render_head(title: str, depth: str) -> str:
    css_path, js_path, _ = relative_paths(depth)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="description" content="湖南省数字教研工作室成员操作手册离线文档站">
  <title>{html.escape(title)}｜数字教研工作室用户操作手册</title>
  <link rel="stylesheet" href="{css_path}">
  <script src="{js_path}search-index.js" defer></script>
  <script src="{js_path}main.js" defer></script>
</head>"""


def render_sidebar(
    chapters: list[dict],
    current_id: str | None,
    depth: str,
) -> str:
    _, _, home_path = relative_paths(depth)
    nav_parts: list[str] = []
    for chapter in chapters:
        is_current_chapter = any(
            section["id"] == current_id for section in chapter["sections"]
        )
        open_attribute = " open" if is_current_chapter else ""
        if current_id is None and chapter["number"] == 1:
            open_attribute = " open"
        section_links = []
        for section in chapter["sections"]:
            if depth == "chapter":
                href = f"{section['id']}.html"
            else:
                href = f"chapters/{section['id']}.html"
            active = section["id"] == current_id
            active_attributes = (
                ' class="active" aria-current="page"' if active else ""
            )
            section_links.append(
                f'<li><a href="{href}"{active_attributes}>'
                f"{html.escape(section['title'])}</a></li>"
            )
        nav_parts.append(
            f"""<details class="nav-chapter"{open_attribute}>
  <summary>{html.escape(chapter['label'])}</summary>
  <ol class="nav-sections">
    {''.join(section_links)}
  </ol>
</details>"""
        )

    return f"""<aside class="sidebar" id="sidebar" aria-label="手册章节导航">
  <a class="sidebar-brand" href="{home_path}">
    <span class="brand-kicker">OFFLINE MANUAL</span>
    <span class="brand-title">数字教研工作室<br>用户操作手册</span>
  </a>
  <div class="sidebar-search">
    <label class="search-label" for="site-search">搜索手册内容</label>
    <input class="search-input" id="site-search" type="search"
      placeholder="例如：直播、备课本" autocomplete="off">
    <div class="search-results" id="search-results" role="listbox" hidden></div>
  </div>
  <nav class="chapter-tree">
    {''.join(nav_parts)}
  </nav>
</aside>"""


def render_chrome_start(
    title: str,
    chapters: list[dict],
    current_id: str | None,
    depth: str,
) -> str:
    page_type = "chapter" if depth == "chapter" else "index"
    return f"""{render_head(title, depth)}
<body data-page-type="{page_type}">
  <a class="skip-link" href="#main-content">跳到正文</a>
  <header class="mobile-header">
    <button class="menu-toggle" id="menu-toggle" type="button"
      aria-controls="sidebar" aria-expanded="false" aria-label="打开章节导航">☰</button>
    <span class="mobile-title">{html.escape(title)}</span>
  </header>
  {render_sidebar(chapters, current_id, depth)}
  <button class="drawer-overlay" id="drawer-overlay" type="button"
    aria-label="关闭章节导航"></button>"""


def render_chrome_end() -> str:
    return """  <div class="lightbox" id="lightbox" role="dialog"
    aria-modal="true" aria-label="截图放大预览" hidden>
    <button class="lightbox-close" id="lightbox-close" type="button"
      aria-label="关闭预览">×</button>
    <img class="lightbox-image" id="lightbox-image" alt="">
    <p class="lightbox-caption" id="lightbox-caption"></p>
  </div>
</body>
</html>
"""


def expected_subsections(section: dict) -> dict[int, str]:
    return {
        int(item["number"]): normalize_title(item["title"])
        for item in section.get("subsections", [])
    }


def is_printed_heading(text: str, section: dict) -> bool:
    normalized = normalize_heading(text)
    chapter_token = normalize_heading(section["chapter"])
    chinese = INT_TO_CHINESE.get(section["section_number"], "")
    section_token = normalize_heading(f"（{chinese}）{section['title']}")
    if normalized == chapter_token:
        return True
    if normalized == section_token:
        return True
    if section.get("synthetic") and normalized == chapter_token:
        return True
    return False


def render_text_block(block: dict, section: dict) -> tuple[str, int | None]:
    raw_lines = [line.strip() for line in block["text"].splitlines() if line.strip()]
    raw_lines = [
        line for line in raw_lines if not is_printed_heading(line, section)
    ]
    if not raw_lines:
        return "", None

    subsection_map = expected_subsections(section)
    first_match = SUBSECTION_RE.match(raw_lines[0])
    if first_match:
        number = int(first_match.group(1))
        candidate_title = normalize_title(first_match.group(2))
        expected_title = subsection_map.get(number)
        if expected_title and (
            candidate_title == expected_title
            or candidate_title in expected_title
            or expected_title in candidate_title
        ):
            heading = (
                f'<h3 id="step-{number}">'
                f"{html.escape(first_match.group(1))}. "
                f"{html.escape(first_match.group(2).strip())}</h3>"
            )
            remainder = join_pdf_lines("\n".join(raw_lines[1:]))
            if remainder:
                heading += f"<p>{html.escape(remainder)}</p>"
            return render_inline_icon_markup(heading), number

    text = join_pdf_lines("\n".join(raw_lines))
    if not text:
        return "", None
    if CALLOUT_RE.match(text):
        return (
            f'<blockquote class="callout" role="note">'
            f"{render_inline_icon_markup(html.escape(text))}</blockquote>",
            None,
        )
    return f"<p>{render_inline_icon_markup(html.escape(text))}</p>", None


def render_article_blocks(
    section: dict, blocks: list[dict]
) -> tuple[str, set[int]]:
    rendered: list[str] = []
    found_subsections: set[int] = set()
    image_sequence_by_page: dict[int, int] = {}

    for block in blocks:
        if block["type"] == "text":
            markup, subsection_number = render_text_block(block, section)
            if markup:
                rendered.append(markup)
            if subsection_number is not None:
                found_subsections.add(subsection_number)
            continue

        page = int(block["page"])
        image_sequence_by_page[page] = image_sequence_by_page.get(page, 0) + 1
        sequence = image_sequence_by_page[page]
        src = f"../assets/images/{html.escape(block['src'], quote=True)}"
        alt = f"原手册第 {page} 页操作截图 {sequence}"
        rendered.append(
            f"""<figure class="manual-figure" data-source-page="{page}">
  <img src="{src}" alt="{alt}" loading="lazy" decoding="async">
  <figcaption>{alt}（点击可放大）</figcaption>
</figure>"""
        )

    return "\n".join(rendered), found_subsections


def render_subsection_toc(section: dict) -> str:
    subsections = section.get("subsections", [])
    if not subsections:
        return ""
    items = "".join(
        f'<li><a href="#step-{item["number"]}">'
        f'{item["number"]}. {html.escape(item["title"])}</a></li>'
        for item in subsections
    )
    return f"""<nav class="in-page-toc" aria-label="本节内容">
  <strong>本节内容</strong>
  <ol>{items}</ol>
</nav>"""


def render_pagination(sections: list[dict], index: int) -> str:
    previous_section = sections[index - 1] if index > 0 else None
    next_section = sections[index + 1] if index + 1 < len(sections) else None

    if previous_section:
        previous = f"""<a class="page-link previous"
      href="{previous_section['id']}.html">
      <small>← 上一节</small>
      <strong>{html.escape(previous_section['title'])}</strong>
    </a>"""
    else:
        previous = '<span class="pagination-spacer" aria-hidden="true"></span>'

    if next_section:
        following = f"""<a class="page-link next"
      href="{next_section['id']}.html">
      <small>下一节 →</small>
      <strong>{html.escape(next_section['title'])}</strong>
    </a>"""
    else:
        following = '<span class="pagination-spacer" aria-hidden="true"></span>'

    return f"""<nav class="section-pagination" aria-label="前后章节">
    {previous}
    {following}
  </nav>"""


def build_chapter_page(
    chapters: list[dict],
    sections: list[dict],
    section: dict,
    section_index: int,
    blocks: list[dict],
) -> tuple[str, set[int]]:
    article_markup, found_subsections = render_article_blocks(section, blocks)
    page_range = (
        f"原手册第 {section['start_page']} 页"
        if section["start_page"] == section["end_page"]
        else f"原手册第 {section['start_page']}–{section['end_page']} 页"
    )
    return (
        f"""{render_chrome_start(section['title'], chapters, section['id'], "chapter")}
  <main class="page-shell" id="main-content">
    <div class="content-wrap">
      <p class="breadcrumbs"><a href="../index.html">手册首页</a> /
        {html.escape(section['chapter'])} / {html.escape(section['title'])}</p>
      <article class="article-card">
        <header class="article-header">
          <p class="chapter-label">{html.escape(section['chapter'])}</p>
          <h1>{html.escape(section['title'])}</h1>
          <p class="page-range">{page_range}</p>
        </header>
        <div class="article-body">
          {render_subsection_toc(section)}
          {article_markup}
          {render_pagination(sections, section_index)}
        </div>
      </article>
      <footer class="site-footer">数字教研工作室用户操作手册 · 离线版</footer>
    </div>
  </main>
{render_chrome_end()}""",
        found_subsections,
    )


def build_index(chapters: list[dict], image_count: int) -> str:
    catalog_cards = []
    for chapter in chapters:
        items = "".join(
            f'<li><a href="chapters/{section["id"]}.html">'
            f"{html.escape(section['title'])}</a></li>"
            for section in chapter["sections"]
        )
        catalog_cards.append(
            f"""<section class="catalog-chapter">
  <h2>{html.escape(chapter['label'])}</h2>
  <ol>{items}</ol>
</section>"""
        )

    return f"""{render_chrome_start("手册首页", chapters, None, "index")}
  <main class="page-shell" id="main-content">
    <div class="content-wrap">
      <article class="home-card">
        <header class="hero">
          <p class="hero-eyebrow">湖南省数字教研工作室 · 成员版</p>
          <h1>数字教研工作室用户操作手册</h1>
          <p>按章节浏览平台操作方法，所有内容和截图均来自原始 192 页手册，可直接双击离线阅读。</p>
          <div class="hero-stats">
            <span class="hero-stat">10 个章节</span>
            <span class="hero-stat">48 个内容页</span>
            <span class="hero-stat">{image_count} 张清晰截图</span>
            <span class="hero-stat">支持站内搜索</span>
          </div>
        </header>
        <div class="home-content">
          <section class="guide-box" aria-label="使用说明">
            <div class="guide-step"><b>1</b><p>从左侧目录或下方完整目录选择要学习的操作主题。</p></div>
            <div class="guide-step"><b>2</b><p>按文字与截图顺序阅读；点击截图可查看清晰原图。</p></div>
            <div class="guide-step"><b>3</b><p>用左侧搜索框查找“直播”“备课本”等关键词。</p></div>
          </section>
          <h2 class="catalog-title">完整目录</h2>
          <div class="catalog-grid">
            {''.join(catalog_cards)}
          </div>
        </div>
      </article>
      <footer class="site-footer">数字教研工作室用户操作手册 · 离线版</footer>
    </div>
  </main>
{render_chrome_end()}"""


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
        if tag == "img" and attributes.get("src") is not None:
            self.images.append(str(attributes["src"]))
        if tag == "a" and attributes.get("href") is not None:
            self.links.append(str(attributes["href"]))
        if tag == "script" and attributes.get("src") is not None:
            self.resources.append(str(attributes["src"]))
        if tag == "link" and attributes.get("href") is not None:
            self.resources.append(str(attributes["href"]))


class ArticleContentParser(HTMLParser):
    VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__()
        self.body_depth = 0
        self.skip_depth = 0
        self.text_parts: list[str] = []
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set(str(attributes.get("class", "")).split())
        if self.body_depth == 0 and tag == "div" and "article-body" in classes:
            self.body_depth = 1
            return
        if self.body_depth == 0:
            return
        if tag not in self.VOID_TAGS:
            self.body_depth += 1
        if tag == "nav" and "in-page-toc" in classes:
            self.skip_depth = self.body_depth
        if tag == "img" and not self.skip_depth and attributes.get("src"):
            self.images.append(str(attributes["src"]))

    def handle_endtag(self, tag: str) -> None:
        if self.body_depth == 0:
            return
        if self.skip_depth == self.body_depth:
            self.skip_depth = 0
        self.body_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.body_depth and not self.skip_depth and data.strip():
            self.text_parts.append(data)


def resolve_local_reference(html_path: Path, reference: str) -> tuple[Path, str]:
    parsed = urlsplit(reference)
    target_text = unquote(parsed.path)
    target = html_path if not target_text else (html_path.parent / target_text)
    return target.resolve(), parsed.fragment


def validate_pdf_spot_checks(
    sections: list[dict],
    segmented: dict[str, list[dict]],
) -> list[str]:
    section_lookup = {section["id"]: section for section in sections}
    checked: list[str] = []

    for section_id in ("01-02", "04-01"):
        section = section_lookup[section_id]
        page_path = CHAPTER_DIR / f"{section_id}.html"
        parser = ArticleContentParser()
        parser.feed(page_path.read_text(encoding="utf-8"))
        actual_text = normalize_heading("".join(parser.text_parts))

        for block in segmented[section_id]:
            if block["type"] != "text":
                continue
            lines = [
                line.strip()
                for line in block["text"].splitlines()
                if line.strip() and not is_printed_heading(line, section)
            ]
            expected_text = normalize_heading(join_pdf_lines("\n".join(lines)))
            if expected_text:
                assert expected_text in actual_text, (
                    f"{section_id} 文字抽查缺失：{expected_text[:40]}"
                )

        expected_images = [
            f"../assets/images/{block['src']}"
            for block in segmented[section_id]
            if block["type"] == "image"
        ]
        assert parser.images == expected_images, (
            f"{section_id} 图片顺序不一致："
            f"{len(parser.images)}/{len(expected_images)}"
        )
        checked.append(section_id)

    return checked


def validate_required_paths() -> dict:
    index_source = (SITE_DIR / "index.html").read_text(encoding="utf-8")
    beginner_source = (CHAPTER_DIR / "01-02.html").read_text(encoding="utf-8")
    longest_source = (CHAPTER_DIR / "04-01.html").read_text(encoding="utf-8")
    css_source = (SITE_DIR / "assets" / "css" / "style.css").read_text(
        encoding="utf-8"
    )
    js_source = (JS_DIR / "main.js").read_text(encoding="utf-8")
    search_source = (JS_DIR / "search-index.js").read_text(encoding="utf-8")

    assert 'href="chapters/01-02.html"' in index_source
    assert 'href="01-03.html"' in beginner_source
    assert 'href="#step-3"' in longest_source
    assert 'id="step-3"' in longest_source
    assert "@media (max-width: 768px)" in css_source
    assert "sidebar-open" in css_source and "sidebar-open" in js_source
    assert "lightbox-open" in js_source
    assert "window.SEARCH_INDEX=" in search_source
    assert "fetch(" not in js_source and "fetch(" not in search_source

    return {
        "beginner_route": "pass",
        "longest_chapter_route": "pass",
        "mobile_drawer_hooks": "pass",
        "lightbox_hooks": "pass",
        "file_protocol_search": "pass",
    }


def validate_site(
    expected_chapter_pages: int,
    sections: list[dict],
    segmented: dict[str, list[dict]],
) -> dict:
    html_files = sorted(SITE_DIR.rglob("*.html"))
    image_files = sorted(path for path in IMAGE_DIR.iterdir() if path.is_file())
    missing_images: list[str] = []
    broken_links: list[str] = []
    missing_resources: list[str] = []
    image_references = 0

    parsed_pages: dict[Path, ReferenceParser] = {}
    for html_path in html_files:
        source = html_path.read_text(encoding="utf-8")
        assert 'src=""' not in source, f"发现空 src：{html_path}"
        parser = ReferenceParser()
        parser.feed(source)
        parsed_pages[html_path.resolve()] = parser
        image_references += len(parser.images)

        for image_ref in parser.images:
            target, _ = resolve_local_reference(html_path, image_ref)
            if not target.is_file():
                missing_images.append(f"{html_path.name}: {image_ref}")

        for resource_ref in parser.resources:
            parsed = urlsplit(resource_ref)
            if parsed.scheme or parsed.netloc:
                missing_resources.append(f"外部资源：{resource_ref}")
                continue
            target, _ = resolve_local_reference(html_path, resource_ref)
            if not target.is_file():
                missing_resources.append(f"{html_path.name}: {resource_ref}")

        for link_ref in parser.links:
            parsed = urlsplit(link_ref)
            if parsed.scheme or parsed.netloc:
                continue
            target, fragment = resolve_local_reference(html_path, link_ref)
            if not target.is_file():
                broken_links.append(f"{html_path.name}: {link_ref}")
                continue
            if fragment and target.suffix.lower() == ".html":
                target_parser = parsed_pages.get(target)
                if target == html_path.resolve():
                    target_parser = parser
                if target_parser is None:
                    target_source = target.read_text(encoding="utf-8")
                    target_parser = ReferenceParser()
                    target_parser.feed(target_source)
                    parsed_pages[target] = target_parser
                if fragment not in target_parser.ids:
                    broken_links.append(f"{html_path.name}: {link_ref}（锚点缺失）")

    chapter_pages = list(CHAPTER_DIR.glob("*.html"))
    assert len(chapter_pages) == expected_chapter_pages, (
        f"章节 HTML 数应为 {expected_chapter_pages}，实际为 {len(chapter_pages)}"
    )
    assert len(html_files) == expected_chapter_pages + 1, (
        f"HTML 总数应为 {expected_chapter_pages + 1}，实际为 {len(html_files)}"
    )
    assert not missing_images, f"缺失图片：{missing_images[:5]}"
    assert not broken_links, f"失效链接：{broken_links[:5]}"
    assert not missing_resources, f"资源引用异常：{missing_resources[:5]}"

    report = {
        "html_pages": len(html_files),
        "chapter_pages": len(chapter_pages),
        "image_references": image_references,
        "image_files": len(image_files),
        "missing_images": len(missing_images),
        "broken_links": len(broken_links),
        "missing_resources": len(missing_resources),
    }
    report.update(validate_required_paths())
    report["pdf_spot_checks"] = validate_pdf_spot_checks(sections, segmented)
    return report


def main() -> None:
    sections_data = load_json(SECTIONS_PATH)
    content_data = load_json(CONTENT_PATH)
    chapters = sections_data["chapters"]
    sections = sections_data["sections"]
    flattened_blocks = flatten_content(content_data)
    segmented = split_sections(sections, flattened_blocks)
    inline_icon_count = 0
    prepared_segments: dict[str, list[dict]] = {}
    for section in sections:
        prepared_blocks, embedded_count = embed_inline_icons(
            segmented[section["id"]]
        )
        prepared_segments[section["id"]] = prepared_blocks
        inline_icon_count += embedded_count
    segmented = prepared_segments

    CHAPTER_DIR.mkdir(parents=True, exist_ok=True)
    JS_DIR.mkdir(parents=True, exist_ok=True)
    for old_page in CHAPTER_DIR.glob("*.html"):
        old_page.unlink()

    subsection_warnings: list[dict] = []
    search_index: list[dict] = []
    for index, section in enumerate(sections):
        page_markup, found_subsections = build_chapter_page(
            chapters,
            sections,
            section,
            index,
            segmented[section["id"]],
        )
        (CHAPTER_DIR / f"{section['id']}.html").write_text(
            page_markup,
            encoding="utf-8",
        )

        expected_numbers = {
            int(item["number"]) for item in section.get("subsections", [])
        }
        missing_numbers = sorted(expected_numbers - found_subsections)
        if missing_numbers:
            subsection_warnings.append(
                {"section": section["id"], "missing": missing_numbers}
            )

        search_text = " ".join(
            INLINE_ICON_TOKEN_RE.sub("图标", join_pdf_lines(block["text"]))
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

    image_count = len([path for path in IMAGE_DIR.iterdir() if path.is_file()])
    (SITE_DIR / "index.html").write_text(
        build_index(chapters, image_count),
        encoding="utf-8",
    )
    (JS_DIR / "search-index.js").write_text(
        "window.SEARCH_INDEX="
        + json.dumps(search_index, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )

    assert len(search_index) == len(sections)
    assert any("直播" in item["text"] for item in search_index), (
        "搜索索引无法命中“直播”"
    )

    report = validate_site(len(sections), sections, segmented)
    report["search_entries"] = len(search_index)
    report["inline_icons"] = sum(
        path.read_text(encoding="utf-8").count('class="inline-icon"')
        for path in CHAPTER_DIR.glob("*.html")
    )
    assert report["inline_icons"] == inline_icon_count, (
        f"行内图标数量异常：{report['inline_icons']}/{inline_icon_count}"
    )
    report["subsection_warnings"] = subsection_warnings
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        "站点构建与断言检查完成："
        f"页面数={report['html_pages']}，"
        f"章节页={report['chapter_pages']}，"
        f"图片引用={report['image_references']}，"
        f"图片文件={report['image_files']}，"
        f"缺失数={report['missing_images']}，"
        f"失效链接={report['broken_links']}"
    )
    if subsection_warnings:
        print(f"小节标题识别警告：{len(subsection_warnings)} 节，见 {REPORT_PATH}")
    else:
        print("小节标题识别：全部通过")
    print(f"站点输出：{SITE_DIR}")


if __name__ == "__main__":
    main()
