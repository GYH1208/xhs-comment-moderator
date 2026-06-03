# Local Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Flask web UI where non-technical coworkers paste one Xiaohongshu post URL, guide browser login/confirmation, collect visible comments, and review risky comments.

**Architecture:** Keep existing moderation logic in `xhs_comment_moderator.py`. Add reusable browser session helpers to `xhs_browser_collect.py`, then build a small Flask app in `xhs_ui_app.py` with background job state persisted under `xhs_ui_data/`.

**Tech Stack:** Python 3, Flask, Playwright, existing local rule classifier, HTML/CSS/vanilla JavaScript.

---

### Task 1: Make Browser Collection Reusable

**Files:**
- Modify: `xhs_browser_collect.py`

- [ ] Extract the Playwright scrolling/extraction loop into reusable functions that accept a page and settings.
- [ ] Keep the existing CLI behavior working.
- [ ] Add a browser session class with `open()`, `collect()`, and `close()` methods so the Flask app can wait for a web button before collecting.
- [ ] Verify with `python3 -m py_compile xhs_browser_collect.py`.

### Task 2: Add Local Web App Backend

**Files:**
- Create: `xhs_ui_app.py`
- Modify: `requirements.txt`

- [ ] Add `flask>=2.2.0` to dependencies.
- [ ] Create a Flask app with routes for home, start job, job status JSON, continue collection, result page, report download, and history.
- [ ] Store job metadata in `xhs_ui_data/jobs/<job_id>/job.json`.
- [ ] Run browser collection in a background thread and expose simple job states: `opening`, `waiting`, `collecting`, `reviewing`, `done`, `error`.
- [ ] Verify with `python3 -m py_compile xhs_ui_app.py`.

### Task 3: Add Templates and Styling

**Files:**
- Create: `templates/base.html`
- Create: `templates/index.html`
- Create: `templates/job.html`
- Create: `templates/result.html`
- Create: `templates/history.html`
- Create: `static/xhs_ui.css`
- Create: `static/xhs_ui.js`

- [ ] Build a calm, task-focused UI with a single URL input on the home page.
- [ ] Show status steps and a continue button on the job page.
- [ ] Show risky comments first on the result page, with clean/feedback comments collapsed lower on the page.
- [ ] Add status polling JavaScript for the job page.
- [ ] Keep all text readable on mobile and desktop.

### Task 4: Add Verification Coverage

**Files:**
- Create: `tests/test_xhs_ui_app.py`

- [ ] Test home route loads.
- [ ] Test invalid URL submission is rejected.
- [ ] Test result rendering works from a saved finished job.
- [ ] Test job serialization keeps rows and counts consistent.
- [ ] Run `python3 -m unittest discover -s tests`.

### Task 5: Update Documentation and Smoke Test

**Files:**
- Modify: `README.md`

- [ ] Add first-version local UI startup instructions.
- [ ] Document the user workflow: paste URL, handle browser login, continue, review results.
- [ ] Run `python3 xhs_comment_moderator.py sample_xhs_comments.csv -o /tmp/xhs_sample_report.csv`.
- [ ] Run `python3 -m unittest discover -s tests`.
- [ ] Start the app with `python3 xhs_ui_app.py` and verify it serves locally.
