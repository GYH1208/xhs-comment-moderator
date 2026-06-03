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
PROFILE_DIR = Path(".xhs_browser_profile")
RISK_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "feedback": 4, "clean": 5}
RISKY_LEVELS = {"critical", "high", "medium", "low"}

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


def classify_comments(comments: list[str], url: str) -> list[dict[str, Any]]:
    comment_objects = [
        moderator.Comment(index=index, text=text, url=url)
        for index, text in enumerate(comments, start=1)
    ]
    return sort_rows(moderator.build_rows(comment_objects))


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
    settings = browser_collect.BrowserCollectionSettings(
        url=job["url"],
        profile_dir=PROFILE_DIR,
        screenshot_dir=job_dir(job_id) / "screenshots",
    )
    collector = browser_collect.BrowserCollector(settings)

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
        rows = classify_comments(comments, job["url"])
        counts = count_rows(rows)
        save_json(rows_json_path(job_id), rows)
        moderator.write_csv(report_path(job_id), rows)
        update_job(
            job_id,
            status="done",
            message="检测完成",
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
    return render_template("index.html", recent_jobs=list_jobs()[:5])


@app.post("/jobs")
def start_job() -> Any:
    url = request.form.get("url", "").strip()
    if not valid_xhs_url(url):
        flash("请输入有效的小红书帖子链接。")
        return redirect(url_for("index"))

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


if __name__ == "__main__":
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
