import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.application.pipeline import render_message
from app.application.templates import TemplateValidationError, seed_templates, validate_template
from app.domain.models import AnalysisResult, ContentItem
from app.infrastructure.store import SQLiteStore


class TemplateManagementTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = SQLiteStore(Path(self.directory.name) / "runtime.db")
        seed_templates(self.store)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_draft_does_not_affect_rendering_until_published(self):
        detail = self.store.template_detail("realtime")
        content = "<b>NEW {title}</b>\n{summary}\n<a href=\"{original_url}\">原文</a>"
        saved = self.store.save_template_draft("realtime", content, detail["draft_revision"])

        before = render_message(self._item(), self._analysis(), template_provider=self.store)
        self.assertNotIn("NEW", before)

        published = self.store.publish_template("realtime", saved["draft_revision"], "test")
        after = render_message(self._item(), self._analysis(), template_provider=self.store)
        self.assertIn("NEW 模型更新", after)
        self.assertEqual(published["published_version"], 2)

    def test_stale_revision_cannot_overwrite_newer_draft(self):
        detail = self.store.template_detail("realtime")
        first = self.store.save_template_draft(
            "realtime", "<b>{title}</b>\n{summary}\n<a href=\"{original_url}\">原文</a>", detail["draft_revision"]
        )
        stale = self.store.save_template_draft(
            "realtime", "<b>stale {title}</b>\n{summary}\n<a href=\"{original_url}\">原文</a>", detail["draft_revision"]
        )
        self.assertIsNotNone(first)
        self.assertIsNone(stale)

    def test_restore_creates_draft_and_requires_publish(self):
        detail = self.store.template_detail("realtime")
        saved = self.store.save_template_draft(
            "realtime", "<b>V2 {title}</b>\n{summary}\n<a href=\"{original_url}\">原文</a>", detail["draft_revision"]
        )
        published = self.store.publish_template("realtime", saved["draft_revision"], "test")
        restored = self.store.restore_template_version(
            "realtime", 1, published["draft_revision"]
        )
        self.assertEqual(restored["status"], "draft")
        self.assertIn("V2", self.store.get_published_template("realtime"))
        self.assertNotIn("V2", restored["draft_content"])

    def test_same_draft_cannot_be_published_twice(self):
        detail = self.store.template_detail("realtime")
        saved = self.store.save_template_draft(
            "realtime", "<b>V2 {title}</b>\n{summary}\n<a href=\"{original_url}\">原文</a>", detail["draft_revision"]
        )

        published = self.store.publish_template("realtime", saved["draft_revision"], "test")
        duplicate = self.store.publish_template("realtime", saved["draft_revision"], "test")

        self.assertEqual(published["published_version"], 2)
        self.assertIsNone(duplicate)
        self.assertEqual(len(self.store.template_detail("realtime")["versions"]), 2)

    def test_validation_rejects_unknown_variables_and_unsafe_html(self):
        with self.assertRaises(TemplateValidationError):
            validate_template("realtime", "{title}\n{summary}\n{unknown}")
        with self.assertRaises(TemplateValidationError):
            validate_template("realtime", "<script>{title}</script>\n{summary}\n{links_line}")
        with self.assertRaises(TemplateValidationError):
            validate_template("realtime", "<b>{title}\n{summary}\n{links_line}")

    def test_validation_accepts_title_prefix(self):
        content = "{title_prefix} {title}\n{summary}"
        self.assertEqual(validate_template("realtime", content), content)

        with self.assertRaises(TemplateValidationError):
            validate_template(
                "realtime",
                '<tg-emoji emoji-id="6073311243781807979">🤖</tg-emoji> {title}\n{summary}',
            )

    @staticmethod
    def _item():
        return ContentItem(
            "one", "source", "Source", "模型", "模型更新", "https://example.com",
            "摘要", datetime(2026, 8, 21, tzinfo=timezone.utc),
        )

    @staticmethod
    def _analysis():
        return AnalysisResult("notify", "S", "模型", "摘要", "重点", "查看", 0.95)


if __name__ == "__main__":
    unittest.main()
