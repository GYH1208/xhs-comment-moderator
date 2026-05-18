#!/usr/bin/env python3
"""Monitor Xiaohongshu post comment sources and flag new risky comments.

This monitor deliberately avoids private Xiaohongshu APIs. Each post points to
an approved local source:
- a CSV/JSON/TXT comment file
- a folder of screenshots, processed through local OCR when available
- a single screenshot image

The script remembers comments it has already seen and writes reports for new
comments only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import xhs_comment_moderator as moderator

try:
    import xhs_ocr_to_comments as ocr
except Exception:  # pragma: no cover - OCR is optional at runtime.
    ocr = None


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def stable_hash(post_name: str, text: str, author: str = "") -> str:
    normalized = " ".join(text.split()).strip().lower()
    key = f"{post_name}\n{author.strip().lower()}\n{normalized}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def source_is_image_source(path: Path) -> bool:
    if path.is_file():
        return path.suffix.lower() in IMAGE_EXTENSIONS
    if path.is_dir():
        return any(child.suffix.lower() in IMAGE_EXTENSIONS for child in path.iterdir())
    return False


def load_comments_from_source(post: dict[str, Any], output_dir: Path) -> list[moderator.Comment]:
    source = Path(post["source"])
    if not source.is_absolute():
        source = Path.cwd() / source

    if source_is_image_source(source):
        if ocr is None:
            raise RuntimeError("OCR module is unavailable.")
        images = ocr.collect_images(source)
        comments: list[moderator.Comment] = []
        raw_chunks = []
        index = 1
        for image in images:
            result = ocr.ocr_image(image, str(post.get("ocr_lang", "chi_sim+eng")))
            raw_chunks.append(
                f"===== {image.name} ({result.engine}) =====\n{result.text.strip()}"
            )
            for text in ocr.split_comments(result.text, int(post.get("min_length", 4))):
                comments.append(
                    moderator.Comment(
                        index=index,
                        text=text,
                        author="",
                        url=str(post.get("url", "")),
                        raw={"source_image": image.name},
                    )
                )
                index += 1

        raw_path = output_dir / f"{post['name']}_latest_ocr_raw.txt"
        raw_path.write_text("\n\n".join(raw_chunks) + "\n", encoding="utf-8")
        return comments

    return moderator.load_comments(source)


def write_report(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "index",
        "post",
        "post_url",
        "first_seen",
        "risk_level",
        "score",
        "categories",
        "action",
        "reasons",
        "author",
        "time",
        "url",
        "comment",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def scan_once(config: dict[str, Any], state: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    output_dir = Path(config.get("output_dir", "xhs_monitor_reports"))
    seen = state.setdefault("seen", {})
    all_new_rows: list[dict[str, Any]] = []
    now = datetime.now().isoformat(timespec="seconds")

    for post in config.get("posts", []):
        name = str(post["name"])
        post_seen = seen.setdefault(name, {})
        comments = load_comments_from_source(post, output_dir)

        new_comments = []
        for comment in comments:
            comment_hash = stable_hash(name, comment.text, comment.author)
            if comment_hash in post_seen:
                continue
            post_seen[comment_hash] = {
                "first_seen": now,
                "text": comment.text,
                "author": comment.author,
            }
            new_comments.append(comment)

        rows = moderator.build_rows(new_comments)
        for row in rows:
            row["post"] = name
            row["post_url"] = str(post.get("url", ""))
            row["first_seen"] = now
            if not row["url"]:
                row["url"] = str(post.get("url", ""))
            all_new_rows.append(row)

        print(f"{name}: 总评论 {len(comments)}，新增 {len(new_comments)}")

    state["last_scan"] = now
    return state, all_new_rows


def print_alerts(rows: list[dict[str, Any]]) -> None:
    risky = [
        row
        for row in rows
        if row["risk_level"] in {"critical", "high", "medium", "low"}
    ]
    if not risky:
        print("本轮没有新增风险评论。")
        return

    priority = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    risky.sort(key=lambda row: (priority[row["risk_level"]], row["post"], row["comment"]))
    print("\n新增风险评论：")
    for row in risky[:20]:
        preview = row["comment"][:70] + ("..." if len(row["comment"]) > 70 else "")
        print(f"[{row['risk_level']}] {row['post']} - {row['categories']} - {preview}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor local Xiaohongshu comment sources and report new risks."
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("xhs_monitor_config.example.json"),
        help="Monitor config JSON path.",
    )
    parser.add_argument("--once", action="store_true", help="Run one scan and exit.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_json(args.config, {})
    state_file = Path(config.get("state_file", "xhs_monitor_state.json"))
    if not state_file.is_absolute():
        state_file = Path.cwd() / state_file

    while True:
        state = load_json(state_file, {"seen": {}})
        state, rows = scan_once(config, state)

        output_dir = Path(config.get("output_dir", "xhs_monitor_reports"))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = output_dir / f"new_comments_{timestamp}.csv"
        write_report(report_path, rows)
        save_json(state_file, state)
        print_alerts(rows)
        print(f"本轮新增评论报告: {report_path}")

        if args.once:
            break
        interval = int(config.get("interval_seconds", 300))
        print(f"等待 {interval} 秒后继续监控...\n")
        time.sleep(interval)


if __name__ == "__main__":
    main()
