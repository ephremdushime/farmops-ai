import base64
import hashlib
import json
import importlib
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image, PngImagePlugin


class FarmOpsSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(cls.temp_dir.name) / "test-farmops.db"
        with patch.dict(os.environ, {"FARMOPS_DB_PATH": str(db_path)}):
            cls.module = importlib.import_module("app")
        cls.module.UPLOAD_DIR = Path(cls.temp_dir.name) / "uploads"
        cls.client = cls.module.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def setUp(self):
        self.client = self.module.app.test_client()
        with self.module.db() as conn:
            conn.execute("DELETE FROM case_reviews")
            conn.execute("DELETE FROM case_evidence")
            conn.execute("DELETE FROM case_events")
            conn.execute("DELETE FROM tasks")
            conn.execute("DELETE FROM cases")
        if self.module.UPLOAD_DIR.exists():
            for path in self.module.UPLOAD_DIR.iterdir():
                if path.is_file():
                    path.unlink()

    def create_case(self, **overrides):
        data = {
            "farm_name": "Demo Farm",
            "reporter_name": "Field Officer",
            "location": "Demo District",
            "crop": "Maize",
            "issue_type": "Visible crop change",
            "description": "Yellowing leaves reported after heavy rain.",
            "district": "Central Demo District",
            "observed_at": self.module.datetime.now(
                self.module.timezone.utc
            ).date().isoformat(),
            "latitude": "-1.95",
            "longitude": "30.06",
        }
        data.update(overrides)
        with patch.dict(os.environ, {"MODEL_API_KEY": ""}):
            response = self.client.post("/cases/new", data=data)
        self.assertEqual(response.status_code, 302)
        with self.module.db() as conn:
            return conn.execute("SELECT MAX(id) FROM cases").fetchone()[0]

    def test_health_endpoint(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    def test_incomplete_case_is_rejected(self):
        response = self.client.post("/cases/new", data={"farm_name": "Demo Farm"})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Please complete every required field.", response.data)
        with self.module.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0], 0)

    def test_case_creation_and_follow_up_workflow(self):
        case_id = self.create_case()
        case_url = f"/cases/{case_id}"
        detail = self.client.get(case_url)
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b"DEMO MODE", detail.data)
        self.assertIn(b"Yellowing leaves reported after heavy rain.", detail.data)
        self.assertIn(b"Questions for the reporter", detail.data)
        self.assertIn(b"When did you first notice the problem?", detail.data)
        self.assertIn(b"DEMO MODE", detail.data)
        with self.module.db() as conn:
            row = conn.execute(
                "SELECT observation_ref, assessment_source, assessment_model "
                "FROM cases WHERE id=?",
                (case_id,),
            ).fetchone()
            observation_ref = row["observation_ref"]
            self.assertIn("DEMO MODE", row["assessment_source"])
            self.assertEqual(row["assessment_model"], "")
        self.assertRegex(observation_ref, r"^OBS-[A-F0-9]{12}$")
        self.assertIn(observation_ref.encode(), detail.data)

        with self.module.db() as conn:
            case_id = conn.execute("SELECT id FROM cases").fetchone()[0]
            task_id = conn.execute(
                "SELECT id FROM tasks WHERE case_id=? ORDER BY id LIMIT 1", (case_id,)
            ).fetchone()[0]

        status_response = self.client.post(
            f"/cases/{case_id}/status", data={"status": "In progress"}
        )
        self.assertEqual(status_response.status_code, 302)
        self.client.post(
            f"/tasks/{task_id}/toggle", data={"outcome": "Officer inspected the affected row."}
        )

        with self.module.db() as conn:
            self.assertEqual(
                conn.execute("SELECT status FROM cases WHERE id=?", (case_id,)).fetchone()[0],
                "In progress",
            )
            self.assertEqual(
                conn.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()[0],
                "Completed",
            )
            events = conn.execute(
                "SELECT event_type FROM case_events WHERE case_id=? ORDER BY id",
                (case_id,),
            ).fetchall()
        self.assertEqual(
            [event["event_type"] for event in events],
            ["report_submitted", "action_assigned", "action_assigned",
             "action_assigned", "action_assigned", "action_assigned",
             "case_status_changed", "action_completed"],
        )

    def test_photo_intake_is_private_and_sent_to_meta(self):
        payload = {
            "summary": "Visible leaf yellowing needs field review.",
            "urgency": "Needs review",
            "observations": ["Yellowing leaves are visible in the submitted photo."],
            "hypotheses": [],
            "missing_information": ["Affected area is unknown."],
            "follow_up_questions": ["How widespread is the yellowing?"],
            "steps": ["Estimate affected area.", "Record recent rain.", "Arrange review."],
            "uncertainty": "The photo does not establish a cause.",
        }
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text=json.dumps(payload)
        )
        image_info = PngImagePlugin.PngInfo()
        image_info.add_text("Author", "Private Reporter Name")
        image = Image.new("RGB", (4, 4), color=(40, 120, 60))
        image_buffer = BytesIO()
        image.save(image_buffer, format="PNG", pnginfo=image_info)
        image_bytes = image_buffer.getvalue()
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}):
            with patch("openai.OpenAI", return_value=client):
                client.responses.create.return_value.model = "muse-spark-1.3"
                response = self.client.post(
                    "/cases/new",
                    data={
                        "farm_name": "Demo Farm",
                        "reporter_name": "Field Officer",
                        "location": "Demo District",
                        "crop": "Maize",
                        "issue_type": "Visible crop change",
                        "description": "Yellowing leaves.",
                        "district": "Central Demo District",
                        "observed_at": self.module.datetime.now(
                            self.module.timezone.utc
                        ).date().isoformat(),
                        "latitude": "-1.95",
                        "longitude": "30.06",
                        "photos": (BytesIO(image_bytes), "leaf.png", "image/png"),
                    },
                    content_type="multipart/form-data",
                )
        self.assertEqual(response.status_code, 302)
        input_content = client.responses.create.call_args.kwargs["input"][0]["content"]
        self.assertTrue(any(item["type"] == "input_image" for item in input_content))
        image_item = next(item for item in input_content if item["type"] == "input_image")
        self.assertTrue(image_item["image_url"].startswith("data:image/png;base64,"))
        encoded_image = image_item["image_url"].split(",", 1)[1]
        with Image.open(BytesIO(base64.b64decode(encoded_image))) as sent_image:
            self.assertNotIn("Author", sent_image.info)

        with self.module.db() as conn:
            row = conn.execute(
                "SELECT id, evidence_paths, assessment_source, assessment_model FROM cases"
            ).fetchone()
            case_id = row["id"]
            filenames = json.loads(row["evidence_paths"])
            evidence_metadata = conn.execute(
                "SELECT * FROM case_evidence WHERE case_id=?", (case_id,)
            ).fetchone()
        self.assertEqual(len(filenames), 1)
        self.assertEqual((self.module.UPLOAD_DIR / filenames[0]).read_bytes(), image_bytes)
        self.assertEqual(evidence_metadata["original_name"], "leaf.png")
        self.assertEqual(evidence_metadata["sha256"], hashlib.sha256(image_bytes).hexdigest())
        self.assertEqual(row["assessment_source"], "Meta Model API")
        self.assertEqual(row["assessment_model"], "muse-spark-1.3")
        self.assertIn(b"SHA-256", self.client.get(f"/cases/{case_id}").data)

        evidence = self.client.get(f"/cases/{case_id}/evidence/{filenames[0]}")
        self.assertEqual(evidence.status_code, 200)
        self.assertEqual(evidence.mimetype, "image/png")
        self.assertEqual(evidence.headers["Cache-Control"], "private, no-store")
        evidence.close()
        self.assertEqual(
            self.client.get(f"/cases/{case_id + 1}/evidence/{filenames[0]}").status_code,
            404,
        )
        self.assertIn(b"Field photographs", self.client.get(f"/cases/{case_id}").data)

    def test_jpeg_metadata_is_removed_before_meta_analysis(self):
        image = Image.new("RGB", (4, 4), color=(40, 120, 60))
        exif = Image.Exif()
        exif[315] = "Private Reporter Name"
        image_buffer = BytesIO()
        image.save(image_buffer, format="JPEG", exif=exif)

        sanitized = self.module._image_without_metadata(
            "image/jpeg", image_buffer.getvalue()
        )
        with Image.open(BytesIO(sanitized)) as meta_image:
            self.assertEqual(dict(meta_image.getexif()), {})

    def test_rejects_image_with_mismatched_contents(self):
        with patch.object(self.module, "analyze_with_meta") as analyze:
            response = self.client.post(
                "/cases/new",
                data={
                    "farm_name": "Demo Farm",
                    "reporter_name": "Field Officer",
                    "location": "Demo District",
                    "crop": "Maize",
                    "issue_type": "Visible crop change",
                    "description": "Yellowing leaves.",
                    "district": "Central Demo District",
                    "observed_at": self.module.datetime.now(
                        self.module.timezone.utc
                    ).date().isoformat(),
                    "latitude": "-1.95",
                    "longitude": "30.06",
                    "photos": (BytesIO(b"not a PNG"), "leaf.png", "image/png"),
                },
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"contents do not match", response.data)
        analyze.assert_not_called()
        with self.module.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0], 0)

    def test_officer_review_records_corrections_and_audit_history(self):
        case_id = self.create_case()
        with self.module.db() as conn:
            conn.execute(
                "UPDATE cases SET hypotheses=? WHERE id=?",
                (json.dumps(["Waterlogging is a possibility."]), case_id),
            )

        invalid = self.client.post(
            f"/cases/{case_id}/review",
            data={
                "reviewer": "Officer One",
                "decision": "verified",
                "reviewed_summary": "Verified summary.",
                "reviewed_observations": "Yellowing leaves observed.",
                "reviewed_urgency": "Soon",
                "reviewed_missing_information": "Affected area.",
                "reviewed_steps": "Visit field.",
                "reviewed_follow_up_questions": "When did this start?",
                "reviewed_uncertainty": "Cause not known.",
                "hypothesis_decision_0": "not-a-choice",
                "hypothesis_text_0": "Waterlogging.",
            },
        )
        self.assertEqual(invalid.status_code, 302)
        with self.module.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM case_reviews").fetchone()[0], 0)

        response = self.client.post(
            f"/cases/{case_id}/review",
            data={
                "reviewer": "Officer One",
                "decision": "follow_up",
                "reviewed_summary": "Observed yellowing; cause remains undetermined.",
                "reviewed_observations": "Yellowing leaves observed.\nAfter heavy rain.",
                "reviewed_urgency": "Soon",
                "reviewed_missing_information": "Affected area is still unknown.",
                "reviewed_steps": "Visit field.\nTake follow-up photos.",
                "reviewed_follow_up_questions": "When did symptoms begin?",
                "reviewed_uncertainty": "Cause remains undetermined pending inspection.",
                "hypothesis_decision_0": "unresolved",
                "hypothesis_text_0": "Waterlogging remains unconfirmed.",
                "notes": "Check soil moisture during field visit.",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.module.db() as conn:
            case = conn.execute(
                "SELECT review_status, ai_summary FROM cases WHERE id=?", (case_id,)
            ).fetchone()
            review = conn.execute(
                "SELECT * FROM case_reviews WHERE case_id=?", (case_id,)
            ).fetchone()

        self.assertEqual(case["review_status"], "Follow Up")
        self.assertIn("Demo Farm", case["ai_summary"])
        self.assertEqual(review["reviewer"], "Officer One")
        original = json.loads(review["original_assessment"])
        reviewed = json.loads(review["reviewed_assessment"])
        self.assertIn("Waterlogging is a possibility.", original["hypotheses"])
        self.assertEqual(reviewed["hypotheses"][0]["disposition"], "unresolved")
        self.assertEqual(reviewed["urgency"], "Soon")
        self.assertEqual(reviewed["steps"], ["Visit field.", "Take follow-up photos."])
        self.assertEqual(reviewed["follow_up_questions"], ["When did symptoms begin?"])
        self.assertEqual(reviewed["observations"], [
            "Yellowing leaves observed.", "After heavy rain."
        ])
        detail = self.client.get(f"/cases/{case_id}")
        self.assertIn(b"Officer review", detail.data)
        self.assertIn(b"Compare with original AI assessment", detail.data)
        self.assertIn(b"Waterlogging remains unconfirmed.", detail.data)

    def test_field_actions_record_dates_and_outcomes(self):
        case_id = self.create_case()
        add_response = self.client.post(
            f"/cases/{case_id}/tasks",
            data={"title": "Inspect the field", "due_date": "2026-11-03"},
        )
        self.assertEqual(add_response.status_code, 302)
        with self.module.db() as conn:
            task = conn.execute(
                "SELECT * FROM tasks WHERE case_id=? AND title='Inspect the field'",
                (case_id,),
            ).fetchone()
            task_id = task["id"]
            self.assertEqual(task["due_date"], "2026-11-03")

        rejected = self.client.post(f"/tasks/{task_id}/toggle", data={"outcome": ""})
        self.assertEqual(rejected.status_code, 302)
        with self.module.db() as conn:
            self.assertEqual(
                conn.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()[0],
                "Pending",
            )

        self.client.post(
            f"/tasks/{task_id}/toggle",
            data={"outcome": "Visited field; affected area was smaller than first reported."},
        )
        with self.module.db() as conn:
            task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            self.assertEqual(task["status"], "Completed")
            self.assertIn("smaller than first reported", task["outcome"])
        self.assertIn(b"smaller than first reported", self.client.get(f"/cases/{case_id}").data)

    def test_dashboard_summarizes_unresolved_patterns(self):
        verified_case_id = self.create_case()
        self.create_case()
        self.client.post(
            f"/cases/{verified_case_id}/review",
            data={
                "reviewer": "Officer One",
                "decision": "verified",
                "reviewed_summary": "Field notes were reviewed.",
                "reviewed_observations": "Yellowing leaves confirmed by officer.",
                "reviewed_urgency": "Soon",
                "reviewed_missing_information": "Affected area.",
                "reviewed_steps": "Continue field monitoring.",
                "reviewed_follow_up_questions": "Has the yellowing spread?",
                "reviewed_uncertainty": "Cause not determined.",
            },
        )
        dashboard = self.client.get("/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"GEOGRAPHIC DISTRIBUTION", dashboard.data)
        self.assertIn(b"VERIFIED OBSERVATIONS", dashboard.data)
        self.assertIn(b"Yellowing leaves confirmed by officer.", dashboard.data)
        self.assertIn(b"Open reports by crop and issue", dashboard.data)
        self.assertIn(b"Demo District", dashboard.data)
        self.assertIn(b"Awaiting officer review", dashboard.data)

    def test_primary_intelligence_pages_render(self):
        self.create_case()
        for path in (
            "/",
            "/field-reports",
            "/intelligence",
            "/risk-map",
            "/verification",
            "/operations",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_spatial_clusters_observe_distance_and_time_limits(self):
        first_id = self.create_case()
        nearby_id = self.create_case()
        far_id = self.create_case()
        stale_id = self.create_case()
        today = self.module.datetime.now(self.module.timezone.utc).date()
        with self.module.db() as conn:
            conn.execute(
                "UPDATE cases SET latitude=-1.95, longitude=30.06, observed_at=? WHERE id=?",
                (today.isoformat(), first_id),
            )
            conn.execute(
                "UPDATE cases SET latitude=-1.96, longitude=30.07, observed_at=? WHERE id=?",
                (today.isoformat(), nearby_id),
            )
            conn.execute(
                "UPDATE cases SET latitude=-1.95, longitude=30.50, observed_at=? WHERE id=?",
                (today.isoformat(), far_id),
            )
            conn.execute(
                "UPDATE cases SET latitude=-1.95, longitude=30.06, observed_at=? WHERE id=?",
                ((today - self.module.timedelta(days=20)).isoformat(), stale_id),
            )
            cases = conn.execute("SELECT * FROM cases ORDER BY id").fetchall()
        clusters = self.module.build_risk_clusters(cases)
        self.assertEqual(len(clusters), 1)
        self.assertEqual({row["id"] for row in clusters[0]["reports"]}, {first_id, nearby_id})
        self.assertIn("not an outbreak probability", clusters[0]["explanation"])
        self.assertGreaterEqual(clusters[0]["signal"], 0)
        self.assertLessEqual(clusters[0]["signal"], 100)

    def test_location_metadata_validation_rejects_partial_or_future_coordinates(self):
        today = self.module.datetime.now(self.module.timezone.utc).date()
        base = {
            "district": "Central Demo District",
            "observed_at": today.isoformat(),
            "latitude": "-1.95",
            "longitude": "30.06",
        }
        self.assertEqual(
            self.module._validate_observation_metadata(base),
            ("Central Demo District", today.isoformat(), -1.95, 30.06),
        )
        with self.assertRaisesRegex(ValueError, "both coordinates"):
            self.module._validate_observation_metadata({**base, "longitude": ""})
        with self.assertRaisesRegex(ValueError, "Latitude"):
            self.module._validate_observation_metadata({**base, "latitude": "91"})
        with self.assertRaisesRegex(ValueError, "future"):
            self.module._validate_observation_metadata({
                **base,
                "observed_at": (today + self.module.timedelta(days=1)).isoformat(),
            })

    def test_synthetic_seed_is_explicit_and_repeat_safe(self):
        self.assertEqual(self.module.seed_demo_data(), 24)
        with self.module.db() as conn:
            synthetic_count = conn.execute(
                "SELECT COUNT(*) FROM cases WHERE is_synthetic=1"
            ).fetchone()[0]
            pending_count = conn.execute(
                "SELECT COUNT(*) FROM cases WHERE is_synthetic=1 AND review_status='Pending review'"
            ).fetchone()[0]
            districts = conn.execute(
                "SELECT COUNT(DISTINCT district) FROM cases WHERE is_synthetic=1"
            ).fetchone()[0]
            cases = conn.execute(
                "SELECT * FROM cases WHERE is_synthetic=1"
            ).fetchall()
        self.assertEqual(synthetic_count, 24)
        self.assertEqual(pending_count, 6)
        self.assertEqual(districts, 3)
        self.assertEqual(len(self.module.build_risk_clusters(cases)), 2)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.module.seed_demo_data()
        with self.module.db() as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM cases WHERE is_synthetic=1").fetchone()[0],
                24,
            )
        overview = self.client.get("/")
        self.assertIn(b"24 reports are labelled as fictional UI scenarios", overview.data)

    def test_synthetic_seed_refuses_a_nonempty_database(self):
        self.create_case()
        with self.assertRaisesRegex(ValueError, "empty database"):
            self.module.seed_demo_data()
        with self.module.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0], 1)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM cases WHERE is_synthetic=1").fetchone()[0],
                0,
            )

    def test_meta_assessment_is_parsed_and_validated(self):
        payload = {
            "summary": "A maize report needs field verification.",
            "urgency": "Soon",
            "observations": ["Yellowing leaves after heavy rain."],
            "hypotheses": ["Waterlogging is one possibility; it is unconfirmed."],
            "missing_information": ["Affected area and onset are not known."],
            "follow_up_questions": ["When did the symptoms first appear?"],
            "steps": ["Confirm onset.", "Estimate affected area.", "Arrange field review."],
            "uncertainty": "The report alone cannot establish the cause.",
        }
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text=json.dumps(payload),
            model="muse-spark-1.3",
        )
        case_data = {
            "farm_name": "PRIVATE FARM ALPHA",
            "reporter_name": "PRIVATE REPORTER BETA",
            "location": "PRIVATE LOCATION GAMMA",
            "district": "PRIVATE DISTRICT DELTA",
            "latitude": "-1.95",
            "longitude": "30.06",
            "observation_ref": "OBS-PRIVATE-1234",
            "crop": "Maize",
            "issue_type": "Visible crop change",
            "observed_at": "2026-10-30",
            "description": (
                "PRIVATE REPORTER BETA saw yellowing at PRIVATE FARM ALPHA "
                "near PRIVATE LOCATION GAMMA."
            ),
        }
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key", "META_MODEL_ID": "test-model"}):
            with patch("openai.OpenAI", return_value=client) as openai_client:
                result = self.module.analyze_with_meta(
                    case_data
                )

        self.assertEqual(result["mode"], "Meta Model API")
        self.assertEqual(result["model"], "muse-spark-1.3")
        self.assertEqual(result["urgency"], "Soon")
        self.assertEqual(len(result["steps"]), 3)
        self.assertEqual(result["follow_up_questions"], payload["follow_up_questions"])
        openai_client.assert_called_once_with(
            api_key="test-key",
            base_url="https://api.meta.ai/v1",
            timeout=60.0,
            max_retries=1,
        )
        self.assertEqual(
            client.responses.create.call_args.kwargs["model"], "test-model"
        )
        request = client.responses.create.call_args.kwargs
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        prompt = request["input"][0]["content"][0]["text"]
        for private_value in (
            "PRIVATE FARM ALPHA",
            "PRIVATE REPORTER BETA",
            "PRIVATE LOCATION GAMMA",
            "PRIVATE DISTRICT DELTA",
            "OBS-PRIVATE-1234",
            "-1.95",
            "30.06",
        ):
            self.assertNotIn(private_value, prompt)
        self.assertIn("[redacted]", prompt)

    def test_invalid_meta_assessment_uses_labelled_fallback(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text='{"summary":"Bad result","urgency":"Critical"}'
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}):
            with patch("openai.OpenAI", return_value=client):
                with self.assertLogs("app", level="WARNING"):
                    result = self.module.analyze_with_meta(
                        {
                            "farm_name": "Demo Farm",
                            "reporter_name": "Field Officer",
                            "location": "Demo District",
                            "crop": "Maize",
                            "issue_type": "Visible crop change",
                            "description": "Yellowing leaves after heavy rain.",
                        }
                    )

        self.assertEqual(result["mode"], "Fallback mode — Meta API request failed")
        self.assertIn("ValueError", result["uncertainty"])
        self.assertTrue(result["follow_up_questions"])

    def test_existing_database_is_migrated_without_losing_cases(self):
        old_db_path = Path(self.temp_dir.name) / "old-farmops.db"
        with closing(sqlite3.connect(old_db_path)) as conn:
            with conn:
                conn.execute("""
                    CREATE TABLE cases (
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
                    CREATE TABLE tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        case_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        due_date TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'Pending',
                        created_at TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    INSERT INTO tasks (case_id, title, created_at)
                    VALUES (1, 'Legacy task', '2026-01-01Z')
                """)
                conn.execute("""
                    INSERT INTO cases (
                        farm_name, reporter_name, location, crop, issue_type, description,
                        created_at
                    ) VALUES (
                        'Saved Farm', 'Officer', 'District', 'Maize', 'Other',
                        'Old report', '2026-01-01Z'
                    )
                """)

        original_db_path = self.module.DB_PATH
        try:
            self.module.DB_PATH = old_db_path
            self.module.init_db()
            with self.module.db() as conn:
                row = conn.execute("SELECT * FROM cases WHERE farm_name='Saved Farm'").fetchone()
                self.assertEqual(row["description"], "Old report")
                self.assertEqual(json.loads(row["observations"]), [])
                self.assertEqual(json.loads(row["follow_up_questions"]), [])
                self.assertEqual(row["observation_ref"], "")
                self.assertEqual(row["assessment_source"], "")
                self.assertEqual(row["assessment_model"], "")
                task = conn.execute("SELECT * FROM tasks WHERE title='Legacy task'").fetchone()
                self.assertEqual(task["outcome"], "")
        finally:
            self.module.DB_PATH = original_db_path

    def test_dotenv_loading_respects_process_environment_precedence(self):
        env_file = Path(self.temp_dir.name) / "test.env"
        env_file.write_text("MODEL_API_KEY=dotenv-test-key\n", encoding="utf-8")
        with patch.dict(os.environ, {"MODEL_API_KEY": "process-test-key"}):
            self.module.load_environment(env_file)
            self.assertEqual(os.environ["MODEL_API_KEY"], "process-test-key")
            os.environ.pop("MODEL_API_KEY")
            self.module.load_environment(env_file)
            self.assertEqual(os.environ["MODEL_API_KEY"], "dotenv-test-key")


if __name__ == "__main__":
    unittest.main()
