#!/usr/bin/env python3
"""Convert Xiaohongshu comment screenshots to a CSV for moderation.

The script is intentionally local-first. It supports:
1. Tesseract through the `pytesseract` Python package, when available.
2. The `tesseract` command line executable, when available.

It does not call Xiaohongshu private APIs, log in, or scrape the app.
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass
class OcrResult:
    image: Path
    text: str
    engine: str


def collect_images(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported image file: {input_path}")
        return [input_path]

    if input_path.is_dir():
        images = [
            path
            for path in sorted(input_path.iterdir())
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ]
        if not images:
            raise ValueError(f"No supported image files found in: {input_path}")
        return images

    raise FileNotFoundError(input_path)


def run_pytesseract(image: Path, lang: str) -> str | None:
    try:
        from PIL import Image, ImageFilter, ImageOps
        import pytesseract
    except ImportError:
        return None

    with Image.open(image) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("L")
        img = ImageOps.autocontrast(img)
        img = img.filter(ImageFilter.SHARPEN)
        config = "--psm 6"
        return pytesseract.image_to_string(img, lang=lang, config=config)


def run_tesseract_cli(image: Path, lang: str) -> str | None:
    with tempfile.TemporaryDirectory() as tmpdir:
        out_base = Path(tmpdir) / "ocr"
        command = ["tesseract", str(image), str(out_base), "-l", lang, "--psm", "6"]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except FileNotFoundError:
            return None

        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"Tesseract failed for {image}: {message}")

        output_file = out_base.with_suffix(".txt")
        return output_file.read_text(encoding="utf-8", errors="replace")


def ocr_image(image: Path, lang: str) -> OcrResult:
    text = run_pytesseract(image, lang)
    if text is not None:
        return OcrResult(image=image, text=text, engine="pytesseract")

    text = run_tesseract_cli(image, lang)
    if text is not None:
        return OcrResult(image=image, text=text, engine="tesseract-cli")

    raise RuntimeError(
        "No OCR engine found. Install Tesseract OCR and Chinese language data, "
        "or install Python packages: pillow pytesseract."
    )


def normalize_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    line = line.strip("|·•。")
    return line


def looks_like_ui_noise(line: str) -> bool:
    if not line:
        return True
    compact = re.sub(r"\s+", "", line)
    noise_exact = {
        "评论",
        "回复",
        "赞",
        "点赞",
        "展开",
        "查看更多",
        "说点什么",
        "发送",
        "作者赞过",
    }
    if compact in noise_exact:
        return True
    if re.fullmatch(r"\d+", compact):
        return True
    if re.fullmatch(r"\d+[分钟前小时天周月年]*", compact):
        return True
    if len(compact) <= 1:
        return True
    return False


def split_comments(raw_text: str, min_length: int) -> list[str]:
    lines = [normalize_line(line) for line in raw_text.splitlines()]
    lines = [line for line in lines if not looks_like_ui_noise(line)]

    comments: list[str] = []
    buffer: list[str] = []

    for line in lines:
        starts_new_comment = bool(
            re.match(r"^(@?[\w\u4e00-\u9fff.-]{2,20})[:：]\s*(.+)", line)
        )
        if starts_new_comment and buffer:
            comments.append(" ".join(buffer).strip())
            buffer = [line]
        else:
            buffer.append(line)

    if buffer:
        comments.append(" ".join(buffer).strip())

    cleaned = []
    seen = set()
    for comment in comments:
        comment = re.sub(r"\s+", " ", comment).strip()
        if len(comment) < min_length or comment in seen:
            continue
        cleaned.append(comment)
        seen.add(comment)
    return cleaned


def write_comments_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file, fieldnames=["source_image", "comment_index", "comment"]
        )
        writer.writeheader()
        writer.writerows(rows)


def write_raw_text(path: Path, results: list[OcrResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks = []
    for result in results:
        chunks.append(f"===== {result.image.name} ({result.engine}) =====\n{result.text.strip()}")
    path.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OCR Xiaohongshu comment screenshots into a comments CSV."
    )
    parser.add_argument("input", type=Path, help="Image file or folder of screenshots.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("xhs_ocr_comments.csv"),
        help="Output CSV path.",
    )
    parser.add_argument(
        "--raw-output",
        type=Path,
        default=Path("xhs_ocr_raw.txt"),
        help="Raw OCR text output path.",
    )
    parser.add_argument(
        "--lang",
        default="chi_sim+eng",
        help="Tesseract language pack. Defaults to chi_sim+eng.",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=4,
        help="Minimum comment length after OCR cleanup.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    images = collect_images(args.input)

    results = []
    rows: list[dict[str, str]] = []
    for image in images:
        result = ocr_image(image, args.lang)
        results.append(result)
        comments = split_comments(result.text, args.min_length)
        for index, comment in enumerate(comments, start=1):
            rows.append(
                {
                    "source_image": image.name,
                    "comment_index": str(index),
                    "comment": comment,
                }
            )

    write_comments_csv(args.output, rows)
    write_raw_text(args.raw_output, results)

    print(f"OCR 完成: {len(images)} 张图片")
    print(f"提取评论: {len(rows)} 条")
    print(f"评论 CSV: {args.output}")
    print(f"原始文本: {args.raw_output}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)
