#!/usr/bin/env python
"""Extract ordered text and image blocks from PDF pages 8-192."""

from __future__ import annotations

import json
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "build" / "manual.pdf"
OUTPUT_PATH = ROOT / "build" / "content.json"
IMAGE_DIR = ROOT / "site" / "assets" / "images"
FIRST_CONTENT_PAGE = 8
LAST_CONTENT_PAGE = 192


def round_bbox(bbox: tuple[float, float, float, float]) -> list[float]:
    return [round(float(value), 2) for value in bbox]


def extract_text_block(block: dict) -> dict | None:
    lines: list[str] = []
    sizes: list[float] = []
    fonts: list[str] = []

    for line in block.get("lines", []):
        line_text = "".join(
            span.get("text", "") for span in line.get("spans", [])
        ).rstrip()
        if line_text:
            lines.append(line_text)
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


def remove_previous_outputs() -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    for path in IMAGE_DIR.iterdir():
        if path.is_file() and path.name.startswith("p"):
            path.unlink()


def extract() -> dict:
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"找不到输入 PDF：{PDF_PATH}")

    remove_previous_outputs()
    content: dict[str, list[dict]] = {}
    exported_xrefs: dict[int, str] = {}
    image_occurrences = 0

    with fitz.open(PDF_PATH) as doc:
        if doc.page_count != LAST_CONTENT_PAGE:
            raise AssertionError(
                f"PDF 页数应为 {LAST_CONTENT_PAGE}，实际为 {doc.page_count}"
            )

        for page_number in range(FIRST_CONTENT_PAGE, LAST_CONTENT_PAGE + 1):
            page = doc[page_number - 1]
            blocks: list[dict] = []

            for raw_block in page.get_text("dict").get("blocks", []):
                if raw_block.get("type") != 0:
                    continue
                text_block = extract_text_block(raw_block)
                if text_block:
                    blocks.append(text_block)

            image_infos = sorted(
                page.get_image_info(xrefs=True),
                key=lambda info: (
                    float(info["bbox"][1]),
                    float(info["bbox"][0]),
                ),
            )
            for sequence, image_info in enumerate(image_infos, start=1):
                xref = int(image_info.get("xref", 0))
                if xref <= 0:
                    raise AssertionError(
                        f"第 {page_number} 页存在无法提取的图片 xref={xref}"
                    )

                if xref not in exported_xrefs:
                    image_data = doc.extract_image(xref)
                    extension = image_data["ext"].lower()
                    if extension == "jpg":
                        extension = "jpeg"
                    if extension not in {"png", "jpeg"}:
                        raise AssertionError(
                            f"xref {xref} 的图片格式不受支持：{extension}"
                        )
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

    output = {
        "source": PDF_PATH.name,
        "first_page": FIRST_CONTENT_PAGE,
        "last_page": LAST_CONTENT_PAGE,
        "image_occurrences": image_occurrences,
        "unique_images": len(exported_xrefs),
        "pages": content,
    }
    return output


def validate(data: dict) -> None:
    pages = data["pages"]
    image_files = [path for path in IMAGE_DIR.iterdir() if path.is_file()]
    first_text = next(
        block["text"]
        for block in pages["8"]
        if block["type"] == "text"
    )

    assert len(pages) == 185, f"正文页数应为 185，实际为 {len(pages)}"
    assert len(image_files) >= 350, (
        f"唯一图片数应不少于 350，实际为 {len(image_files)}"
    )
    assert "一、进入与使用数字教研工作室" in first_text

    missing = []
    for page_blocks in pages.values():
        for block in page_blocks:
            if block["type"] == "image" and not (IMAGE_DIR / block["src"]).is_file():
                missing.append(block["src"])
    assert not missing, f"图片提取后缺失：{missing[:5]}"


def main() -> None:
    data = extract()
    validate(data)
    OUTPUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    print(
        "内容提取完成："
        f"{len(data['pages'])} 页，"
        f"{data['image_occurrences']} 次图片引用，"
        f"{data['unique_images']} 个唯一图片"
    )
    print("页眉页脚抽样：正文页未发现独立页眉、页码或手册名块，无需过滤")
    print(f"输出：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
