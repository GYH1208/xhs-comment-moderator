#!/usr/bin/env python3
"""Local web UI for Xiaohongshu comment moderation."""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

import xhs_browser_collect as browser_collect
import xhs_comment_moderator as moderator


DATA_DIR = Path("xhs_ui_data")
JOBS_DIR = DATA_DIR / "jobs"
SETTINGS_PATH = DATA_DIR / "settings.json"
PROFILE_DIR = Path(".xhs_browser_profile")
RISK_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "feedback": 4, "clean": 5}
RISKY_LEVELS = {"critical", "high", "medium", "low"}
LLM_MODES = {"all", "uncertain", "risky"}
COLLECTION_INTENSITIES = {"standard", "deep"}
DEFAULT_MODEL_SETTINGS = {
    "enabled": True,
    "api_key": "",
    "model": "gpt-4o-mini",
    "base_url": "https://api.openai.com/v1",
    "llm_mode": "all",
    "max_llm_comments": 0,
    "collection_intensity": "standard",
}

app = Flask(__name__)
app.secret_key = "xhs-local-ui"

_job_events: dict[str, threading.Event] = {}
_job_threads: dict[str, threading.Thread] = {}
_job_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def valid_xhs_url(url: str) -> bool:
    return bool(
        re.match(r"^https?://", url)
        and ("xiaohongshu.com" in url or "xhslink.com" in url)
    )


def job_dir(job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        abort(404)
    return JOBS_DIR / job_id


def job_json_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.json"


def rows_json_path(job_id: str) -> Path:
    return job_dir(job_id) / "rows.json"


def report_path(job_id: str) -> Path:
    return job_dir(job_id) / "report.csv"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def load_model_settings() -> dict[str, Any]:
    saved = load_json(SETTINGS_PATH, {})
    if not isinstance(saved, dict):
        saved = {}
    settings = dict(DEFAULT_MODEL_SETTINGS)
    settings.update({key: saved[key] for key in settings.keys() if key in saved})
    if settings["llm_mode"] not in LLM_MODES:
        settings["llm_mode"] = DEFAULT_MODEL_SETTINGS["llm_mode"]
    if settings["collection_intensity"] not in COLLECTION_INTENSITIES:
        settings["collection_intensity"] = DEFAULT_MODEL_SETTINGS["collection_intensity"]
    try:
        settings["max_llm_comments"] = int(settings["max_llm_comments"])
    except (TypeError, ValueError):
        settings["max_llm_comments"] = DEFAULT_MODEL_SETTINGS["max_llm_comments"]
    if settings["max_llm_comments"] < 0:
        settings["max_llm_comments"] = 0
    settings["enabled"] = bool(settings["enabled"])
    return settings


def mask_api_key(api_key: str) -> str:
    if not api_key:
        return "未设置"
    if len(api_key) <= 8:
        return "****"
    return f"{api_key[:3]}****{api_key[-4:]}"


def parse_model_settings_form(form: Any, current: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    llm_mode = form.get("llm_mode", DEFAULT_MODEL_SETTINGS["llm_mode"]).strip()
    if llm_mode not in LLM_MODES:
        return current, "复核范围无效。"

    collection_intensity = form.get(
        "collection_intensity",
        DEFAULT_MODEL_SETTINGS["collection_intensity"],
    ).strip()
    if collection_intensity not in COLLECTION_INTENSITIES:
        return current, "采集强度无效。"

    base_url = form.get("base_url", DEFAULT_MODEL_SETTINGS["base_url"]).strip().rstrip("/")
    if not re.match(r"^https?://", base_url):
        return current, "Base URL 需要以 http:// 或 https:// 开头。"

    try:
        max_llm_comments = int(form.get("max_llm_comments", DEFAULT_MODEL_SETTINGS["max_llm_comments"]))
    except (TypeError, ValueError):
        return current, "最大复核条数必须是数字。"
    if max_llm_comments < 0:
        return current, "最大复核条数不能小于 0。"

    api_key = form.get("api_key", "").strip() or str(current.get("api_key", ""))
    settings = {
        "enabled": form.get("enabled") == "on",
        "api_key": api_key,
        "model": form.get("model", DEFAULT_MODEL_SETTINGS["model"]).strip()
        or DEFAULT_MODEL_SETTINGS["model"],
        "base_url": base_url,
        "llm_mode": llm_mode,
        "max_llm_comments": max_llm_comments,
        "collection_intensity": collection_intensity,
    }
    if settings["enabled"] and not settings["api_key"]:
        return current, "启用模型复核前需要填写 API Key。"
    return settings, None


def save_model_settings(settings: dict[str, Any]) -> None:
    save_json(SETTINGS_PATH, settings)


def model_status_label(settings: dict[str, Any]) -> str:
    if settings.get("enabled") and settings.get("api_key"):
        return f"强制模型复核：{settings.get('model')}"
    if settings.get("enabled"):
        return "强制模型复核：缺少 API Key"
    return "仅使用本地规则"


def build_llm_moderator(settings: dict[str, Any]) -> moderator.LlmModerator | None:
    if not settings.get("enabled") or not settings.get("api_key"):
        return None
    return moderator.LlmModerator(
        api_key=str(settings["api_key"]),
        model=str(settings["model"]),
        base_url=str(settings["base_url"]),
    )


def force_model_review_enabled(settings: dict[str, Any]) -> bool:
    return bool(settings.get("enabled"))


def max_llm_comments_value(settings: dict[str, Any]) -> int | None:
    value = int(settings.get("max_llm_comments", 0) or 0)
    return None if value == 0 else value


def collection_settings_for_job(url: str, job_id: str, settings: dict[str, Any]) -> browser_collect.BrowserCollectionSettings:
    browser_settings = browser_collect.BrowserCollectionSettings(
        url=url,
        profile_dir=PROFILE_DIR,
        screenshot_dir=job_dir(job_id) / "screenshots",
    )
    if settings.get("collection_intensity") == "deep":
        browser_settings.scrolls = 40
        browser_settings.pause_ms = 1500
        browser_settings.scroll_pixels = 800
        browser_settings.screenshot_every = 8
    return browser_settings


def load_job(job_id: str) -> dict[str, Any]:
    job = load_json(job_json_path(job_id), None)
    if not isinstance(job, dict):
        abort(404)
    return job


def save_job(job: dict[str, Any]) -> None:
    job["updated_at"] = now_iso()
    save_json(job_json_path(job["id"]), job)


def update_job(job_id: str, **changes: Any) -> dict[str, Any]:
    with _job_lock:
        job = load_job(job_id)
        job.update(changes)
        save_job(job)
        return job


def count_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    risky_count = sum(1 for row in rows if row.get("risk_level") in RISKY_LEVELS)
    return {
        "comment_count": len(rows),
        "risky_count": risky_count,
        "clean_count": sum(1 for row in rows if row.get("risk_level") == "clean"),
        "feedback_count": sum(1 for row in rows if row.get("risk_level") == "feedback"),
    }


def sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            RISK_ORDER.get(str(row.get("risk_level", "clean")), 99),
            -int(row.get("score", 0) or 0),
            str(row.get("comment", "")),
        ),
    )


def classify_comments(
    comments: list[str],
    url: str,
    settings: dict[str, Any] | None = None,
    llm_factory: Any = build_llm_moderator,
) -> tuple[list[dict[str, Any]], str | None]:
    comment_objects = [
        moderator.Comment(index=index, text=text, url=url)
        for index, text in enumerate(comments, start=1)
    ]
    settings = settings or load_model_settings()
    llm_moderator = llm_factory(settings)
    if not llm_moderator:
        if force_model_review_enabled(settings):
            raise RuntimeError("强制模型复核已启用，请先配置模型 API Key。")
        return sort_rows(moderator.build_rows(comment_objects)), None

    try:
        rows = moderator.build_rows_with_options(
            comment_objects,
            llm_moderator=llm_moderator,
            llm_mode=str(settings["llm_mode"]),
            max_llm_comments=max_llm_comments_value(settings),
        )
        return sort_rows(rows), None
    except Exception as exc:
        if force_model_review_enabled(settings):
            raise RuntimeError(f"模型复核失败，未生成完整审核结论：{exc}") from exc
        rows = moderator.build_rows(comment_objects)
        return sort_rows(rows), f"模型复核失败，已使用本地规则生成结果：{exc}"


def create_job(url: str) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    path = JOBS_DIR / job_id
    path.mkdir(parents=True, exist_ok=True)
    job = {
        "id": job_id,
        "url": url,
        "status": "opening",
        "message": "正在打开小红书页面",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "comment_count": 0,
        "risky_count": 0,
        "clean_count": 0,
        "feedback_count": 0,
        "report_path": str(report_path(job_id)),
    }
    save_job(job)
    return job


def run_job(job_id: str) -> None:
    job = load_job(job_id)
    event = _job_events[job_id]
    model_settings = load_model_settings()
    browser_settings = collection_settings_for_job(job["url"], job_id, model_settings)
    collector = browser_collect.BrowserCollector(browser_settings)

    try:
        update_job(job_id, status="opening", message="正在打开小红书页面")
        collector.open()
        update_job(
            job_id,
            status="waiting",
            message="请在弹出的浏览器里登录或确认页面，并打开评论区，然后回到这里继续",
        )
        event.wait()
        update_job(job_id, status="collecting", message="正在滚动页面并采集可见评论")
        comments = collector.collect()

        update_job(job_id, status="reviewing", message="正在识别风险评论")
        rows, warning = classify_comments(comments, job["url"], settings=model_settings)
        counts = count_rows(rows)
        save_json(rows_json_path(job_id), rows)
        moderator.write_csv(report_path(job_id), rows)
        update_job(
            job_id,
            status="done",
            message="检测完成",
            model_status=model_status_label(model_settings),
            audit_complete=not warning,
            warning=warning or "",
            **counts,
        )
    except Exception as exc:
        update_job(job_id, status="error", message=str(exc), error=str(exc))
    finally:
        collector.close()


def start_background_job(job: dict[str, Any]) -> None:
    event = threading.Event()
    thread = threading.Thread(target=run_job, args=(job["id"],), daemon=True)
    with _job_lock:
        _job_events[job["id"]] = event
        _job_threads[job["id"]] = thread
    thread.start()


def list_jobs() -> list[dict[str, Any]]:
    jobs = []
    for path in JOBS_DIR.glob("*/job.json"):
        job = load_json(path, {})
        if isinstance(job, dict) and job.get("id"):
            jobs.append(job)
    return sorted(jobs, key=lambda item: str(item.get("created_at", "")), reverse=True)


def load_rows(job_id: str) -> list[dict[str, Any]]:
    rows = load_json(rows_json_path(job_id), [])
    if not isinstance(rows, list):
        return []
    return sort_rows([row for row in rows if isinstance(row, dict)])


@app.get("/")
def index() -> str:
    settings = load_model_settings()
    return render_template(
        "index.html",
        recent_jobs=list_jobs()[:5],
        model_status=model_status_label(settings),
    )


@app.post("/jobs")
def start_job() -> Any:
    url = request.form.get("url", "").strip()
    if not valid_xhs_url(url):
        flash("请输入有效的小红书帖子链接。")
        return redirect(url_for("index"))
    settings = load_model_settings()
    if force_model_review_enabled(settings) and not settings.get("api_key"):
        flash("请先配置模型 API Key，强制模型复核完成后才能开始全自动审核。")
        return redirect(url_for("model_settings_page"))

    job = create_job(url)
    start_background_job(job)
    return redirect(url_for("job_page", job_id=job["id"]))


@app.get("/jobs/<job_id>")
def job_page(job_id: str) -> str:
    return render_template("job.html", job=load_job(job_id))


@app.get("/jobs/<job_id>/status")
def job_status(job_id: str) -> Any:
    return jsonify(load_job(job_id))


@app.post("/jobs/<job_id>/continue")
def continue_job(job_id: str) -> Any:
    load_job(job_id)
    event = _job_events.get(job_id)
    if event is None:
        update_job(job_id, status="error", message="这个检测任务已经不在运行，请重新开始。")
    else:
        event.set()
    return redirect(url_for("job_page", job_id=job_id))


@app.get("/jobs/<job_id>/result")
def result(job_id: str) -> str:
    job = load_job(job_id)
    rows = load_rows(job_id)
    risky_rows = [row for row in rows if row.get("risk_level") in RISKY_LEVELS]
    other_rows = [row for row in rows if row.get("risk_level") not in RISKY_LEVELS]
    return render_template(
        "result.html",
        job=job,
        risky_rows=risky_rows,
        other_rows=other_rows,
    )


@app.get("/jobs/<job_id>/report.csv")
def download_report(job_id: str) -> Any:
    path = report_path(job_id)
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=f"xhs_report_{job_id}.csv")


@app.get("/history")
def history() -> str:
    return render_template("history.html", jobs=list_jobs())


@app.get("/settings/model")
def model_settings_page() -> str:
    settings = load_model_settings()
    return render_template(
        "settings.html",
        settings=settings,
        masked_api_key=mask_api_key(str(settings.get("api_key", ""))),
    )


@app.post("/settings/model")
def save_model_settings_page() -> Any:
    current = load_model_settings()
    settings, error = parse_model_settings_form(request.form, current)
    if error:
        flash(error)
        return redirect(url_for("model_settings_page"))
    save_model_settings(settings)
    flash("模型配置已保存。")
    return redirect(url_for("model_settings_page"))


@app.post("/settings/model/test")
def test_model_settings() -> Any:
    settings = load_model_settings()
    llm_moderator = build_llm_moderator(settings)
    if not llm_moderator:
        flash("请先启用模型复核并保存 API Key。")
        return redirect(url_for("model_settings_page"))

    try:
        comment = moderator.Comment(index=1, text="测试连接")
        decision = moderator.Decision(
            risk_level="clean",
            score=0,
            categories=["未命中"],
            action="无需处理",
            reasons=["连接测试"],
        )
        llm_moderator.review(comment, decision)
    except Exception as exc:
        flash(f"模型连接测试失败：{exc}")
    else:
        flash("模型连接测试成功。")
    return redirect(url_for("model_settings_page"))


if __name__ == "__main__":
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
