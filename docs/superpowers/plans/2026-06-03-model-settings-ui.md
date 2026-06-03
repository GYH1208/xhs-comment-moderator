# Model Settings UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local web UI model settings and use those settings during comment detection jobs.

**Architecture:** Store UI-specific settings in `xhs_ui_data/settings.json`. Add settings routes and templates to `xhs_ui_app.py`, then use configured `LlmModerator` during `classify_comments`.

**Tech Stack:** Python 3, Flask, unittest, existing DeepSeek-compatible moderation client.

---

### Task 1: Settings Model and Tests

**Files:**
- Modify: `xhs_ui_app.py`
- Modify: `tests/test_xhs_ui_app.py`

- [ ] Add failing tests for default settings, saving settings, API Key masking, and invalid review mode.
- [ ] Implement settings helper functions: defaults, load, save, mask, parse form.
- [ ] Run `python3 -m unittest discover -s tests`.

### Task 2: Settings Routes and UI

**Files:**
- Modify: `xhs_ui_app.py`
- Modify: `templates/base.html`
- Create: `templates/settings.html`
- Modify: `templates/index.html`
- Modify: `static/xhs_ui.css`

- [ ] Add GET/POST settings routes.
- [ ] Add connection test route.
- [ ] Add nav link and home status badge.
- [ ] Add settings form with clear labels and masked saved key.
- [ ] Run `python3 -m unittest discover -s tests`.

### Task 3: Use Settings During Jobs

**Files:**
- Modify: `xhs_ui_app.py`
- Modify: `templates/result.html`
- Modify: `tests/test_xhs_ui_app.py`

- [ ] Add failing tests for model-enabled classification and model failure fallback.
- [ ] Update `classify_comments` to accept settings and call `build_rows_with_options`.
- [ ] Store job warning and model state in job metadata.
- [ ] Show model warning on result page.
- [ ] Run `python3 -m unittest discover -s tests`.

### Task 4: Documentation and Final Verification

**Files:**
- Modify: `README.md`

- [ ] Document model settings from the web UI.
- [ ] Run `python3 -m py_compile xhs_ui_app.py xhs_browser_collect.py xhs_comment_moderator.py`.
- [ ] Run `python3 -m unittest discover -s tests`.
