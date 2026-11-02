import base64
import re
import hashlib
import httpx
import json
import openai
import importlib
import os
import sqlite3
import tempfile
import unittest
import wave
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
             "evidence_requested", "evidence_requested", "evidence_requested",
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
        case_id = self.create_case()
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
                self.assertIn(b"primary-sidebar", response.data)

        overview = self.client.get("/")
        self.assertIn(b"National Agricultural Intelligence Operations Centre", overview.data)
        self.assertNotIn(b"Data Sources", overview.data)
        self.assertNotIn(b"PLANNED", overview.data)
        self.assertIn(b"Response Operations", overview.data)
        self.assertIn(b"overview-map", overview.data)
        with self.module.db() as conn:
            case = conn.execute(
                "SELECT latitude, longitude FROM cases WHERE id=?", (case_id,)
            ).fetchone()
        match = re.search(
            rb'<script id="overview-geojson" type="application/json">(.*?)</script>',
            overview.data,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        geojson = json.loads(match.group(1))
        report_feature = next(
            feature for feature in geojson["features"]
            if feature["properties"].get("case_id") == case_id
        )
        self.assertEqual(
            report_feature["geometry"]["coordinates"],
            [case["longitude"], case["latitude"]],
        )
        detail = self.client.get(f"/cases/{case_id}")
        self.assertIn(b"Source evidence", detail.data)
        self.assertIn(b"Missing evidence", detail.data)
        self.assertIn(b"source-demo", detail.data)

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

    def test_blank_model_id_falls_back_to_default(self):
        payload = {
            "summary": "A maize report needs field verification.",
            "urgency": "Soon",
            "observations": ["Yellowing leaves after heavy rain."],
            "hypotheses": [],
            "missing_information": ["Affected area is not known."],
            "follow_up_questions": ["When did the symptoms first appear?"],
            "steps": ["Confirm onset.", "Estimate affected area.", "Arrange field review."],
            "uncertainty": "The report alone cannot establish the cause.",
        }
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text=json.dumps(payload),
            model="muse-spark-1.3",
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key", "META_MODEL_ID": "  "}):
            with patch("openai.OpenAI", return_value=client):
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
        self.assertEqual(result["mode"], "Meta Model API")
        self.assertEqual(client.responses.create.call_args.kwargs["model"], "muse-spark-1.3")

    def test_whitespace_api_key_uses_demo_mode_without_calling_meta(self):
        with patch.dict(os.environ, {"MODEL_API_KEY": "   "}):
            with patch("openai.OpenAI") as openai_client:
                with self.assertLogs("app", level="INFO"):
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
        self.assertTrue(result["mode"].startswith("DEMO MODE"))
        openai_client.assert_not_called()

    def test_intake_trend_buckets_reports_by_observed_day(self):
        trend = self.module.build_intake_trend(
            [
                {"observed_at": "2026-10-30", "created_at": "2026-10-30T00:00:00Z", "urgency": "Soon"},
                {"observed_at": "2026-10-30", "created_at": "2026-10-30T00:00:00Z", "urgency": "Urgent field review"},
                {"observed_at": "", "created_at": "2026-10-29T00:00:00Z", "urgency": "Routine"},
                {"observed_at": "not-a-date", "created_at": "also-bad", "urgency": "Soon"},
            ],
            days=3,
            today=self.module.datetime(2026, 10, 30).date(),
        )
        self.assertEqual([day["date"] for day in trend], ["2026-10-28", "2026-10-29", "2026-10-30"])
        self.assertEqual(trend[2]["total"], 2)
        self.assertEqual(trend[2]["urgent"], 1)
        self.assertEqual(trend[1]["total"], 1)
        self.assertEqual(trend[0]["total"], 0)

    def test_urgency_mix_uses_fixed_severity_order(self):
        mix = self.module.build_urgency_mix([
            {"urgency": "Routine"},
            {"urgency": "Soon"},
            {"urgency": "Soon"},
            {"urgency": "Bogus"},
        ])
        self.assertEqual(
            [(row["level"], row["count"]) for row in mix],
            [("Urgent field review", 0), ("Soon", 2), ("Needs review", 0), ("Routine", 1)],
        )

    def test_overview_exposes_analytics_data(self):
        self.create_case()
        overview = self.client.get("/")
        self.assertEqual(overview.status_code, 200)
        self.assertIn(b"trend-data", overview.data)
        self.assertIn(b"DISTRICT RANKING", overview.data)
        self.assertIn(b"Urgency mix", overview.data)
        self.assertIn(b"OPERATIONS WATCH", overview.data)
        self.assertIn(b"Evidence depth", overview.data)
        self.assertIn(b"theme-toggle", overview.data)
        self.assertIn(b"farmops-theme", overview.data)
        self.assertIn(b"First reports from", overview.data)

    def test_watch_signals_flag_intake_spike(self):
        day = self.module.datetime(2026, 11, 1).date()
        cases = [
            {"observed_at": "2026-10-31", "created_at": "2026-10-31T00:00:00Z",
             "urgency": "Soon", "status": "Open", "district": "Same District"},
            {"observed_at": "2026-11-01", "created_at": "2026-11-01T00:00:00Z",
             "urgency": "Soon", "status": "Open", "district": "Same District"},
            {"observed_at": "2026-11-01", "created_at": "2026-11-01T00:00:00Z",
             "urgency": "Soon", "status": "Open", "district": "Same District"},
            {"observed_at": "2026-10-30", "created_at": "2026-10-30T00:00:00Z",
             "urgency": "Soon", "status": "Open", "district": "Same District"},
            {"observed_at": "2026-10-30", "created_at": "2026-10-30T00:00:00Z",
             "urgency": "Soon", "status": "Open", "district": "Same District"},
            {"observed_at": "2026-10-20", "created_at": "2026-10-20T00:00:00Z",
             "urgency": "Routine", "status": "Open", "district": "Same District"},
        ]
        signals = self.module.build_watch_signals(cases, [], today=day)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["title"], "Intake spike")
        self.assertEqual(signals[0]["level"], "watch")
        self.assertEqual(signals[0]["endpoint"], "field_reports")

    def test_watch_signals_flag_urgent_backlog_and_new_district(self):
        day = self.module.datetime(2026, 11, 1).date()
        cases = [
            {"observed_at": "2026-11-01", "created_at": "2026-11-01T00:00:00Z",
             "urgency": "Urgent field review", "status": "Open", "district": "Old District"},
            {"observed_at": "2026-11-01", "created_at": "2026-11-01T00:00:00Z",
             "urgency": "Urgent field review", "status": "Open", "district": "Old District"},
            {"observed_at": "2026-10-10", "created_at": "2026-10-10T00:00:00Z",
             "urgency": "Routine", "status": "Open", "district": "Old District"},
            {"observed_at": "2026-11-01", "created_at": "2026-11-01T00:00:00Z",
             "urgency": "Soon", "status": "Open", "district": "Brand New District"},
        ]
        signals = self.module.build_watch_signals(cases, [], today=day)
        self.assertEqual(
            [signal["title"] for signal in signals],
            ["Urgent field reviews pending", "First reports from a new district"],
        )

    def test_watch_signals_flag_strong_cluster(self):
        day = self.module.datetime(2026, 11, 1).date()
        signals = self.module.build_watch_signals(
            [],
            [{"signal": 90, "signal_label": "Strong linkage signal",
              "crop": "Maize", "count": 8, "explanation": "Eight linked reports."}],
            today=day,
        )
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["level"], "elevated")
        self.assertEqual(signals[0]["endpoint"], "intelligence_cases")
        self.assertIn("Maize", signals[0]["title"])

    def test_watch_signals_quiet_when_baseline_calms(self):
        day = self.module.datetime(2026, 11, 1).date()
        signals = self.module.build_watch_signals(
            [
                {"observed_at": "2026-10-01", "created_at": "2026-10-01T00:00:00Z",
                 "urgency": "Routine", "status": "Open", "district": "Known District"},
                {"observed_at": "2026-11-01", "created_at": "2026-11-01T00:00:00Z",
                 "urgency": "Routine", "status": "Open", "district": "Known District"},
            ],
            [],
            today=day,
        )
        self.assertEqual(signals, [])

    def test_evidence_details_validation(self):
        valid = {
            "affected_area_value": "2.5",
            "affected_area_unit": "hectares",
            "field_position": "Northwest corner",
            "proportion_affected": "10-25%",
            "growth_stage": "Flowering",
            "variety": "Longe 5",
            "planting_date": "2026-09-01",
            "drainage": "Poor",
            "standing_water": "Yes",
            "soil_note": "Clay near the stream.",
            "recent_weather": "Heavy rain for two days.",
        }
        cleaned = self.module._validate_evidence_details(valid)
        self.assertEqual(cleaned["affected_area_value"], 2.5)
        self.assertEqual(cleaned["proportion_affected"], "10-25%")
        self.assertEqual(
            self.module._validate_evidence_details({})["affected_area_value"], None
        )
        with self.assertRaisesRegex(ValueError, "positive number"):
            self.module._validate_evidence_details({"affected_area_value": "-1"})
        with self.assertRaisesRegex(ValueError, "number"):
            self.module._validate_evidence_details({"affected_area_value": "lots"})
        with self.assertRaisesRegex(ValueError, "area unit"):
            self.module._validate_evidence_details({"affected_area_unit": "parsecs"})
        future = (self.module.datetime.now(self.module.timezone.utc).date()
                  + self.module.timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "future"):
            self.module._validate_evidence_details({"planting_date": future})
        with self.assertRaisesRegex(ValueError, "120 characters"):
            self.module._validate_evidence_details({"variety": "x" * 121})

    def test_new_case_saves_evidence_details(self):
        response = self.client.post("/cases/new", data={
            "farm_name": "Demo Farm",
            "reporter_name": "Field Officer",
            "location": "Demo District",
            "crop": "Maize",
            "issue_type": "Visible crop change",
            "description": "Yellowing leaves after heavy rain.",
            "district": "Central Demo District",
            "observed_at": self.module.datetime.now(
                self.module.timezone.utc).date().isoformat(),
            "affected_area_value": "2.5",
            "affected_area_unit": "hectares",
            "field_position": "Northwest corner",
            "proportion_affected": "10-25%",
            "growth_stage": "Flowering",
            "variety": "Longe 5",
            "drainage": "Poor",
            "standing_water": "Yes",
        })
        self.assertEqual(response.status_code, 302)
        with self.module.db() as conn:
            row = conn.execute(
                "SELECT affected_area_value, affected_area_unit, growth_stage,"
                " standing_water FROM cases").fetchone()
        self.assertEqual(row["affected_area_value"], 2.5)
        self.assertEqual(row["affected_area_unit"], "hectares")
        self.assertEqual(row["growth_stage"], "Flowering")
        self.assertEqual(row["standing_water"], "Yes")

    def test_labeled_photo_slots_store_shot_types(self):
        image_bytes = b"\x89PNG\r\n\x1a\nfake-image-data"
        with patch.dict(os.environ, {"MODEL_API_KEY": ""}):
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
                        self.module.timezone.utc).date().isoformat(),
                    "photos_overview": (BytesIO(image_bytes), "wide.png", "image/png"),
                    "photos_detail": (BytesIO(image_bytes), "leaf.png", "image/png"),
                },
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 302)
        with self.module.db() as conn:
            shots = [row["shot_type"] for row in conn.execute(
                "SELECT shot_type FROM case_evidence ORDER BY id")]
        self.assertEqual(shots, ["overview", "detail"])

    def test_photo_cap_is_four(self):
        image_bytes = b"\x89PNG\r\n\x1a\nfake-image-data"
        files = [("photos", (BytesIO(image_bytes), "leaf%d.png" % i, "image/png"))
                 for i in range(5)]
        data = {
            "farm_name": "Demo Farm",
            "reporter_name": "Field Officer",
            "location": "Demo District",
            "crop": "Maize",
            "issue_type": "Visible crop change",
            "description": "Yellowing leaves.",
            "district": "Central Demo District",
            "observed_at": self.module.datetime.now(
                self.module.timezone.utc).date().isoformat(),
        }
        with patch.dict(os.environ, {"MODEL_API_KEY": ""}):
            response = self.client.post(
                "/cases/new", data=dict(data, photos=[f[1] for f in files]),
                content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"no more than 4", response.data)

    def test_meta_payload_includes_structured_evidence(self):
        payload = {
            "summary": "A maize report needs field verification.",
            "urgency": "Soon",
            "observations": ["Yellowing leaves after heavy rain."],
            "hypotheses": [],
            "missing_information": ["Affected area is not known."],
            "follow_up_questions": ["When did the symptoms first appear?"],
            "steps": ["Confirm onset.", "Estimate affected area.", "Arrange field review."],
            "uncertainty": "The report alone cannot establish the cause.",
        }
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text=json.dumps(payload), model="muse-spark-1.3"
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}):
            with patch("openai.OpenAI", return_value=client):
                result = self.module.analyze_with_meta(
                    {
                        "farm_name": "Secret Farm",
                        "reporter_name": "Secret Reporter",
                        "location": "Demo District",
                        "crop": "Maize",
                        "issue_type": "Visible crop change",
                        "description": "Yellowing leaves after heavy rain.",
                        "growth_stage": "Flowering",
                        "variety": "Longe 5",
                        "affected_area_value": 2.5,
                        "affected_area_unit": "hectares",
                        "drainage": "Poor",
                    }
                )
        self.assertEqual(result["mode"], "Meta Model API")
        prompt_text = client.responses.create.call_args.kwargs["input"][0]["content"][0]["text"]
        self.assertIn("Flowering", prompt_text)
        self.assertIn("Longe 5", prompt_text)
        self.assertIn("2.5", prompt_text)
        self.assertNotIn("Secret Reporter", prompt_text)

    def test_initial_assessment_run_is_recorded(self):
        case_id = self.create_case()
        with self.module.db() as conn:
            runs = conn.execute(
                "SELECT run_number, source, assessment_json FROM assessment_runs"
                " WHERE case_id=? ORDER BY run_number", (case_id,)).fetchall()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["run_number"], 1)
        self.assertIn("DEMO MODE", runs[0]["source"])
        stored = json.loads(runs[0]["assessment_json"])
        self.assertIn("Demo Farm", stored["summary"])

    def test_evidence_tasks_carry_evidence_kind(self):
        case_id = self.create_case()
        with self.module.db() as conn:
            kinds = sorted(row["kind"] for row in conn.execute(
                "SELECT kind FROM tasks WHERE case_id=?", (case_id,)).fetchall())
        self.assertEqual(kinds, ["action"] * 5 + ["evidence"] * 3)

    def test_follow_up_evidence_and_reassessment(self):
        case_id = self.create_case()
        response = self.client.post(
            f"/cases/{case_id}/evidence",
            data={"author": "Field Officer",
                  "note": "Affected area measured at 2 hectares on revisit."})
        self.assertEqual(response.status_code, 302)
        self.assertIn(b"Affected area measured", self.client.get(f"/cases/{case_id}").data)
        with patch.dict(os.environ, {"MODEL_API_KEY": ""}):
            rerun = self.client.post(f"/cases/{case_id}/reassess")
        self.assertEqual(rerun.status_code, 302)
        with self.module.db() as conn:
            runs = conn.execute(
                "SELECT run_number FROM assessment_runs WHERE case_id=? ORDER BY run_number",
                (case_id,)).fetchall()
            self.assertEqual([row["run_number"] for row in runs], [1, 2])
            events = conn.execute(
                "SELECT event_type FROM case_events WHERE case_id=? AND event_type IN"
                " ('evidence_added','assessment_rerun') ORDER BY id", (case_id,)).fetchall()
        self.assertEqual([row["event_type"] for row in events],
                         ["evidence_added", "assessment_rerun"])
        self.assertIn(b"Assessment history", self.client.get(f"/cases/{case_id}").data)

    def test_evidence_completeness_counts_new_dimensions(self):
        full = {
            "description": "Yellowing leaves.",
            "observed_at": "2026-11-01",
            "district": "Central",
            "location": "Sector 1",
            "latitude": -1.95,
            "longitude": 30.06,
            "evidence_paths": ["a.png"],
            "affected_area_value": 2.5,
            "growth_stage": "Flowering",
            "drainage": "Poor",
        }
        self.assertEqual(self.module.evidence_completeness(full), 100)
        thin = {"description": "Yellowing leaves.", "observed_at": "2026-11-01"}
        self.assertEqual(self.module.evidence_completeness(thin), 25)

    def test_verification_queue_prioritizes_thin_evidence(self):
        thin_id = self.create_case(crop="Beans")
        self.client.post("/cases/new", data={
            "farm_name": "Demo Farm",
            "reporter_name": "Field Officer",
            "location": "Demo District",
            "crop": "Maize",
            "issue_type": "Visible crop change",
            "description": "Yellowing leaves after heavy rain.",
            "district": "Central Demo District",
            "observed_at": self.module.datetime.now(
                self.module.timezone.utc).date().isoformat(),
            "latitude": "-1.95",
            "longitude": "30.06",
            "affected_area_value": "2",
            "affected_area_unit": "hectares",
            "growth_stage": "Flowering",
            "variety": "Longe 5",
            "drainage": "Good",
        })
        with self.module.db() as conn:
            rich_id = conn.execute("SELECT MAX(id) FROM cases").fetchone()[0]
        page = self.client.get("/verification").data.decode("utf-8")
        self.assertLess(page.index(f"/cases/{thin_id}"), page.index(f"/cases/{rich_id}"))

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
                self.assertEqual(row["growth_stage"], "")
                self.assertEqual(row["recent_weather"], "")
                self.assertIsNone(row["affected_area_value"])
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM assessment_runs").fetchone()[0], 0
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM case_notes").fetchone()[0], 0
                )
                task = conn.execute("SELECT * FROM tasks WHERE title='Legacy task'").fetchone()
                self.assertEqual(task["outcome"], "")
                self.assertEqual(task["kind"], "action")
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

    def _wav_bytes(self, seconds=0.2, rate=16000):
        buf = BytesIO()
        with wave.open(buf, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(b"\x00\x00" * int(seconds * rate))
        return buf.getvalue()

    def _voice_case_fields(self):
        return {
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
        }

    def test_voice_note_is_transcribed_and_enriches_assessment(self):
        payload = {
            "summary": "Review yellowing with the transcript context.",
            "urgency": "Needs review",
            "observations": ["Transcript mentions low corner."],
            "hypotheses": [],
            "missing_information": [],
            "follow_up_questions": [],
            "steps": ["Visit the low corner."],
            "uncertainty": "Transcript context is limited.",
        }
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text=json.dumps(payload)
        )
        transcript = "Yellow patches near the low corner after rain."
        asr = SimpleNamespace(status_code=200, json=lambda: {"transcript": transcript})
        fields = self._voice_case_fields()
        fields["voice_note"] = (
            BytesIO(self._wav_bytes()), "note.wav", "audio/wav",
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}):
            with patch("openai.OpenAI", return_value=client):
                with patch("app.requests") as asr_lib:
                    asr_lib.post.return_value = asr
                    response = self.client.post(
                        "/cases/new", data=fields,
                        content_type="multipart/form-data",
                    )
        self.assertEqual(response.status_code, 302)
        request_payload = json.loads(asr_lib.post.call_args.kwargs["files"]["request"][1])
        self.assertEqual(request_payload["model"], "muse-voice-transcribe-1.0")
        self.assertEqual(request_payload["audioEncoding"], "WAV")
        self.assertEqual(request_payload["mode"], "PUSH_TO_TALK")
        self.assertEqual(request_payload["keywords"], ["Maize", "Central Demo District"])
        self.assertIn(transcript, str(client.responses.create.call_args))
        with self.module.db() as conn:
            row = conn.execute(
                "SELECT id, evidence_paths FROM cases"
            ).fetchone()
            case_id = row["id"]
            filenames = json.loads(row["evidence_paths"])
            evidence = conn.execute(
                "SELECT * FROM case_evidence WHERE case_id=?", (case_id,)
            ).fetchone()
            note = conn.execute(
                "SELECT note FROM case_notes WHERE case_id=?", (case_id,)
            ).fetchone()
        self.assertEqual(len(filenames), 1)
        self.assertTrue(filenames[0].endswith(".wav"))
        self.assertEqual(evidence["shot_type"], "voice")
        self.assertEqual(evidence["original_name"], "note.wav")
        self.assertEqual(note["note"], transcript)
        detail = self.client.get(f"/cases/{case_id}").data
        self.assertIn(b"Field voice notes", detail)
        self.assertIn(b"<audio", detail)
        self.assertIn(transcript.encode(), detail)
        audio = self.client.get(f"/cases/{case_id}/evidence/{filenames[0]}")
        self.assertEqual(audio.status_code, 200)
        audio.close()

    def test_oversized_voice_note_is_rejected(self):
        fields = self._voice_case_fields()
        fields["voice_note"] = (
            BytesIO(b"x" * (10 * 1024 * 1024 + 1)), "long.wav", "audio/wav",
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": ""}):
            response = self.client.post(
                "/cases/new", data=fields, content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"exceeds the 10 MB", response.data)

    def test_non_audio_upload_is_rejected_as_voice_note(self):
        fields = self._voice_case_fields()
        fields["voice_note"] = (
            BytesIO(b"MZ fake binary"), "evil.exe", "application/octet-stream",
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": ""}):
            response = self.client.post(
                "/cases/new", data=fields, content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"unsupported audio type", response.data)

    def test_voice_note_without_api_key_is_stored_with_notice(self):
        fields = self._voice_case_fields()
        fields["voice_note"] = (
            BytesIO(self._wav_bytes()), "note.wav", "audio/wav",
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": ""}):
            response = self.client.post(
                "/cases/new", data=fields, content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 302)
        with self.module.db() as conn:
            row = conn.execute("SELECT id FROM cases").fetchone()
            note = conn.execute(
                "SELECT note FROM case_notes WHERE case_id=?", (row["id"],)
            ).fetchone()
        self.assertIn("stored", note["note"])
        self.assertIn("API key not configured", note["note"])
        self.assertIn(b"Field voice notes", self.client.get(f"/cases/{row['id']}").data)

    def test_follow_up_voice_note_is_stored(self):
        case_id = self.create_case()
        transcript = "Drainage ditch is blocked on the east side."
        asr = SimpleNamespace(status_code=200, json=lambda: {"transcript": transcript})
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}):
            with patch("app.requests") as asr_lib:
                asr_lib.post.return_value = asr
                response = self.client.post(
                    f"/cases/{case_id}/evidence",
                    data={
                        "note": "Evening revisit.",
                        "author": "Field Officer",
                        "voice_note": (
                            BytesIO(self._wav_bytes()), "revisit.wav",
                            "audio/wav",
                        ),
                    },
                    content_type="multipart/form-data",
                )
        self.assertEqual(response.status_code, 302)
        with self.module.db() as conn:
            paths = json.loads(conn.execute(
                "SELECT evidence_paths FROM cases WHERE id=?", (case_id,)
            ).fetchone()["evidence_paths"])
            evidence = conn.execute(
                "SELECT * FROM case_evidence WHERE case_id=?", (case_id,)
            ).fetchone()
            notes = conn.execute(
                "SELECT note FROM case_notes WHERE case_id=?", (case_id,)
            ).fetchall()
        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].endswith(".wav"))
        self.assertEqual(evidence["shot_type"], "voice")
        self.assertIn(transcript, [row["note"] for row in notes])
        self.assertIn(transcript.encode(), self.client.get(f"/cases/{case_id}").data)

    def test_voice_only_report_does_not_claim_photo_evidence(self):
        fields = self._voice_case_fields()
        fields["voice_note"] = (
            BytesIO(self._wav_bytes()), "note.wav", "audio/wav",
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": ""}):
            response = self.client.post(
                "/cases/new", data=fields, content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 302)
        with self.module.db() as conn:
            row = conn.execute("SELECT id FROM cases").fetchone()
        detail = self.client.get(f"/cases/{row['id']}").data
        self.assertNotIn(b"Field photographs", detail)
        self.assertIn(b"Field voice notes", detail)
        self.assertIn(b">50%</strong>", detail)

    def _assessment_payload(self, **overrides):
        payload = {
            "summary": "Summary A.",
            "urgency": "Soon",
            "observations": ["Observed yellowing."],
            "hypotheses": ["Possibly water stress."],
            "missing_information": ["Affected area size."],
            "follow_up_questions": ["When did it start?"],
            "steps": ["Step one.", "Step two.", "Step three."],
            "uncertainty": "Field verification needed.",
        }
        payload.update(overrides)
        return payload

    def _minimal_case_data(self):
        return {
            "farm_name": "Demo Farm",
            "reporter_name": "Field Officer",
            "location": "Demo District",
            "crop": "Maize",
            "issue_type": "Visible crop change",
            "description": "Yellowing leaves after heavy rain.",
        }

    def test_malformed_meta_response_uses_labelled_fallback(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text="{not valid json"
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}):
            with patch("openai.OpenAI", return_value=client):
                result = self.module.analyze_with_meta(self._minimal_case_data())
        self.assertEqual(result["mode"], "Fallback mode \u2014 Meta API request failed")
        self.assertIn("No AI assessment was produced", result["uncertainty"])
        self.assertIn("JSONDecodeError", result["uncertainty"])

    def test_meta_timeout_uses_labelled_fallback(self):
        client = Mock()
        client.responses.create.side_effect = openai.APITimeoutError(Mock())
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}):
            with patch("openai.OpenAI", return_value=client):
                result = self.module.analyze_with_meta(self._minimal_case_data())
        self.assertEqual(result["mode"], "Fallback mode \u2014 Meta API request failed")
        self.assertIn("APITimeoutError", result["uncertainty"])

    def test_meta_auth_failure_uses_labelled_fallback(self):
        client = Mock()
        client.responses.create.side_effect = openai.AuthenticationError(
            "bad key",
            response=httpx.Response(
                401, request=httpx.Request("POST", "https://api.meta.ai/v1/responses")
            ),
            body=None,
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}):
            with patch("openai.OpenAI", return_value=client):
                result = self.module.analyze_with_meta(self._minimal_case_data())
        self.assertEqual(result["mode"], "Fallback mode \u2014 Meta API request failed")
        self.assertIn("AuthenticationError (HTTP 401)", result["uncertainty"])

    def test_reassessment_excludes_voice_from_images(self):
        case_id = self.create_case()
        transcript = "Standing water in the low corner."
        asr = SimpleNamespace(status_code=200, json=lambda: {"transcript": transcript})
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}):
            with patch("app.requests") as asr_lib:
                asr_lib.post.return_value = asr
                follow = self.client.post(
                    f"/cases/{case_id}/evidence",
                    data={
                        "note": "Evening revisit.",
                        "author": "Field Officer",
                        "voice_note": (
                            BytesIO(self._wav_bytes()), "revisit.wav", "audio/wav",
                        ),
                    },
                    content_type="multipart/form-data",
                )
        self.assertEqual(follow.status_code, 302)
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text=json.dumps(self._assessment_payload())
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}):
            with patch("openai.OpenAI", return_value=client):
                rerun = self.client.post(f"/cases/{case_id}/reassess")
        self.assertEqual(rerun.status_code, 302)
        content = client.responses.create.call_args.kwargs["input"][0]["content"]
        self.assertFalse(any(item["type"] == "input_image" for item in content))
        self.assertIn(transcript, str(client.responses.create.call_args))
        with self.module.db() as conn:
            source = conn.execute(
                "SELECT assessment_source FROM cases WHERE id=?", (case_id,)
            ).fetchone()[0]
        self.assertEqual(source, "Meta Model API")

    def test_assessment_history_shows_run_changes(self):
        first = self._assessment_payload(
            summary="First summary.", urgency="Soon", observations=["One thing."]
        )
        second = self._assessment_payload(
            summary="Second summary.", urgency="Urgent field review",
            observations=["One thing.", "Another thing."],
        )
        client = Mock()
        client.responses.create.side_effect = [
            SimpleNamespace(output_text=json.dumps(first)),
            SimpleNamespace(output_text=json.dumps(second)),
        ]
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}):
            with patch("openai.OpenAI", return_value=client):
                created = self.client.post("/cases/new", data=self._voice_case_fields())
                self.assertEqual(created.status_code, 302)
                with self.module.db() as conn:
                    case_id = conn.execute("SELECT MAX(id) FROM cases").fetchone()[0]
                rerun = self.client.post(f"/cases/{case_id}/reassess")
                self.assertEqual(rerun.status_code, 302)
        detail = self.client.get(f"/cases/{case_id}").data
        self.assertIn(b"Initial assessment.", detail)
        self.assertIn("urgency Soon \u2192 Urgent field review".encode(), detail)
        self.assertIn(b"+1 observations", detail)
        self.assertIn(b"summary updated", detail)

    def _cluster_pair(self):
        first_id = self.create_case()
        nearby_id = self.create_case()
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
            cases = conn.execute("SELECT * FROM cases ORDER BY id").fetchall()
        return today, self.module.build_risk_clusters(cases)

    def test_cluster_explanation_names_match_criteria(self):
        today, clusters = self._cluster_pair()
        self.assertEqual(len(clusters), 1)
        explanation = clusters[0]["explanation"]
        self.assertIn("Maize", explanation)
        self.assertIn("Visible crop change", explanation)
        self.assertIn(today.isoformat(), explanation)
        self.assertIn("not an outbreak probability", explanation)

    def test_cluster_members_carry_inclusion_reasons(self):
        today, clusters = self._cluster_pair()
        self.assertEqual(len(clusters), 1)
        for report in clusters[0]["reports"]:
            reason = report.get("inclusion_reason", "")
            self.assertIn("km from the furthest member", reason)
            self.assertIn(today.isoformat(), reason)
        self.assertIn(b"km from the furthest member", self.client.get("/intelligence").data)

    def _review_payload(self, **overrides):
        payload = {
            "reviewer": "Officer One",
            "decision": "follow_up",
            "reviewed_summary": "Observed yellowing; cause remains undetermined.",
            "reviewed_observations": "Yellowing leaves confirmed.\nAfter heavy rain.",
            "reviewed_urgency": "Routine",
            "reviewed_missing_information": "Affected area is still unknown.",
            "reviewed_steps": "Visit field.\nTake follow-up photos.",
            "reviewed_follow_up_questions": "When did symptoms begin?",
            "reviewed_uncertainty": "Cause remains undetermined pending inspection.",
            "hypothesis_decision_0": "rejected",
            "hypothesis_text_0": "Waterlogging ruled out by drainage check.",
            "notes": "Check soil moisture during field visit.",
        }
        payload.update(overrides)
        return payload

    def test_review_audit_compares_original_and_verified(self):
        case_id = self.create_case()
        with self.module.db() as conn:
            conn.execute(
                "UPDATE cases SET urgency='Soon', observations=?, hypotheses=? WHERE id=?",
                (json.dumps(["AI saw yellowing."]), json.dumps(["Waterlogging is a possibility."]), case_id),
            )
        response = self.client.post(f"/cases/{case_id}/review", data=self._review_payload())
        self.assertEqual(response.status_code, 302)
        detail = self.client.get(f"/cases/{case_id}").data
        self.assertIn(b"AI-reported observations", detail)
        self.assertIn(b"AI saw yellowing.", detail)
        self.assertIn(b"Yellowing leaves confirmed.", detail)
        self.assertIn(b"AI hypotheses (tentative at the time)", detail)
        self.assertIn(b"Waterlogging is a possibility.", detail)
        self.assertIn(b"Waterlogging ruled out by drainage check.", detail)
        self.assertIn(b"Rejected:", detail)
        self.assertIn(b"(was Soon)", detail)
        self.assertIn(b"Original AI hypothesis: Waterlogging is a possibility.", detail)

    def test_reviews_are_append_only_with_decisions(self):
        case_id = self.create_case()
        first = self.client.post(
            f"/cases/{case_id}/review",
            data=self._review_payload(reviewer="Officer One", decision="follow_up"),
        )
        second = self.client.post(
            f"/cases/{case_id}/review",
            data=self._review_payload(
                reviewer="Officer Two", decision="verified",
                reviewed_summary="Second review confirms the report.",
            ),
        )
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        with self.module.db() as conn:
            rows = conn.execute(
                "SELECT reviewer, decision, created_at FROM case_reviews WHERE case_id=? ORDER BY id",
                (case_id,),
            ).fetchall()
            status = conn.execute(
                "SELECT review_status FROM cases WHERE id=?", (case_id,)
            ).fetchone()[0]
            events = conn.execute(
                "SELECT actor, details FROM case_events WHERE case_id=? AND event_type='officer_review' ORDER BY id",
                (case_id,),
            ).fetchall()
        self.assertEqual([(row["reviewer"], row["decision"]) for row in rows],
                         [("Officer One", "follow_up"), ("Officer Two", "verified")])
        self.assertTrue(all(row["created_at"] for row in rows))
        self.assertEqual(status, "Verified")
        self.assertEqual(
            [(event["actor"], json.loads(event["details"])["decision"]) for event in events],
            [("Officer One", "follow_up"), ("Officer Two", "verified")],
        )
        detail = self.client.get(f"/cases/{case_id}").data
        self.assertIn(b"Officer One", detail)
        self.assertIn(b"Officer Two", detail)

    def test_review_status_filter_and_clear(self):
        pending_id = self.create_case()
        verified_id = self.create_case()
        response = self.client.post(
            f"/cases/{verified_id}/review",
            data=self._review_payload(reviewer="Officer Two", decision="verified"),
        )
        self.assertEqual(response.status_code, 302)
        filtered = self.client.get("/field-reports?status=Verified").data
        self.assertIn(f"/cases/{verified_id}".encode(), filtered)
        self.assertNotIn(f"/cases/{pending_id}".encode(), filtered)
        self.assertIn(b"Clear filters", filtered)
        self.assertIn(b"All statuses", filtered)
        unfiltered = self.client.get("/field-reports").data
        self.assertIn(f"/cases/{pending_id}".encode(), unfiltered)
        self.assertIn(f"/cases/{verified_id}".encode(), unfiltered)
        self.assertNotIn(b"Clear filters", unfiltered)

    def test_ai_loading_states_present(self):
        intake = self.client.get("/cases/new").data
        self.assertIn(b"data-loading-text=", intake)
        self.assertIn(b"requesting assessment", intake)
        case_id = self.create_case()
        detail = self.client.get(f"/cases/{case_id}").data
        self.assertIn(b"Re-running assessment with latest evidence", detail)

    def test_provenance_shows_assessed_time(self):
        case_id = self.create_case()
        with self.module.db() as conn:
            created_at = conn.execute(
                "SELECT created_at FROM assessment_runs WHERE case_id=? ORDER BY run_number DESC",
                (case_id,),
            ).fetchone()[0]
        detail = self.client.get(f"/cases/{case_id}").data
        self.assertIn(b"assessed ", detail)
        self.assertIn(created_at.encode(), detail)

    def test_session_cookie_hardening(self):
        self.assertTrue(self.module.app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual(self.module.app.config["SESSION_COOKIE_SAMESITE"], "Lax")

    def test_evidence_route_rejects_traversal(self):
        case_id = self.create_case()
        self.assertEqual(
            self.client.get(f"/cases/{case_id}/evidence/..%2Fapp.py").status_code, 404
        )
        self.assertEqual(
            self.client.get(f"/cases/{case_id}/evidence/..%2F..%2F..%2Fenv").status_code, 404
        )

    def test_api_key_never_leaks_into_responses_or_logs(self):
        secret = "test-key-must-never-leak-12345"
        client = Mock()
        client.responses.create.side_effect = openai.APIConnectionError(request=Mock())
        with patch.dict(os.environ, {"MODEL_API_KEY": secret}):
            with patch("openai.OpenAI", return_value=client):
                with self.assertLogs("app", level="INFO") as captured:
                    created = self.client.post("/cases/new", data=self._voice_case_fields())
        self.assertEqual(created.status_code, 302)
        with self.module.db() as conn:
            case_id = conn.execute("SELECT MAX(id) FROM cases").fetchone()[0]
        detail = self.client.get(f"/cases/{case_id}").data
        self.assertNotIn(secret.encode(), detail)
        combined_logs = "\n".join(captured.output)
        self.assertNotIn(secret, combined_logs)

    def test_validate_defaults_missing_consistency_notes(self):
        result = self.module.validate_assessment(self._assessment_payload())
        self.assertEqual(result["consistency_notes"], [])
        with self.assertRaisesRegex(ValueError, "consistency_notes"):
            self.module.validate_assessment(
                self._assessment_payload(consistency_notes="not-a-list")
            )

    def test_consistency_notes_render_from_latest_run(self):
        payload = self._assessment_payload(consistency_notes=[
            "Voice transcript agrees with the written report.",
            "No photographs provided; visual check impossible.",
        ])
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text=json.dumps(payload)
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}):
            with patch("openai.OpenAI", return_value=client):
                created = self.client.post("/cases/new", data=self._voice_case_fields())
        self.assertEqual(created.status_code, 302)
        with self.module.db() as conn:
            case_id = conn.execute("SELECT MAX(id) FROM cases").fetchone()[0]
        detail = self.client.get(f"/cases/{case_id}").data
        self.assertIn(b"Evidence consistency", detail)
        self.assertIn(b"Voice transcript agrees with the written report.", detail)
        self.assertIn(b"visual check impossible", detail)

    def test_consistency_section_absent_without_notes(self):
        case_id = self.create_case()
        detail = self.client.get(f"/cases/{case_id}").data
        self.assertNotIn(b"Evidence consistency", detail)

    def test_consistency_prompt_requires_photo_restraint(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text=json.dumps(self._assessment_payload())
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}):
            with patch("openai.OpenAI", return_value=client):
                self.module.analyze_with_meta(self._minimal_case_data())
        prompt = str(client.responses.create.call_args)
        self.assertIn("Never state that a photograph confirms", prompt)
        self.assertIn("consistency_notes", prompt)

    def test_voice_transcribe_server_error_stores_notice(self):
        fields = self._voice_case_fields()
        fields["voice_note"] = (
            BytesIO(self._wav_bytes()), "note.wav", "audio/wav",
        )
        asr = SimpleNamespace(status_code=500, json=lambda: {})
        client = Mock()
        client.responses.create.side_effect = openai.APIConnectionError(request=Mock())
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}):
            with patch("app.requests") as asr_lib:
                asr_lib.post.return_value = asr
                with patch("openai.OpenAI", return_value=client):
                    response = self.client.post(
                        "/cases/new", data=fields, content_type="multipart/form-data",
                    )
        self.assertEqual(response.status_code, 302)
        with self.module.db() as conn:
            row = conn.execute("SELECT id FROM cases").fetchone()
            note = conn.execute(
                "SELECT note FROM case_notes WHERE case_id=?", (row["id"],)
            ).fetchone()
        self.assertIn("failed (HTTP 500", note["note"])

    def test_reassessment_sends_new_follow_up_photo(self):
        case_id = self.create_case()
        image = Image.new("RGB", (4, 4), color=(40, 120, 60))
        image_buffer = BytesIO()
        image.save(image_buffer, format="PNG")
        follow = self.client.post(
            f"/cases/{case_id}/evidence",
            data={
                "note": "Morning revisit with photo.",
                "author": "Field Officer",
                "photo": (BytesIO(image_buffer.getvalue()), "leaf.png", "image/png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(follow.status_code, 302)
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text=json.dumps(self._assessment_payload())
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": "test-key"}):
            with patch("openai.OpenAI", return_value=client):
                rerun = self.client.post(f"/cases/{case_id}/reassess")
        self.assertEqual(rerun.status_code, 302)
        content = client.responses.create.call_args.kwargs["input"][0]["content"]
        self.assertTrue(any(item["type"] == "input_image" for item in content))
        self.assertIn("Morning revisit with photo.", str(client.responses.create.call_args))


if __name__ == "__main__":
    unittest.main()
