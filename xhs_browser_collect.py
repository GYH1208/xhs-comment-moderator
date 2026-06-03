#!/usr/bin/env python3
"""Collect visible Xiaohongshu web comments with browser automation.

This uses Playwright to open a normal browser page, scroll, and read text that
is already visible in the web UI. It does not call private Xiaohongshu APIs,
does not bypass login, and does not solve captchas.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path


COMMENT_SELECTORS = [
    "[class*='comment']",
    "[id*='comment']",
    "[data-testid*='comment']",
    ".parent-comment",
    ".comment-item",
    ".comment-item-container",
    ".comment-list",
]


@dataclass
class BrowserCollectionSettings:
    url: str
    profile_dir: Path = Path(".xhs_browser_profile")
    screenshot_dir: Path = Path("xhs_browser_screenshots")
    scrolls: int = 20
    pause_ms: int = 1200
    scroll_pixels: int = 900
    screenshot_every: int = 5
    timeout_ms: int = 60000
    width: int = 1280
    height: int = 900
    headless: bool = False


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip("|·•")


def looks_like_noise(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 4:
        return True
    noise = {
        "评论",
        "回复",
        "点赞",
        "赞",
        "收藏",
        "分享",
        "关注",
        "展开",
        "收起",
        "查看更多",
        "说点什么",
        "发送",
        "作者赞过",
    }
    if compact in noise:
        return True
    if re.fullmatch(r"\d+[分钟前小时天周月年]*", compact):
        return True
    if re.fullmatch(r"\d+", compact):
        return True
    return False


def extract_comment_candidates(raw_texts: list[str]) -> list[str]:
    candidates: list[str] = []
    seen = set()

    for raw_text in raw_texts:
        lines = [normalize_text(line) for line in raw_text.splitlines()]
        lines = [line for line in lines if not looks_like_noise(line)]

        # Comment containers often include username, body, reply, like count.
        # Keep the longest meaningful line as the best local candidate.
        meaningful = [
            line
            for line in lines
            if len(re.sub(r"\s+", "", line)) >= 4
            and not re.search(r"^(回复|赞|点赞|展开|收起|查看更多)", line)
        ]
        if not meaningful:
            continue

        best = max(meaningful, key=len)
        best = normalize_text(best)
        if best and best not in seen:
            seen.add(best)
            candidates.append(best)

    return candidates


def write_csv(path: Path, comments: list[str], url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["url", "comment_index", "comment"])
        writer.writeheader()
        for index, comment in enumerate(comments, start=1):
            writer.writerow({"url": url, "comment_index": index, "comment": comment})


def read_visible_comment_texts(page: object) -> list[str]:
    selector_script = """
    (selectors) => {
      const visible = (el) => {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style && style.visibility !== 'hidden' &&
          style.display !== 'none' && rect.width > 0 && rect.height > 0;
      };
      const nodes = [];
      for (const selector of selectors) {
        document.querySelectorAll(selector).forEach((el) => {
          if (visible(el)) nodes.push(el.innerText || el.textContent || '');
        });
      }
      if (nodes.length === 0) {
        nodes.push(document.body.innerText || '');
      }
      return nodes;
    }
    """
    return page.evaluate(selector_script, COMMENT_SELECTORS)


def collect_from_open_page(page: object, settings: BrowserCollectionSettings) -> list[str]:
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    all_raw_texts: list[str] = []

    for step in range(settings.scrolls + 1):
        page.wait_for_timeout(settings.pause_ms)
        raw_texts = read_visible_comment_texts(page)
        all_raw_texts.extend(raw_texts)

        if step in {0, settings.scrolls} or step % settings.screenshot_every == 0:
            page.screenshot(
                path=str(settings.screenshot_dir / f"xhs_browser_step_{step:03d}.png"),
                full_page=False,
            )

        page.mouse.wheel(0, settings.scroll_pixels)

    return extract_comment_candidates(all_raw_texts)


class BrowserCollector:
    def __init__(self, settings: BrowserCollectionSettings) -> None:
        self.settings = settings
        self._playwright = None
        self._context = None
        self._page = None

    def open(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "缺少 Python Playwright。请先运行: pip install playwright && python -m playwright install chromium"
            ) from exc

        profile_dir = self.settings.profile_dir.resolve()
        self.settings.screenshot_dir = self.settings.screenshot_dir.resolve()
        self.settings.screenshot_dir.mkdir(parents=True, exist_ok=True)

        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=self.settings.headless,
            viewport={"width": self.settings.width, "height": self.settings.height},
            locale="zh-CN",
        )
        self._page = self._context.new_page()
        self._page.goto(
            self.settings.url,
            wait_until="domcontentloaded",
            timeout=self.settings.timeout_ms,
        )

    def collect(self) -> list[str]:
        if self._page is None:
            raise RuntimeError("浏览器还没有打开。")
        return collect_from_open_page(self._page, self.settings)

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self._page = None


def settings_from_args(args: argparse.Namespace) -> BrowserCollectionSettings:
    return BrowserCollectionSettings(
        url=args.url,
        profile_dir=args.profile_dir,
        screenshot_dir=args.screenshot_dir,
        scrolls=args.scrolls,
        pause_ms=args.pause_ms,
        scroll_pixels=args.scroll_pixels,
        screenshot_every=args.screenshot_every,
        timeout_ms=args.timeout_ms,
        width=args.width,
        height=args.height,
        headless=args.headless,
    )


def collect_comments(args: argparse.Namespace) -> list[str]:
    collector = BrowserCollector(settings_from_args(args))
    try:
        collector.open()

        if args.wait_for_enter:
            print("浏览器已打开。请在浏览器里登录/确认页面，并打开到评论区。")
            input("准备好后回到这个终端按 Enter 开始采集...")
        elif args.manual_wait > 0:
            print(f"浏览器已打开。请手动登录/确认页面，等待 {args.manual_wait} 秒...")
            remaining = args.manual_wait
            while remaining > 0:
                step = min(5, remaining)
                time.sleep(step)
                remaining -= step
                if remaining > 0:
                    print(f"还剩 {remaining} 秒开始采集...")

        return collector.collect()
    finally:
        collector.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open a Xiaohongshu post in a browser and collect visible comments."
    )
    parser.add_argument("url", help="Xiaohongshu post URL.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("xhs_browser_comments.csv"),
        help="Output comments CSV path.",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path(".xhs_browser_profile"),
        help="Persistent browser profile for login/session reuse.",
    )
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        default=Path("xhs_browser_screenshots"),
        help="Screenshots saved during scrolling; can be OCR fallback input.",
    )
    parser.add_argument("--scrolls", type=int, default=20, help="Number of scroll steps.")
    parser.add_argument("--pause-ms", type=int, default=1200, help="Wait after each scroll.")
    parser.add_argument("--scroll-pixels", type=int, default=900, help="Pixels per scroll.")
    parser.add_argument(
        "--manual-wait",
        type=int,
        default=45,
        help="Seconds to wait for manual login/page confirmation.",
    )
    parser.add_argument(
        "--wait-for-enter",
        action="store_true",
        help="Wait until you press Enter before scrolling and collecting comments.",
    )
    parser.add_argument("--screenshot-every", type=int, default=5)
    parser.add_argument("--timeout-ms", type=int, default=60000)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--headless", action="store_true", help="Run without visible browser.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        comments = collect_comments(args)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)

    write_csv(args.output, comments, args.url)
    print(f"浏览器采集完成，提取 {len(comments)} 条候选评论")
    print(f"评论 CSV: {args.output}")
    print(f"截图目录: {args.screenshot_dir}")
    if not comments:
        print("没有提取到评论。可以把截图目录交给 OCR 脚本继续处理。")


if __name__ == "__main__":
    main()
