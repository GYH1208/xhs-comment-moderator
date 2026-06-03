# Forced Model Review Design

## Goal

Make the web UI support full automatic review for collected comments by requiring model review before a detection result is considered complete.

## Scope

This change applies to web UI detection jobs. It does not automate deleting, reporting, or blocking comments. It does not solve comments that were never collected from the Xiaohongshu web page.

## Behavior

Model settings default to forced model review:

- `enabled`: true
- `llm_mode`: `all`
- `max_llm_comments`: `0`, meaning unlimited
- `collection_intensity`: `standard`

When forced model review is enabled, the web UI requires an API Key before starting a detection job. During review, every collected comment is sent through the configured model unless the user sets a positive maximum review count. If model review fails, the job becomes an error and does not present local-rule-only output as a complete automatic audit.

Users may still disable model review to run local-rule-only detection, but the UI labels that state clearly.

## Collection Intensity

Model review cannot fix comments that were not collected. The settings page therefore includes a collection intensity option:

- `standard`: existing scroll settings.
- `deep`: more scrolls, longer waits, and smaller scroll distance to improve comment discovery from the visible web page.

## Testing

Tests cover forced defaults, missing API Key rejection, successful forced model review, forced model failure, and local-rule fallback only when model review is disabled.
