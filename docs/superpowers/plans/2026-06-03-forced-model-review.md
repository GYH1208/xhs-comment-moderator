# Forced Model Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require model review for web UI automatic audits and fail jobs when forced model review cannot complete.

**Architecture:** Extend existing `xhs_ui_app.py` settings and classification helpers. Keep local-rule-only behavior available only when model review is disabled.

**Tech Stack:** Python 3, Flask, unittest, existing DeepSeek-compatible moderation client.

---

### Task 1: Forced Review Settings

**Files:**
- Modify: `xhs_ui_app.py`
- Modify: `templates/settings.html`
- Modify: `tests/test_xhs_ui_app.py`

- [ ] Change defaults to enabled model review, `llm_mode=all`, and unlimited model calls.
- [ ] Add collection intensity setting.
- [ ] Reject detection start when forced model review is enabled without an API Key.
- [ ] Verify with `python3 -m unittest discover -s tests`.

### Task 2: Strict Model Failure Handling

**Files:**
- Modify: `xhs_ui_app.py`
- Modify: `tests/test_xhs_ui_app.py`

- [ ] Make forced model review raise an error when no model client is available.
- [ ] Make forced model review raise an error when the model call fails.
- [ ] Preserve local-rule-only fallback when model review is disabled.
- [ ] Verify with `python3 -m unittest discover -s tests`.

### Task 3: Documentation and Verification

**Files:**
- Modify: `README.md`

- [ ] Document forced model review behavior.
- [ ] Document collection intensity.
- [ ] Run `python3 -m py_compile xhs_ui_app.py xhs_browser_collect.py xhs_comment_moderator.py`.
- [ ] Run `python3 -m unittest discover -s tests`.
