# Hackathon work log

Use this file to record work completed during the Meta Global AI Developer Hackathon.

## 2026-10-26 — Initial prototype scaffold
- Created a Flask application for agricultural incident intake.
- Added SQLite persistence for cases and follow-up tasks.
- Added case dashboard, case detail view, status changes, and task completion controls.
- Added optional Meta Model API integration and clearly labelled fallback behavior.
- Added README, environment example, and `.gitignore`.

## 2026-11-01 — Core workflow smoke tests
- Added automated checks for health, required-field validation, case creation, status updates, and follow-up task completion.
- Isolated test data in a temporary SQLite database and ensured database connections close after each operation.
- Made the manual Meta API connection check safe to import during test discovery.
- Validation: `python -m unittest discover -v` — 3 tests passed.

## 2026-11-01 — Structured field assessment
- Standardized Meta responses into validated observations, tentative hypotheses, missing information, reporter questions, urgency, safety notes, and 3–5 coordinated actions.
- Added backward-compatible SQLite migration for the new assessment fields and surfaced them on case detail pages with explicit human-verification labeling.
- Added mocked API success/invalid-response coverage; no live Meta request was made because no API key is configured in the environment.
- Validation: `python -m unittest discover -v` — 6 tests passed, including migration of an existing database.

## 2026-11-01 — Evidence, officer verification, and action tracking
- Added bounded JPEG/PNG/WebP photo intake with signature checks, private local storage, case-scoped evidence delivery, and image input to the Meta Responses request.
- Added officer correction and confirm/follow-up/reject decisions, per-hypothesis dispositions, and append-only original-versus-reviewed assessment history.
- Added migrations for evidence/review state and task outcomes without discarding existing records.
- Added officer-confirmed observations and unresolved-case summaries by location and crop/issue, custom dated field actions, and required completion outcomes.
- Documented that the demo has no authentication and must not hold sensitive case data.
- Validation: `python -m unittest discover -v` — 11 tests passed, including photo, review, audit, dashboard, task outcome, and migration paths. No live Meta request was made because no API key is configured.

## 2026-11-01 — Field intelligence vertical slice
- Added district/date/coordinate metadata and stable observation references with bounds, paired-coordinate, and future-date validation.
- Added explainable report-completeness scoring and pairwise spatial/temporal candidate clustering by crop and issue category (30 km, 14 days); linkage score is explicitly not diagnosis confidence.
- Added six connected operational views: overview, live reports, intelligence candidates, Leaflet risk map, verification queue, and response operations.
- Added an explicit, repeat-safe synthetic-data command (24 records, three fictional districts, six pending reviews, two candidate clusters); it refuses to mix seed records into any non-empty database.
- Added evidence metadata including media type, byte size, original filename, and SHA-256, plus append-only case event history for intake, reviews, status, and field actions.
- Documented external map-tile privacy, API image transfer, synthetic limits, and non-production access-control limitations.
- Validation: targeted spatial/page/seed tests and Python compilation passed; full suite to be rerun after final changes.

## Final validation
- Full regression suite: `python -m unittest discover -v` — 16 tests passed.
- `python -m py_compile app.py test_app.py test_meta_api.py` and `git diff --check` passed.
- A live Meta Model API request remains unverified because no API key is configured.

## Next validation steps
- [ ] Confirm Meta Model API key and model access.
- [ ] Test the first real model request.
- [ ] Validate the workflow with an agricultural worker.
- [x] Add automated tests and run them.
- [x] Add input/output validation for model responses.
- [ ] Add a deployment plan and record demo evidence.
