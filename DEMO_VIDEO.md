# FarmOps AI — 3-Minute Demo Video Plan

Target: under 3:00 (aim 2:45). Track: Indie. Theme: Build for Your World.
Record at 1080p, light theme, browser 100% zoom. Narration ~430 words ≈ 2:45 at a calm pace.

## Recording prep checklist

- [ ] Fresh database with demo data: stop the server, delete `farmops.db`, then `python app.py --seed-demo`.
- [ ] Real key in `.env` (`MODEL_API_KEY`), then restart the server. Verify one assessment returns `Meta Model API` before recording.
- [ ] Prepare evidence files on disk: one crop photo (your own / consented / synthetic only) and one short voice note WAV (≤10 MB, e.g. "Yellow patches near the low corner after heavy rain").
- [ ] Browser: light theme toggled on, bookmarks bar hidden, only the app tab open, zoom 100%.
- [ ] Close chat/email/notification apps. Phone on silent. Record system audio OFF, microphone ON.
- [ ] Do one full dry run off-camera to warm up (typing, uploads, timing).
- [ ] NEVER show: `.env`, the API key, terminal output containing secrets, or real farmer identities. All data on screen must be synthetic.

## Narration script (read verbatim, calm pace)

**SHOT 1 — Hook, overview dashboard (0:00–0:20).**
"In Rwanda, most farmers are smallholders. When trouble hits a remote field, it can take days for an extension officer to hear about it — and by then, neighboring farms are at risk. FarmOps AI closes that gap: a field-intelligence loop from farmer report, to AI triage, to officer verification, with a live national picture on top."

**SHOT 2 — New report, evidence intake (0:20–0:55).**
"Everything starts with a field report. The intake guides the reporter through the evidence that matters: affected area, crop context, and field conditions — plus guided photo slots and, new, a spoken voice note for officers who would rather talk than type."

**SHOT 3 — Submit, loading, Meta assessment (0:55–1:25).**
"On submit, the report goes to Meta's Muse Spark model, with the voice note transcribed by Muse Voice Transcribe. Seconds later we get a structured assessment — and note the provenance badge: every assessment is permanently labelled with its source and model, and every hypothesis is marked tentative and unverified. The model never issues a diagnosis."

**SHOT 4 — Follow-up evidence + reassessment (1:25–1:55).**
"Farming is a moving picture, so new evidence can be added at any time. Watch the assessment history: re-running the assessment with the latest evidence shows exactly what changed between runs — urgency, observations, and source."

**SHOT 5 — Officer verification (1:55–2:20).**
"Now the human step. The officer compares the original AI output against verified observations, rules on each hypothesis, and records a decision. Everything lands in an append-only audit trail — nothing is ever overwritten."

**SHOT 6 — National picture: map + clusters (2:20–2:45).**
"Zoom out, and reports become a national picture: a live map of geolocated observations, and explainable candidate clusters that show their own reasoning — same crop, same issue, within thirty kilometers and fourteen days. They prioritize human review; they never claim an outbreak. That is FarmOps AI: Meta models, human judgment, healthier harvests."

## Shot list (exact clicks)

| # | Time | Screen | Action |
|---|------|--------|--------|
| 1 | 0:00 | `/` overview | Slow scroll: KPIs → map with markers → Operations Watch. Click one KPI to show it navigates. |
| 2 | 0:20 | `/cases/new` | Fill farm/crop/issue/district/date (synthetic). Scroll through evidence sections. Attach 1 photo + 1 voice note. |
| 3 | 0:55 | submit → `/cases/<id>` | Click "Create case and plan". Hold on the loading button briefly. Scroll the assessment: provenance badge, observations, tentative hypotheses, uncertainty box. Play the voice note. |
| 4 | 1:25 | same page | "Record evidence": add a note. Click "Re-run assessment with latest evidence". Open Assessment history, point at the change line for run 2. |
| 5 | 1:55 | `#officer-review` | Scroll the form (prefilled corrections, hypothesis dispositions). Submit a "Verified" review as a demo officer. Show the audit entry + compare block. |
| 6 | 2:20 | `/risk-map`, `/intelligence` | Pan the map, open a marker popup. Switch to Intelligence: one cluster card, its metrics, one inclusion reason. End on overview. |

## Recording notes

- The submit buttons show progress text during the model call; keep narrating over it.
- If the API is unreachable, the app shows its labelled fallback state instead of failing silently. That honesty-by-design is part of the demo, so keep going.
- For a wrong click, pause, navigate back, and keep recording; trim in edit.

## After recording

- [ ] Trim to ≤3:00. Add captions (auto + fix names: "Muse Spark", "FarmOps AI").
- [ ] Upload to YouTube as Unlisted. Title: "FarmOps AI — Field Intelligence for Rwandan Agriculture (Meta Hackathon Demo)".
- [ ] Paste the link into the submission form demo-video field and test it in an incognito window.
- [ ] Description box: one paragraph (problem + solution), repo link, "Built with Muse Spark and Muse Voice Transcribe via Meta Model API. Prototype; synthetic demo data."
