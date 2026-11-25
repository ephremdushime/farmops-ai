# Sprint 0 — Production Architecture & Security Audit (COMPLETE)

Date: 2026-11-24 · Repo: farmops-ai @ main cb4eed6 · Baseline: 78/78 tests pass (~15s), re-run live this session.
Method: read-only audit by 6 scoped reviewers (routes/auth, uploads, DB, templates/UX, Meta integration,
tests/config) + adversarial critic + synthesis. 14 extra gaps found by critic; all folded in below.

Confirmed renovation direction: serve BOTH officers and decision-makers (separate workspaces),
integrated-intelligence focus, evolve the Flask platform toward modular architecture (no rebuild).

## Verdict

Prototype is well-crafted for a hackathon (clean validation chains, honest fallback labeling, zero XSS sinks
found) but MUST NOT hold real farmer data or face the network until P0 is done. Total: 10 P0 blockers,
10 P1 hardening items, 8 P2 evolution items. Data compat and all 78 tests must stay green throughout.

## Load-bearing facts (file:line verified)

- 18 routes: 11 read-only GETs, 7 state-mutating POSTs, 0 state-changing GETs — plus Flask default
  GET /static/<path>. No auth check and no CSRF token on any route.
- app.py:74 secret falls back to dev-only-change-me; cookies HttpOnly+SameSite=Lax only (:75-76);
  no Secure flag, no HSTS, zero 401/403 paths in the app.
- Reviewer identity is free text (:2189-2194, default Field team :2339); anonymous POSTs proven by tests.
- Unauthenticated callers can trigger billed Meta Spark + voice-transcribe calls (intake/evidence/reassess).
- Stored/served evidence bytes are EXIF-intact originals; metadata strip applies to Meta-bound copies only.
- Follow-up photo uploads bypass the 4-photo intake cap (unbounded per-case growth).
- .mp4/.webm accepted as voice notes and served back inline (video-as-voice undecided).
- DB: 7 tables, additive migrations, no version table, no indexes, no UNIQUE anywhere, plain
  sqlite3.connect (no timeout/WAL), init_db() at import time, no backup/restore code.
- Only error handler is 413 redirect that drops all user input; no 404/405/500 handlers, so
  debug=true (:2815) would expose the Werkzeug debugger on any 500.
- Entry point is the Flask dev server; no wsgi/Dockerfile/Procfile/CI; loose unpinned requirements;
  httpx imported by tests but missing from requirements; PORT/FARMOPS_DB_PATH/FARMOPS_UPLOAD_DIR
  missing from .env.example.

## P0 — production blockers (all before any pilot data)

- P0-1 AuthN/AuthZ + two workspaces. users table + Flask-Login, roles officer/decision-maker/admin,
  login_required on all routes incl. evidence + static review; officers mutate, decision-makers read-only;
  session identity replaces free-text reviewer; additive migration. L (3-5d). Verify: anon POST gives
  302/403 on all 7 POSTs; decision-maker POST gives 403; 78 green via login helper.
- P0-2 CSRF on all 8 POST forms (Flask-WTF/SeaSurf, incl. multipart intake). S (0.5-1d).
  Verify: tokenless POST gives 400; 78 green.
- P0-3 Fail-closed secrets/cookies/HTTPS/debug. Remove dev-secret fallback (refuse prod boot without
  secret); Secure cookies + HTTPS/HSTS; force FLASK_DEBUG=false in prod. S (0.5d). Verify: boot fails
  loudly; cookie flags asserted; 500 page leaks nothing.
- P0-4 Production entry + config. wsgi.py + gunicorn/waitress + Dockerfile/Procfile; init_db() out of
  import time into explicit migrate CLI; complete .env.example; document seed accounts. M (1-2d).
  Verify: container serves app; import creates no files; bad PORT fails fast.
- P0-5 SQLite durability + ref integrity. timeout + WAL; indexes on cases(district,status,review_status,
  observed_at) + child FKs; UNIQUE observation_ref + retry-on-collision; backup/restore/export CLI with
  tested restore. M (2d). Verify: parallel-write smoke; dup-ref retried; backup-corrupt-restore test.
- P0-6 Upload abuse + retention. Cumulative per-case photo cap + disk quotas; decide video-as-voice
  (reject or reclassify); PIL-open/dimension check at intake; startup orphan sweep; delete/retention policy.
  M (2d). Verify: quota tests; truncated-image gives 400; kill-mid-write then sweep; retention job tested.
- P0-7 Stored-original privacy + cache headers. Strip/sanitize on store (originals server-side only) +
  strip audio container tags; keep traversal/cross-case 404s; extend private,no-store+nosniff to all PII
  HTML (today only the evidence route sets Cache-Control). M (1-2d). Verify: served bytes EXIF/GPS-free.
- P0-8 Metered-AI spend + payload minimization. Auth + rate limits + daily AI budget kill-switch on all
  3 Meta-invoking POSTs; sanitize voice multipart filename (raw user filename sent today); decide
  district-as-voice-keyword; fix redaction docs (see Correction 1). M (1-2d). Verify: anon AI POST makes
  zero Meta calls (mock-asserted).
- P0-9 Error handling + 413 UX. 404/405/500 branded handlers; 413 preserves input; reconcile 32MB
  global vs per-file caps with clear message. S (0.5-1d). Verify: codes correct; oversize POST keeps fields.
- P0-10 Pin dependencies + runtime. Hashed lockfile; add httpx, gunicorn/waitress, Flask-Login, CSRF lib;
  declare ffmpeg optional with degrade matrix; enforce Python 3.10+ at runtime. S (0.5d). Verify: hashed
  install + 78 green in fresh venv.

## P1 — hardening (before institutional pilot)

- P1-1 HTTP headers (CSP, X-Frame-Options, Referrer-Policy) + /static/ cache policy. S.
- P1-2 Rate limits (Flask-Limiter) on mutating + login routes; server idempotency keys. S (1d).
- P1-3 Validation/escaping regression net: boundary tests for every server validator; forbid
  safe/Markup/innerHTML/eval/fetch sinks by test; lock tojson-in-JSON-script pattern. M (1-2d).
- P1-4 Voice/ffmpeg off request thread with progress; full failure-matrix tests. M (2d).
- P1-5 Meta resilience: 429/500/503/DNS/slow-stream tests + circuit-breaker + degraded banner. S (1d).
- P1-6 Storage-failure tests (DB-fail orphan, disk-full, quota, delete). S.
- P1-7 Input/hostility matrix (XSS/overlong/unicode/filter-injection, health-with-DB-down, 404/405). S.
- P1-8 Leaflet: verify leaflet.css/js version match + SRI; decide tile proxying (viewer IP/viewport
  currently goes to CARTO/OSM). S.
- P1-9 Secrets hygiene: prove .env ignored (live .env exists; only .gitignore:5-8 was cited, never
  line 1); scope .vscode/settings.json useEnvFile auto-load; git-history secret scan; reconcile
  DEMO_VIDEO.md oracle claims. S (0.5d).
- P1-10 PII minimization: masked decision-maker view vs full officer view; keep every
  SYNTHETIC/provenance/consent disclaimer verbatim (grep-tested). S (1d).

## P2 — modular evolution (no rebuild; URLs, templates, JSON shapes, migrations preserved)

- P2-1 Split app.py into blueprints + services + extensions; route-map diff must be empty. L (3-5d).
- P2-2 Officer workspace (queue to verify to act) + decision-maker workspace (brief to map to clusters) on
  one intelligence layer; per-view must-preserve checklist incl. mobile 760px + print CSS. L (3-5d).
- P2-3 Versioned migrations (alembic/flask-migrate) wrapping ADD-COLUMN lineage; Postgres-ready
  run-number allocation; CLI reset --demo replaces delete-the-db. M (2d).
- P2-4 Split test class into tests/ modules; GitHub Actions (pytest, node --check, header/escaping
  gates). M (2d).
- P2-5 Async AI pipeline (worker queue + retries + caps); offline DEMO path stays intact. L (3d).
- P2-6 Retention scheduler + export/dump + content-addressed upload layout (compat symlinks). M (2d).
- P2-7 Front-end automation (JS, tiles-outage, print, perf smoke, 404/405 matrix). M (2d).
- P2-8 Observability: structured logs (model/exception-type/HTTP only), request IDs, audit-trail test. S.

## Corrections to earlier claims

1. Redaction scope: voice transcripts + follow-up notes ARE concatenated into the description BEFORE the
   exact-match redacted pass (intake :1888-1893, reassess :2468-2486, redaction :796-804). Only
   non-exact free-text PII survives. Docs/tests must assert exact-removed vs free-text-survives.
2. Test baseline was re-run live this session (78/78 OK); reviewer could-not-run-tests notes are stale.

## Carried to Day-0 (need shell/browser/keyed staging, unavailable to read-only audit)

CI first run as gate; real .env + overrides; git-history scan; Meta 429/500/503/DNS behavior; browser
truth (responsive/drawer/tiles/theme/print); Leaflet vendor internals + css/js match; filesystem ground
truth (static/ vs instance/, permissions).

## Data-compat constraints for all phases

Additive migrations only (no DROP/DELETE lineage); preserve JSON-TEXT shapes, observation_ref format,
seed guards (24 rows / 6 pending / 3 districts / 2 clusters; double-seed + non-empty refusal), and the
append-only review/event audit trail.
