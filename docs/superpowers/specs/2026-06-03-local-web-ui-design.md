# Local Web UI First Version Design

## Goal

Build a local web UI for non-technical coworkers to detect risky comments on one Xiaohongshu post at a time. The primary workflow is: paste a post URL, start detection, complete login or page confirmation in the visible browser if needed, then review a clear list of risky comments and suggested actions.

## Scope

The first version supports manual detection for a single post link. It does not support background monitoring of multiple posts, team accounts, cloud deployment, automatic comment deletion, private Xiaohongshu APIs, or bypassing verification.

## User Experience

The home page shows one prominent Xiaohongshu URL field and a start button. After a job starts, the app shows a status page with clear steps:

1. Opening Xiaohongshu page
2. Waiting for user confirmation
3. Collecting visible comments
4. Reviewing comments
5. Preparing report

When the browser opens, the user can log in, handle verification, and navigate to the comment area. The web UI provides a "continue collection" button so the user never needs to return to the terminal.

The result page prioritizes comments that need attention. Risky comments are sorted by severity and show comment text, risk level, categories, reasons, and recommended action. Clean or ordinary feedback comments are available in a secondary section so the main screen stays focused.

The app keeps local history for recent detection jobs, including the URL, start time, status, number of collected comments, number of risky comments, and report path.

## Architecture

Add a lightweight local Python web server using Flask. The server reuses existing modules rather than rewriting the moderation logic:

- `xhs_comment_moderator.py` remains the classification engine.
- `xhs_browser_collect.py` provides browser collection helpers.
- New web code owns job state, routing, templates, static assets, and report persistence.

Each detection runs as a background thread so the web page can poll status without freezing. Job data is stored locally under `xhs_ui_data/` as JSON and CSV files. This keeps the first version simple and inspectable.

## Data Flow

1. User submits a Xiaohongshu URL.
2. Server creates a job directory under `xhs_ui_data/jobs/<job_id>/`.
3. Server launches a visible Playwright browser with the existing persistent profile.
4. Job status changes to waiting for confirmation.
5. User clicks continue in the web UI.
6. Server scrolls the page, extracts visible comment candidates, and saves screenshots.
7. Server classifies comments using existing local moderation rules.
8. Server writes a CSV report and JSON job summary.
9. Result page reads the saved job summary and report rows.

## Error Handling

The UI should show plain-language errors: missing Playwright, browser launch failure, page load timeout, no comments found, or invalid URL. It should preserve screenshots and partial job output when possible so the user can retry or inspect what happened.

## Testing

Verification should cover:

- Existing sample moderation still works from CLI.
- Flask routes load without errors.
- A job can be created from a URL.
- Result rendering works with saved sample rows.
- Browser collection failure is shown as a readable job error.

Manual browser testing is expected because Xiaohongshu login and page availability depend on external state.
