import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app


TOKEN = "test-admin-token-with-more-than-32-characters"


class TemplateAPITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "ADMIN_API_TOKEN": TOKEN,
            "RUNTIME_DB_PATH": str(Path(self.directory.name) / "runtime.db"),
        })
        self.env.start()
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {TOKEN}"}

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.directory.cleanup()

    def test_admin_routes_reject_missing_token(self):
        response = self.client.get("/api/admin/templates")
        self.assertEqual(response.status_code, 401)

    def test_save_and_publish_template(self):
        templates = self.client.get("/api/admin/templates", headers=self.headers).json()
        realtime = next(item for item in templates if item["id"] == "realtime")
        content = "<b>【{category_line}】API {title}</b>\n{summary}\n<a href=\"{original_url}\">原文</a>"

        saved = self.client.put(
            "/api/admin/templates/realtime/draft",
            headers=self.headers,
            json={"content": content, "expected_revision": realtime["draftRevision"]},
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["status"], "草稿")

        published = self.client.post(
            "/api/admin/templates/realtime/publish",
            headers=self.headers,
            json={"expected_revision": saved.json()["draftRevision"]},
        )
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json()["status"], "已发布")
        self.assertEqual(published.json()["version"], 2)
        duplicate = self.client.post(
            "/api/admin/templates/realtime/publish",
            headers=self.headers,
            json={"expected_revision": published.json()["draftRevision"]},
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_rejects_stale_revision_and_unknown_variable(self):
        realtime = self.client.get(
            "/api/admin/templates/realtime", headers=self.headers
        ).json()
        valid = "<b>【{category_line}】{title}</b>\n{summary}\n<a href=\"{original_url}\">原文</a>"
        first = self.client.put(
            "/api/admin/templates/realtime/draft", headers=self.headers,
            json={"content": valid, "expected_revision": realtime["draftRevision"]},
        )
        self.assertEqual(first.status_code, 200)
        stale = self.client.put(
            "/api/admin/templates/realtime/draft", headers=self.headers,
            json={"content": valid, "expected_revision": realtime["draftRevision"]},
        )
        self.assertEqual(stale.status_code, 409)
        invalid = self.client.put(
            "/api/admin/templates/realtime/draft", headers=self.headers,
            json={
                "content": "{title}\n{summary}\n{bad}",
                "expected_revision": first.json()["draftRevision"],
            },
        )
        self.assertEqual(invalid.status_code, 422)

    def test_realtime_category_is_optional(self):
        realtime = self.client.get(
            "/api/admin/templates/realtime", headers=self.headers
        ).json()
        response = self.client.put(
            "/api/admin/templates/realtime/draft", headers=self.headers,
            json={
                "content": "{title}\n\n{summary}",
                "expected_revision": realtime["draftRevision"],
            },
        )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
