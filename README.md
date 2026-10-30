# FarmOps AI

**Hackathon prototype:** an agriculture operations workspace for turning farm incident reports into structured cases, coordinated next steps, and trackable follow-up tasks.

## Why this exists

Agricultural extension workers often need to gather incomplete reports, decide what information is missing, coordinate field review, and follow up across farms. FarmOps AI prototypes that workflow. It is not intended to replace local agricultural expertise or provide definitive crop diagnosis.

## Current features

- Farm incident intake with farm, location, crop, issue category, and observation fields.
- Case dashboard and case detail view.
- Follow-up task creation and completion tracking.
- Case status tracking.
- Optional Meta Model API integration using Muse Spark.
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

**Security:** Do not commit `.env`, API keys, real farmer personal information, or sensitive farm records. Use synthetic test cases during the hackathon.

## Meta Model API

The app uses the OpenAI Python SDK with Meta's OpenAI-compatible base URL `https://api.meta.ai/v1` and the Responses API. The default model is `muse-spark-1.3`. Confirm the model ID and access in your account's current documentation/dashboard.

## Demo cases

Use fictional farms and observations only, for example:
- “Several maize plants have yellowing leaves in one section after two days of heavy rain. The affected area and onset are not yet confirmed.”
- “A bean farmer reports wilting in a small patch; irrigation history and root condition are unknown.”
- “A storage group noticed moisture and unusual odor in part of a grain store; extent and storage conditions need inspection.”

The prototype should ask for missing information and coordinate review. It should not recommend a specific pesticide, dosage, or definitive diagnosis from an incomplete report.

## Scope and limitations

This is an early hackathon prototype, not production-ready software. It has not undergone security, agronomic, accessibility, or field validation review. Authentication, role-based access, deployment hardening, multilingual input, audio intake, image handling, audit logs, and robust tests are future work.

## Hackathon work log

Keep a dated log of original contributions, tests, and limitations as they are implemented. The submission demo should clearly show features created during the hackathon.

## License

No license has been selected yet. Choose a license before inviting reuse or accepting outside contributions.
