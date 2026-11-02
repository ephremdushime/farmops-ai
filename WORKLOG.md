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

## 2026-11-01 — Meta Model API integration audit
- Verified current Meta docs for `https://api.meta.ai/v1`, `muse-spark-1.3`, the OpenAI-compatible Responses API, `output_text`, and inline image input.
- Added root `.env` loading with process-environment precedence; `.env` remains ignored and unchanged.
- Limited Meta text input to crop, issue category, observation date, and symptom description; removed known reporter/farm/location/district identifiers from the description before sending.
- Removed image metadata from API copies while preserving original local evidence; added visible disclosure of what is shared and the remaining image/text content risks.
- Added strict JSON-schema output plus local validation, an explicit request timeout/retry policy, and persistent source/model attribution with privacy-conscious success/fallback logs.
- Reworked the manual API smoke script to use environment credentials only, avoid printing keys or full error bodies, and skip network access when no key is configured.
- Validation: 18 tests passed; Python compilation and `git diff --check` passed. Live API request skipped because there is no `.env` and `MODEL_API_KEY` is not set in the process environment.

## 2026-11-01 — Live Meta API fire test (key rejected)
- First real Meta request attempt returned HTTP 401; the app correctly fell back with labeled output and a log line.
- `.env` format verified clean without viewing the key; awaiting a valid key from the Meta dashboard.

## 2026-11-01 — Flagship overview analytics interface
- Rebuilt the overview as a dark operations dashboard: intake-velocity chart (7/14-day toggle), urgency mix, district ranking, dark basemap.
- Added pure analytics helpers with unit coverage.
- Validation: `python -m unittest` — 23 tests passed; all pages verified live.

## 2026-11-01 — First live Meta assessment verified
- Rotated to a fresh MODEL_API_KEY; synthetic live-fire case returned a genuine `Meta Model API` assessment (muse-spark-1.3) in ~19s.
- Prior 401 was a rejected key value; app fallback behaved correctly throughout.

## 2026-11-01 — Evidence-completeness system
- Guided intake sections (affected area, crop context, field conditions), 4 labeled photo slots, live completeness meter.
- Structured evidence feeds the Meta prompt; missing items become evidence tasks; follow-up notes plus one-click reassessment with run history.
- Completeness scoring extended to 8 dimensions; verification queue prioritizes thin evidence; overview depth KPI added.
- Validation: `python -m unittest` — 37 tests passed; live E2E verified (real Meta assess + reassess, runs 1-2 recorded).

## Next validation steps
- [x] Confirm Meta Model API key and model access.
- [x] Test the first real model request.
- [ ] Validate the workflow with an agricultural worker.
- [x] Add automated tests and run them.
- [x] Add input/output validation for model responses.
- [ ] Add a deployment plan and record demo evidence.

## Voice-note evidence (Nov 2)
- Optional voice-note upload on intake and follow-up (WAV/MP3/M4A/OGG/WebM/MP4, 10 MB), transcribed via Meta muse-voice-transcribe-1.0 (PUSH_TO_TALK, WAV).
- Transcript stored as a case note, appended to the Muse Spark assessment input, and playable from the case page; audio served privately with no-store.
- Graceful notices when the API key, requests, or ffmpeg is missing; voice never counts as photo evidence in completeness.
- Validation: `python -m unittest` -- 43 tests passed; live E2E verified (real transcribe plus spark assessment on synthetic speech).

## Competition readiness sprint (Nov 2)
- Phase 1: fixed the risk_map.js attribution SyntaxError that broke all maps; node --check clean on 4 scripts; theme/fallback/empty-map behaviors verified with a stubbed harness; CARTO and OSM tiles return 200.
- Phase 2: reassessment now sends images only (voice rows no longer poison the image payload); assessment history shows per-run changes; failure tests cover malformed JSON, SDK timeout, and HTTP 401.
- Phase 3: cluster explanations name crop, issue, and date range; each member carries an inclusion reason shown on the Intelligence page; 30 km/14-day rules held.
- Phase 4: review audit compares original AI observations/hypotheses with officer-verified versions; dispositions cite the original text; urgency changes flagged; append-only history locked by tests.
- Phase 5: AI forms show loading states and block double-posts; provenance shows assessment time; field reports gain a review-status filter and clear link.
- Phase 6: session cookies hardened (HttpOnly, SameSite=Lax); verified no secrets in tracked files or history, no key material in logs/responses, prototype labelling on every page; CSRF tokens documented as deployment-required.
- Validation: `python -m unittest` -- 58 tests passed; `node --check` clean on all app scripts.
