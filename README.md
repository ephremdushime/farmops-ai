# FarmOps AI

## Field Intelligence

**Hackathon prototype:** an agricultural intelligence workspace for turning field evidence into AI-assisted assessments, reviewable spatial signals, verified observations, and coordinated field action.

## Why this exists

Agricultural extension workers often need to gather incomplete reports, decide what information is missing, coordinate field review, and follow up across farms. FarmOps AI prototypes that workflow. It is not intended to replace local agricultural expertise or provide definitive crop diagnosis.

## Current features

- Farm incident intake with farm, location, crop, issue category, and observation fields.
- Case dashboard and case detail view.
- Follow-up task creation and completion tracking.
- Case status tracking.
- Six operational views: overview, live field reports, intelligence cases, risk map, verification centre, and response operations.
- Required observation date and district, optional paired latitude/longitude, and stable observation reference IDs.
- Explainable report-completeness indicator based on five recorded evidence fields; it is not diagnosis confidence.
- Candidate spatial clusters require matching crop and issue category and pairwise proximity within 30 km and 14 days. The 0–100 linkage signal starts at 25, adds up to 25 for report count, 25 for proximity and 25 for time proximity. It is a review-priority heuristic, not an outbreak probability.
- Optional Meta Model API integration using Muse Spark.
- Structured assessments that separate observations, tentative hypotheses, missing information, follow-up questions, and coordinated actions.
- Response validation with a clearly labelled workflow fallback if the API is unavailable or returns invalid data.
- Optional JPEG, PNG, and WebP photo evidence, passed to Muse Spark when configured and stored outside the public static directory.
- Officer review that records corrected observations, urgency, hypotheses, information needs, actions, and a decision in an append-only case audit trail.
- Officer-confirmed observations and location/crop/issue summaries for unresolved cases.
- Field action assignment with due dates and required completion outcomes.
- Clearly labelled demo/fallback mode when API credentials are absent or the API call fails.
- SQLite persistence for local prototyping.

## Run locally

Requires Python 3.10+.

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp .env.example .env
python app.py
```

Set `MODEL_API_KEY` in your environment before launching to enable Meta Model API requests. On Windows PowerShell:

```powershell
$env:MODEL_API_KEY="your-key"
$env:META_MODEL_ID="muse-spark-1.3"
python app.py
```

On macOS/Linux:

```bash
export MODEL_API_KEY="your-key"
export META_MODEL_ID="muse-spark-1.3"
python app.py
```

Open http://127.0.0.1:5000.

## Run tests

Run the app workflow smoke tests with Python's standard-library test runner:

```powershell
python -m unittest discover -v
```

Tests use a temporary SQLite database and do not modify local case data.

## Synthetic demo dataset

The demo seeder adds 24 clearly marked synthetic records across three fictional demo districts, with six awaiting review and two rule-based candidate clusters. It refuses to seed a non-empty database so demonstration records cannot silently mix with existing reports.

Use a separate database in Windows PowerShell:

```powershell
$env:FARMOPS_DB_PATH="$PWD\farmops-demo.db"
$env:FARMOPS_UPLOAD_DIR="$PWD\instance\farmops-demo-uploads"
python app.py --seed-demo
python app.py
```

Keep the environment variable set in the same terminal when running the app. Do not copy real data into the demonstration database.

**Security and privacy:** Do not commit `.env`, API keys, real farmer personal information, or sensitive farm records. Use synthetic test cases during the hackathon. Uploaded images are stored under the ignored `instance/` directory, but the prototype has no authentication or authorization: anyone who can reach the app and obtain a case link can access its evidence and submit reviews. Do not deploy it with real or sensitive records.

## Meta Model API

The app uses the OpenAI Python SDK with Meta's OpenAI-compatible base URL `https://api.meta.ai/v1` and the Responses API. The default model is `muse-spark-1.3`. Confirm the model ID and access in your account's current documentation/dashboard.

When configured, attached images are sent with the report to Meta. Review the provider's data handling requirements before using non-synthetic evidence. The map uses Leaflet and OpenStreetMap tile services; map tiles are requested by the user's browser.

## Demo cases

Use fictional farms and observations only, for example:
- “Several maize plants have yellowing leaves in one section after two days of heavy rain. The affected area and onset are not yet confirmed.”
- “A bean farmer reports wilting in a small patch; irrigation history and root condition are unknown.”
- “A storage group noticed moisture and unusual odor in part of a grain store; extent and storage conditions need inspection.”

The prototype should ask for missing information and coordinate review. It should not recommend a specific pesticide, dosage, or definitive diagnosis from an incomplete report.

## Scope and limitations

This is an early hackathon prototype, not production-ready software. It has not undergone security, agronomic, accessibility, or field validation review. Authentication, role-based access, deployment hardening, offline capture/synchronization, external weather or government data, satellite integrations, and validated yield forecasting remain future work. Muse Spark is used for language/image interpretation, not crop-yield forecasting. Spatial groupings are candidate links from simple distance/time/category rules, not validated disease or outbreak detections.

## Hackathon work log

Keep a dated log of original contributions, tests, and limitations as they are implemented. The submission demo should clearly show features created during the hackathon.

## License

No license has been selected yet. Choose a license before inviting reuse or accepting outside contributions.
