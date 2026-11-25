import unittest
from unittest.mock import patch

from app import app


class ApiCheckpointTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_root_contract(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["docs"], "/api/events")

    def test_registration_requires_authenticated_identity(self):
        response = self.client.post(
            "/api/registrations",
            json={"event_id": "00000000-0000-0000-0000-000000000000"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("X-User-Id", response.get_json()["detail"])

    def test_registration_rejects_identity_mismatch(self):
        response = self.client.post(
            "/api/registrations",
            headers={"X-User-Id": "00000000-0000-0000-0000-000000000001"},
            json={
                "event_id": "00000000-0000-0000-0000-000000000002",
                "user_id": "00000000-0000-0000-0000-000000000003",
            },
        )
        self.assertEqual(response.status_code, 403)

    @patch("app.get_supabase")
    def test_health_reports_database_failure_as_json(self, get_supabase):
        get_supabase.side_effect = RuntimeError("missing configuration")
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["status"], "degraded")


if __name__ == "__main__":
    unittest.main()
