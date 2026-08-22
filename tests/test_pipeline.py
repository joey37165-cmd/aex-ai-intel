import tempfile
import unittest
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.adapters.llm.deepseek import RuleBasedAnalyzer
from app.application.pipeline import process_item, render_digest, render_message, send_pending
from app.domain.models import AnalysisResult, ContentItem, DigestReport, ProcessOutcome
from app.domain.policies import NotificationPolicy
from app.infrastructure.store import SQLiteStore


class FakeNotifier:
    def __init__(self, fail=False):
        self.fail = fail
        self.messages = []

    def send(self, text):
        if self.fail:
            raise RuntimeError("temporary failure")
        self.messages.append(text)
        return str(len(self.messages))

    def send_photo(self, photo_url, caption):
        self.messages.append((photo_url, caption))
        return str(len(self.messages))


class FixedAnalyzer:
    model_name = "fixed"
    prompt_version = "test"

    def __init__(self, result):
        self.result = result

    def analyze(self, content_item):
        return self.result


def item(item_id="one", title="New model release"):
    return ContentItem(
        item_id=item_id,
        source_id="test-source",
        source_name="Test Source",
        category="模型",
        title=title,
        url=f"https://example.com/{item_id}",
        summary="An API model release with an open source implementation.",
        published_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
    )


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = SQLiteStore(Path(self.directory.name) / "runtime.db")

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_new_item_is_analyzed_and_sent_once(self):
        notifier = FakeNotifier()
        result = process_item(self.store, item(), RuleBasedAnalyzer(), notifier)
        duplicate = process_item(self.store, item(), RuleBasedAnalyzer(), notifier)
        self.assertEqual(result, ProcessOutcome(created=True, analyzed=True, sent=True))
        self.assertEqual(duplicate, ProcessOutcome())
        self.assertEqual(len(notifier.messages), 1)
        self.assertEqual(self.store.pending_deliveries(), [])

    def test_failed_delivery_is_retryable(self):
        self.assertEqual(
            process_item(self.store, item(), RuleBasedAnalyzer(), FakeNotifier(fail=True)),
            ProcessOutcome(created=True, analyzed=True, failed=True),
        )
        rows = self.store.pending_deliveries()
        self.assertEqual(len(rows), 0)
        row = self.store.connection.execute("SELECT status, attempts FROM deliveries").fetchone()
        self.assertEqual((row["status"], row["attempts"]), ("retry", 1))

    def test_pending_delivery_can_be_flushed_after_restart(self):
        process_item(self.store, item(), RuleBasedAnalyzer(), None)
        notifier = FakeNotifier()
        self.assertEqual(send_pending(self.store, notifier), 1)
        self.assertEqual(len(notifier.messages), 1)
        self.assertEqual(self.store.pending_deliveries(), [])

    def test_baselined_item_is_not_analyzed_on_next_run(self):
        self.store.save_item(item(), status="baselined")
        self.assertEqual(process_item(self.store, item(), RuleBasedAnalyzer(), FakeNotifier()), ProcessOutcome())
        self.assertEqual(self.store.connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0], 0)

    def test_ignored_item_is_counted_as_analyzed_without_delivery(self):
        ignored = ContentItem(
            item_id="ignored", source_id="test-source", source_name="Test Source", category="其他",
            title="Company picnic", url="https://example.com/ignored", summary="Team photos.", published_at=None,
        )
        outcome = process_item(self.store, ignored, RuleBasedAnalyzer(), FakeNotifier())
        self.assertEqual(outcome, ProcessOutcome(created=True, analyzed=True))
        self.assertEqual(self.store.connection.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0], 0)

    def test_render_escapes_telegram_html(self):
        result = AnalysisResult("notify", "S", "模型", "a < b", "why & now", "查看", 0.9)
        text = render_message(item(title="<unsafe>"), result)
        self.assertIn("&lt;unsafe&gt;", text)
        self.assertNotIn("why &amp; now", text)
        self.assertIn("a &lt; b", text)

    def test_render_preserves_numbered_summary_lines(self):
        result = AnalysisResult(
            "notify", "A", "模型", "（1）第一条事实。\n（2）第二条事实。", "不展示", "查看", 0.9,
        )
        text = render_message(item(), result)
        self.assertIn("（1）第一条事实。\n\n（2）第二条事实。", text)

    def test_render_numbers_unformatted_summary_sentences_without_inventing_text(self):
        result = AnalysisResult(
            "notify", "A", "模型", "第一条事实。第二条事实；第三条事实。", "不展示", "查看", 0.9,
        )
        text = render_message(item(), result)
        self.assertIn("（1）第一条事实。\n\n（2）第二条事实；\n\n（3）第三条事实。", text)

    def test_render_uses_beijing_time(self):
        result = AnalysisResult("notify", "S", "模型", "摘要", "价值", "查看", 0.9)
        text = render_message(item(), result)
        self.assertIn("<b>📝 New model release</b>", text)
        self.assertNotIn("S级", text)
        self.assertNotIn("建议动作", text)
        self.assertNotIn("来源：", text)
        self.assertNotIn("北京时间", text)
        self.assertIn("<b>【要点】</b>", text)
        self.assertIn("<a href=\"https://example.com/one\">↗ 阅读原文</a>", text)

    def test_render_includes_configured_creator_x_link(self):
        result = AnalysisResult("notify", "S", "模型", "摘要", "价值", "查看", 0.9)
        with patch.dict(os.environ, {"CREATOR_X_URL": "https://x.com/aex"}, clear=False):
            text = render_message(item(), result)
        self.assertIn('<a href="https://example.com/one">↗ 阅读原文</a> | <a href="https://x.com/aex">𝕏 · Aex0x0</a>', text)

    def test_render_uses_translated_title_without_emoji(self):
        result = AnalysisResult(
            "notify", "S", "AI 前沿信息", "摘要", "价值", "查看", 0.9,
            display_title="🚀 Claude 4.1 发布：更强的 Agent 能力",
        )
        text = render_message(item(title="🚀 Claude 4.1 released"), result)
        self.assertIn("<b>📝 Claude 4.1 发布：更强的 Agent 能力</b>", text)
        self.assertNotIn("🚀", text)

    def test_title_uses_frontier_icon_without_source_brand_icon(self):
        result = AnalysisResult(
            "notify", "S", "AI 前沿信息", "摘要", "价值", "查看", 0.9,
            display_title="新模型发布",
        )
        source_item = ContentItem(
            "openai", "rss-openai-news", "OpenAI News", "模型", "New model",
            "https://example.com/openai", "Summary", None,
        )
        text = render_message(source_item, result)
        self.assertIn("<b>📝 新模型发布</b>", text)
        self.assertNotIn("🤖", text)
        self.assertNotIn("🚀", text)

    def test_title_uses_application_icon(self):
        result = AnalysisResult(
            "notify", "A", "AI 应用", "摘要", "价值", "查看", 0.9,
            display_title="新的 AI 工作流上线",
        )
        text = render_message(item(title="New workflow"), result)
        self.assertIn("<b>📌 新的 AI 工作流上线</b>", text)

    def test_render_supports_independent_template_link_variables(self):
        result = AnalysisResult("notify", "S", "模型", "摘要", "价值", "查看", 0.9)
        template = '<a href="{my_x_url}">我的 X</a> | <a href="{original_url}">原文</a>'
        with tempfile.TemporaryDirectory() as directory:
            template_path = Path(directory) / "template.html"
            template_path.write_text(template, encoding="utf-8")
            text = render_message(item(), result, template_path=template_path)
        self.assertEqual(
            text,
            '<a href="https://x.com/axe0x0">我的 X</a> | '
            '<a href="https://example.com/one">原文</a>',
        )

    def test_item_with_image_uses_photo_delivery(self):
        photo_item = ContentItem(
            item_id="photo", source_id="test-source", source_name="Test Source", category="模型",
            title="Photo release", url="https://example.com/photo", summary="Summary",
            published_at=None, image_url="https://cdn.example.com/photo.jpg",
        )
        notifier = FakeNotifier()
        result = process_item(self.store, photo_item, FixedAnalyzer(
            AnalysisResult("notify", "S", "模型", "摘要", "价值", "查看", 0.9)
        ), notifier)
        self.assertEqual(result.sent, True)
        self.assertEqual(notifier.messages[0][0], "https://cdn.example.com/photo.jpg")

    def test_daily_and_weekly_reports_share_digest_template(self):
        daily = DigestReport(
            report_title="AI 日报", period_label="2026-08-19", overview="今日有 3 条值得关注的信息。",
            frontier_items="1. 新模型发布", application_items="1. Agent 工作流更新",
            key_takeaways="模型能力和 Agent 工程继续加速。",
        )
        weekly = DigestReport(
            report_title="AI 周报", period_label="2026-08-12 至 2026-08-18", overview="本周重点回顾。",
            frontier_items="1. 模型趋势", application_items="1. 工具趋势",
            key_takeaways="本周观察。",
        )
        daily_text = render_digest(daily)
        weekly_text = render_digest(weekly)
        self.assertIn("AI 日报 · 2026-08-19", daily_text)
        self.assertIn("AI 周报 · 2026-08-12 至 2026-08-18", weekly_text)
        self.assertIn("AI 前沿信息", daily_text)
        self.assertIn("AI 应用", weekly_text)
        self.assertNotIn("建议动作", daily_text)

    def test_digest_drops_source_links_if_telegram_message_would_be_too_long(self):
        report = DigestReport(
            report_title="AI 日报", period_label="2026-08-19",
            overview="摘要", frontier_items="前沿", application_items="应用",
            key_takeaways="观察", source_links="x" * 5000,
        )
        text = render_digest(report)
        self.assertLessEqual(len(text), 4000)
        self.assertNotIn("x" * 100, text)

    def test_low_confidence_notification_is_held_for_review(self):
        result = AnalysisResult("notify", "S", "模型", "摘要", "价值", "查看", 0.74)
        outcome = process_item(self.store, item(), FixedAnalyzer(result), FakeNotifier(), NotificationPolicy())
        stored = self.store.connection.execute("SELECT decision, raw_json FROM analyses").fetchone()
        self.assertEqual(outcome, ProcessOutcome(created=True, analyzed=True))
        self.assertEqual(stored["decision"], "review")
        self.assertIn("confidence_below_0.75", stored["raw_json"])
        self.assertEqual(self.store.connection.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0], 0)

    def test_b_priority_notification_is_held_for_review(self):
        result = AnalysisResult("notify", "B", "行业", "摘要", "价值", "观察", 0.99)
        outcome = process_item(self.store, item(), FixedAnalyzer(result), FakeNotifier(), NotificationPolicy())
        stored = self.store.connection.execute("SELECT decision, raw_json FROM analyses").fetchone()
        self.assertEqual(outcome, ProcessOutcome(created=True, analyzed=True))
        self.assertEqual(stored["decision"], "review")
        self.assertIn("priority_B_not_allowed", stored["raw_json"])
        summary = self.store.status_summary()
        self.assertEqual(summary["analysis_decisions"], {"review": 1})
        self.assertEqual(summary["analysis_priorities"], {"B": 1})

    def test_review_items_are_readable_without_changing_state(self):
        result = AnalysisResult("review", "B", "行业", "摘要", "价值", "观察", 0.5)
        process_item(self.store, item(), FixedAnalyzer(result), None)
        rows = self.store.review_items()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "New model release")
        self.assertEqual(self.store.item_status("one"), "review")

    def test_source_poll_state_is_persisted(self):
        self.assertTrue(self.store.source_is_due("source-one"))
        self.store.mark_source_result("source-one", 15, 12)
        self.assertFalse(self.store.source_is_due("source-one"))
        summary = self.store.status_summary()
        self.assertEqual(summary["sources"][0]["source_id"], "source-one")
        self.assertEqual(summary["sources"][0]["last_item_count"], 12)
        self.assertTrue(self.store.source_state_exists("source-one"))

    def test_source_failure_keeps_last_success(self):
        self.store.mark_source_result("source-one", 15, 12)
        first_success = self.store.status_summary()["sources"][0]["last_success_at"]
        self.store.mark_source_result("source-one", 15, 0, "timeout")
        source = self.store.status_summary()["sources"][0]
        self.assertEqual(source["last_success_at"], first_success)
        self.assertEqual(source["last_error"], "timeout")


if __name__ == "__main__":
    unittest.main()
