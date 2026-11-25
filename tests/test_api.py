import unittest
from unittest.mock import patch

from app import app, configured_cors_origins


class ApiCheckpointTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_root_contract(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["docs"], "/api/events")

    def test_frontend_is_served_by_backend(self):
        response = self.client.get("/app/", buffered=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Gather — Campus events", response.get_data(as_text=True))
        response.close()

        for path in ("/app/styles.css", "/app/app.js"):
            with self.subTest(path=path):
                asset = self.client.get(path, buffered=True)
                self.assertEqual(asset.status_code, 200)
                asset.close()

    def test_frontend_path_without_trailing_slash_redirects(self):
        response = self.client.get("/app")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/app/")

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

    def test_registration_rejects_non_object_json(self):
        response = self.client.post(
            "/api/registrations",
            headers={"X-User-Id": "00000000-0000-0000-0000-000000000001"},
            json=["not", "an", "object"],
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.get_json()["detail"],
            "Request body must be a JSON object.",
        )

    @patch("app.get_supabase")
    def test_health_reports_database_failure_as_json(self, get_supabase):
        get_supabase.side_effect = RuntimeError("missing configuration")
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["status"], "degraded")

    @patch("app.get_supabase")
    def test_health_route_includes_cors_headers(self, get_supabase):
        get_supabase.side_effect = RuntimeError("offline")
        origins = configured_cors_origins()
        origin = (
            origins[0]
            if isinstance(origins, list) and origins
            else "http://localhost:8000"
        )
        response = self.client.get(
            "/health",
            headers={"Origin": origin},
        )
        self.assertIn("Access-Control-Allow-Origin", response.headers)


if __name__ == "__main__":
    unittest.main()
