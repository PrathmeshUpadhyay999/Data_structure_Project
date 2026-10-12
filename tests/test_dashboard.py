"""Tests for the Person 3 Flask dashboard and advisory rules."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from heatwave_dashboard import create_app
from heatwave_dashboard.advisories import generate_advisories
from heatwave_pipeline import config
from heatwave_pipeline.database import connect, init_db
from heatwave_pipeline.aws_simulator import run_live_aws_simulation
from heatwave_pipeline.ingestion import ingest_imd_file, now_ist


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "dashboard.db"
        conn = connect(self.db_path)
        init_db(conn)
        ingest_imd_file(
            conn,
            config.SAMPLE_IMD_FILE,
            now=datetime(2026, 10, 12, 12, 0, 0),
        )
        conn.close()
        self.app = create_app(self.db_path)
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dashboard_page_is_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Heatwave Intelligence", response.data)
        self.assertIn(b"Rule-based advisories", response.data)
        self.assertIn(b'value="4">4 days', response.data)
        self.assertIn(b'value="6">6 days', response.data)
        self.assertIn(b"every 5 seconds", response.data)
        self.assertIn(b"SIMULATED AWS", response.data)

    def test_dashboard_aggregates_existing_api_outputs(self):
        response = self.client.get("/api/dashboard?days=2")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["days_ahead"], 2)
        self.assertEqual(len(payload["locations"]), 5)
        self.assertEqual(len(payload["forecasts"]), 5)
        self.assertEqual(payload["quality"]["total_observations"], 7)
        self.assertTrue(all("actions" in item for item in payload["advisories"]))
        self.assertIn("live_readings", payload)
        self.assertIn("temperature_history", payload)
        self.assertIsNone(payload["history_station"])
        self.assertFalse(payload["live_feed"]["active"])

    def test_forecast_horizon_changes_target_date(self):
        target_dates = {}
        for days in range(1, 8):
            with self.subTest(days=days):
                response = self.client.get(f"/api/dashboard?days={days}")
                self.assertEqual(response.status_code, 200)
                forecast = response.get_json()["forecasts"][0]
                self.assertEqual(forecast["days_ahead"], days)
                target_dates[days] = forecast["target_date"]
        self.assertEqual(len(set(target_dates.values())), 7)

    def test_live_aws_simulator_data_appears_without_dashboard_restart(self):
        before = self.client.get("/api/dashboard").get_json()
        conn = connect(self.db_path)
        try:
            started_at = now_ist()
            run_live_aws_simulation(
                conn,
                cadence_seconds=0,
                fault_rate=0,
                packet_loss_rate=0,
                out_of_order_rate=0,
                retransmission_rate=0,
                max_ticks=1,
            )
        finally:
            conn.close()

        after = self.client.get("/api/dashboard").get_json()
        self.assertEqual(after["quality"]["total_observations"], before["quality"]["total_observations"] + 5)
        self.assertEqual(len(after["locations"]), len(before["locations"]) + 5)
        self.assertTrue(any(location["station_id"] == "AWS-DEL-01" for location in after["locations"]))
        self.assertEqual(len(after["live_readings"]), 5)
        self.assertGreaterEqual(len(after["temperature_history"]), 1)
        self.assertTrue(after["live_feed"]["active"])
        self.assertGreaterEqual(after["live_readings"][0]["observed_at"], started_at.isoformat(timespec="seconds"))
        self.assertLessEqual(after["as_of"], now_ist().date().isoformat())

    def test_dashboard_rejects_invalid_horizon(self):
        for value in ("zero", "0", "8"):
            with self.subTest(value=value):
                response = self.client.get(f"/api/dashboard?days={value}")
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.get_json())

    def test_existing_api_endpoints_are_forwarded(self):
        response = self.client.get("/api/regions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["count"], 4)

    def test_missing_database_is_explicit(self):
        missing = Path(self.temp_dir.name) / "missing.db"
        with self.assertRaises(FileNotFoundError):
            create_app(missing)


class AdvisoryRuleTests(unittest.TestCase):
    def test_alert_severity_takes_precedence_over_forecast(self):
        item = {
            "location_id": 3,
            "name": "Station 3",
            "region": "WEST",
            "target_date": "2025-05-21",
            "forecast": {"severity": 2},
        }
        alert = {"location_id": 3, "severity": 5}
        advisory = generate_advisories([item], [alert])[0]
        self.assertEqual(advisory["severity"], 5)
        self.assertEqual(advisory["basis"], "active_alert_and_forecast")
        self.assertIn("local authority", " ".join(advisory["actions"]))

    def test_insufficient_data_is_not_reported_as_low_risk(self):
        item = {
            "location_id": 4,
            "name": "Station 4",
            "region": "SOUTH",
            "target_date": "2025-05-21",
            "forecast": None,
        }
        advisory = generate_advisories([item], [])[0]
        self.assertIsNone(advisory["severity"])
        self.assertEqual(advisory["category"], "data_gap")
        self.assertIn("not a low-risk assessment", advisory["message"])


if __name__ == "__main__":
    unittest.main()
