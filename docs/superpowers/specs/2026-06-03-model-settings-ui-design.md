# Model Settings UI Design

## Goal

Add a local web UI settings window so coworkers can configure semantic model review without editing `.env` or using the command line.

## Scope

The first version supports one OpenAI-compatible DeepSeek configuration for the local web UI. It does not add user accounts, cloud sharing, multi-provider presets, or encrypted credential storage. Settings are local to the machine running the app.

## User Experience

The top navigation includes "模型配置". The settings page lets the user:

- Enable or disable model review.
- Enter an API Key.
- Edit the model name, defaulting to `deepseek-v4-flash`.
- Edit the base URL, defaulting to `https://api.deepseek.com`.
- Choose review mode: all comments, uncertain comments, or risky comments.
- Set an optional maximum number of comments sent to the model.
- Save settings.
- Test the connection with a short model request.

The API Key is stored locally and shown only as a masked value after saving. The home page shows whether model review is enabled or local rules only.

## Architecture

Keep the model review engine in `xhs_comment_moderator.py`. Add settings helpers in `xhs_ui_app.py` that read and write `xhs_ui_data/settings.json`. When a detection job reaches the review step, the UI app loads settings and creates `LlmModerator` only when model review is enabled and an API Key is present.

## Data Flow

1. User opens model settings.
2. User saves settings to `xhs_ui_data/settings.json`.
3. User starts a detection job.
4. Browser collection returns comment text.
5. The job builds local rule results and, when enabled, calls the configured model according to the selected review mode and limit.
6. Report rows include existing `llm_*` fields.

## Error Handling

Saving settings validates mode, URL shape, and numeric limit. If model review is enabled without an API Key, the settings page explains that the key is required. If model review fails during a job, the job falls back to local rules and records a warning in the job metadata instead of failing the entire detection.

## Testing

Tests cover settings defaults, save behavior with masked API Key display, invalid form handling, job classification using configured model settings, and model failure fallback.
