import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "farmops.db"
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-change-me")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                farm_name TEXT NOT NULL,
                reporter_name TEXT NOT NULL,
                location TEXT NOT NULL,
                crop TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                description TEXT NOT NULL,
                urgency TEXT NOT NULL DEFAULT 'Needs review',
                ai_summary TEXT NOT NULL DEFAULT '',
                next_steps TEXT NOT NULL DEFAULT '',
                uncertainty TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Open',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                due_date TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TEXT NOT NULL,
                FOREIGN KEY(case_id) REFERENCES cases(id)
            )
        """)


def analyze_with_meta(case_data):
    """Use Meta Model API when configured; otherwise return clearly-labelled demo output."""
    api_key = os.getenv("MODEL_API_KEY")
    if not api_key:
        return {
            "mode": "DEMO MODE — no Meta API key configured",
            "summary": (
                f"{case_data['crop']} case reported at {case_data['farm_name']} "
                f"({case_data['location']}): {case_data['description']}"
            ),
            "urgency": "Needs review",
            "steps": [
                "Confirm when the problem began and how much of the field is affected.",
                "Record recent rainfall, irrigation, fertilizer, pesticide, and other relevant changes.",
                "Ask for clear photos or an in-person assessment if appropriate.",
                "Refer the case to a qualified agricultural extension officer for field-specific advice.",
                "Record the agreed action and schedule a follow-up to check the outcome."
            ],
            "uncertainty": (
                "This is a workflow demonstration, not an AI-generated assessment. "
                "The cause has not been established; do not apply chemicals or change treatment "
                "based only on this demo output."
            )
        }

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.meta.ai/v1")
        prompt = f"""
You are FarmOps AI, an assistant for agricultural extension workers.
You are NOT a substitute for local expert assessment. Do not confidently diagnose
crop disease or prescribe pesticide/fertilizer use from incomplete information.
Identify missing information, separate observations from hypotheses, flag uncertainty,
and recommend escalation when needed. Output valid JSON only with keys:
summary (string), urgency (one of "Routine", "Soon", "Urgent field review", "Needs review"),
steps (array of 3-5 concise actions), uncertainty (string).
Treat this as a coordination and triage task, not definitive agronomic diagnosis.

Case:
Farm: {case_data['farm_name']}
Reporter: {case_data['reporter_name']}
Location: {case_data['location']}
Crop: {case_data['crop']}
Issue category: {case_data['issue_type']}
Report: {case_data['description']}
"""
        response = client.responses.create(
            model=os.getenv("META_MODEL_ID", "muse-spark-1.3"),
            input=prompt
        )
        raw = response.output_text.strip()
        parsed = json.loads(raw)
        parsed["mode"] = "Meta Model API"
        parsed["steps"] = parsed.get("steps", [])[:5]
        return parsed
    except Exception as exc:
        return {
            "mode": "Fallback mode — Meta API request failed",
            "summary": f"Case received for {case_data['crop']} at {case_data['farm_name']}.",
            "urgency": "Needs review",
            "steps": [
                "Confirm the onset and extent of the reported problem.",
                "Collect relevant field history and observations.",
                "Arrange review by an agricultural extension worker.",
                "Record the decision and set a follow-up date."
            ],
            "uncertainty": f"No AI assessment was produced. Check API key, model access, and API response. Technical detail: {type(exc).__name__}"
        }


@app.route("/")
def index():
    with db() as conn:
        cases = conn.execute("SELECT * FROM cases ORDER BY id DESC").fetchall()
        task_counts = conn.execute("""
            SELECT
              SUM(CASE WHEN status='Pending' THEN 1 ELSE 0 END) AS pending,
              SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) AS completed
            FROM tasks
        """).fetchone()
    return render_template("index.html", cases=cases, task_counts=task_counts)


@app.route("/cases/new", methods=["GET", "POST"])
def new_case():
    if request.method == "POST":
        data = {
            "farm_name": request.form.get("farm_name", "").strip(),
            "reporter_name": request.form.get("reporter_name", "").strip(),
            "location": request.form.get("location", "").strip(),
            "crop": request.form.get("crop", "").strip(),
            "issue_type": request.form.get("issue_type", "").strip(),
            "description": request.form.get("description", "").strip(),
        }
        if not all(data.values()):
            flash("Please complete every required field.", "error")
            return render_template("new_case.html", data=data)
        result = analyze_with_meta(data)
        with db() as conn:
            cur = conn.execute("""
                INSERT INTO cases
                (farm_name, reporter_name, location, crop, issue_type, description,
                 urgency, ai_summary, next_steps, uncertainty, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Open', ?)
            """, (
                data["farm_name"], data["reporter_name"], data["location"], data["crop"],
                data["issue_type"], data["description"], result.get("urgency", "Needs review"),
                result.get("summary", ""), json.dumps(result.get("steps", [])),
                result.get("uncertainty", ""), datetime.utcnow().isoformat(timespec="seconds") + "Z"
            ))
            case_id = cur.lastrowid
            for step in result.get("steps", []):
                conn.execute(
                    "INSERT INTO tasks (case_id, title, created_at) VALUES (?, ?, ?)",
                    (case_id, step, datetime.utcnow().isoformat(timespec="seconds") + "Z")
                )
        flash(f"Case #{case_id} created. Mode: {result.get('mode', 'unknown')}", "success")
        return redirect(url_for("case_detail", case_id=case_id))
    return render_template("new_case.html", data={})


@app.route("/cases/<int:case_id>")
def case_detail(case_id):
    with db() as conn:
        case = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        tasks = conn.execute("SELECT * FROM tasks WHERE case_id=? ORDER BY id", (case_id,)).fetchall()
    if not case:
        flash("Case not found.", "error")
        return redirect(url_for("index"))
    try:
        steps = json.loads(case["next_steps"])
    except (ValueError, TypeError):
        steps = []
    return render_template("case_detail.html", case=case, tasks=tasks, steps=steps)


@app.route("/tasks/<int:task_id>/toggle", methods=["POST"])
def toggle_task(task_id):
    with db() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if task:
            new_status = "Completed" if task["status"] == "Pending" else "Pending"
            conn.execute("UPDATE tasks SET status=? WHERE id=?", (new_status, task_id))
            flash(f"Task marked {new_status.lower()}.", "success")
            case_id = task["case_id"]
        else:
            flash("Task not found.", "error")
            return redirect(url_for("index"))
    return redirect(url_for("case_detail", case_id=case_id))


@app.route("/cases/<int:case_id>/status", methods=["POST"])
def update_case_status(case_id):
    status = request.form.get("status", "Open")
    if status not in {"Open", "In progress", "Resolved"}:
        status = "Open"
    with db() as conn:
        conn.execute("UPDATE cases SET status=? WHERE id=?", (status, case_id))
    flash("Case status updated.", "success")
    return redirect(url_for("case_detail", case_id=case_id))


@app.route("/health")
def health():
    return {"status": "ok", "app": "FarmOps AI"}


init_db()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true", host="127.0.0.1", port=int(os.getenv("PORT", "5000")))
