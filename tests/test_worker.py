import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.infrastructure.store import SQLiteStore
from app.domain.models import ContentItem
from app.worker import load_notification_policy, run_daemon_tick, run_once


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = SQLiteStore(Path(self.directory.name) / "runtime.db")

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_idle_tick_does_not_create_job_or_loggable_result(self):
        source = {"id": "source-one", "poll_interval_minutes": 15}
        self.store.mark_source_result("source-one", 15, 0)

        result = run_daemon_tick(self.store, [source], Mock(), Mock())

        jobs = self.store.connection.execute("SELECT COUNT(*) FROM job_runs").fetchone()[0]
        self.assertIsNone(result)
        self.assertEqual(jobs, 0)

    @patch("app.worker.run_once")
    def test_due_source_runs_pipeline(self, run_once):
        source = {"id": "source-one", "poll_interval_minutes": 15}
        expected = {"discovered": 1, "analyzed": 1, "sent": 1, "errors": 0}
        run_once.return_value = expected

        result = run_daemon_tick(self.store, [source], Mock(), Mock())

        self.assertEqual(result, expected)
        run_once.assert_called_once()
        self.assertEqual(run_once.call_args.args[1], [source])

    def test_publishing_policy_is_loaded_from_versioned_config(self):
        path = Path(__file__).resolve().parents[1] / "config" / "publishing.json"
        policy = load_notification_policy(path)
        self.assertEqual(policy.allowed_priorities, frozenset({"S", "A"}))
        self.assertEqual(policy.min_confidence, 0.75)

    def test_source_adapter_types_are_explicit(self):
        from app.adapters.sources.email import EmailSourceAdapter
        from app.adapters.sources.changelog import DocusaurusChangelogSourceAdapter
        from app.adapters.sources.rss import RSSSourceAdapter
        from app.adapters.sources.sitemap import SitemapSourceAdapter
        from app.adapters.sources.openai_changelog import OpenAIChangelogSourceAdapter
        from app.adapters.sources.gemini_changelog import GeminiChangelogSourceAdapter
        from app.adapters.sources.x import XSourceAdapter
        from app.worker import build_source_adapter

        self.assertIsInstance(build_source_adapter({"source_type": "rss"}), RSSSourceAdapter)
        self.assertIsInstance(
            build_source_adapter({"source_type": "docusaurus_changelog"}),
            DocusaurusChangelogSourceAdapter,
        )
        self.assertIsInstance(
            build_source_adapter({"source_type": "openai_changelog"}),
            OpenAIChangelogSourceAdapter,
        )
        self.assertIsInstance(
            build_source_adapter({"source_type": "gemini_changelog"}),
            GeminiChangelogSourceAdapter,
        )
        self.assertIsInstance(build_source_adapter({"source_type": "email"}), EmailSourceAdapter)
        self.assertIsInstance(build_source_adapter({"source_type": "sitemap"}), SitemapSourceAdapter)
        self.assertIsInstance(build_source_adapter({"source_type": "x"}), XSourceAdapter)

    @patch("app.worker.build_source_adapter")
    def test_first_sitemap_poll_baselines_without_fetching_articles(self, build_adapter):
        candidate = ContentItem(
            item_id="anthropic-one", source_id="anthropic", source_name="Anthropic News",
            category="模型、产品与研究", title="new model",
            url="https://www.anthropic.com/news/new-model", summary="", published_at=None,
        )
        adapter = Mock()
        adapter.fetch.return_value = [candidate]
        adapter.enrich.return_value = candidate
        build_adapter.return_value = adapter
        self.store.save_item(ContentItem(
            item_id="existing", source_id="existing", source_name="Existing",
            category="其他", title="Existing", url="https://example.com/existing",
            summary="", published_at=None,
        ), status="baselined")
        source = {"id": "anthropic", "source_type": "sitemap", "baseline_on_first_poll": True,
                  "poll_interval_minutes": 1}

        result = run_once(self.store, [source], Mock(), Mock())

        self.assertEqual(result, {"discovered": 1, "analyzed": 0, "sent": 0, "errors": 0})
        adapter.enrich.assert_not_called()
        self.assertEqual(self.store.item_status("anthropic-one"), "baselined")

    @patch("app.worker.build_source_adapter")
    def test_source_recovery_baselines_after_previous_failures(self, build_adapter):
        candidate = ContentItem(
            item_id="openai-recovered", source_id="openai", source_name="OpenAI Changelog",
            category="模型与 API 更新", title="historical update",
            url="https://developers.openai.com/api/docs/changelog", summary="", published_at=None,
        )
        adapter = Mock()
        adapter.fetch.return_value = [candidate]
        build_adapter.return_value = adapter
        self.store.save_item(ContentItem(
            item_id="existing", source_id="existing", source_name="Existing",
            category="其他", title="Existing", url="https://example.com/existing",
            summary="", published_at=None,
        ), status="baselined")
        self.store.mark_source_result("openai", 1, 0, "HTTP 403")
        source = {"id": "openai", "source_type": "openai_changelog",
                  "baseline_on_first_poll": True, "poll_interval_minutes": 1}

        result = run_once(self.store, [source], Mock(), Mock())

        self.assertEqual(result, {"discovered": 1, "analyzed": 0, "sent": 0, "errors": 0})
        self.assertEqual(self.store.item_status("openai-recovered"), "baselined")


if __name__ == "__main__":
    unittest.main()
