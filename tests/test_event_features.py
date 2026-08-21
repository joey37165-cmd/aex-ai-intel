import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.adapters.llm.deepseek import RuleBasedAnalyzer, _result
from app.domain.models import AnalysisResult, ContentItem, EventFeatures
from app.infrastructure.store import SQLiteStore


def make_item() -> ContentItem:
    return ContentItem(
        item_id="event-item",
        source_id="source",
        source_name="Test Source",
        category="模型",
        title="DeepSeek V4 发布",
        url="https://example.com/event",
        summary="DeepSeek 发布新模型并更新 API。",
        published_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )


class EventFeatureTests(unittest.TestCase):
    def test_result_extracts_and_normalizes_event_features(self):
        result = _result(
            {
                "decision": "notify",
                "priority": "S",
                "category": "AI 前沿信息",
                "display_title": "DeepSeek V4 发布",
                "summary": "DeepSeek 发布新模型并更新 API。",
                "why_it_matters": "影响模型调用方式。",
                "suggested_action": "立即查看",
                "confidence": 0.91,
                "event": {
                    "event_type": "MODEL_RELEASE",
                    "organization": "DeepSeek",
                    "product": "V4",
                    "version": "V4",
                    "core_claim": "发布新模型并更新 API",
                    "event_time": "2026-08-21",
                },
            },
            make_item(),
        )
        self.assertEqual(
            result.event,
            EventFeatures(
                event_type="model_release",
                organization="DeepSeek",
                product="V4",
                version="V4",
                core_claim="发布新模型并更新 API",
                event_time="2026-08-21",
            ),
        )

    def test_invalid_event_features_fall_back_without_breaking_analysis(self):
        result = _result({"summary": "摘要", "event": {
            "event_type": "made_up",
            "event_time": "yesterday",
            "core_claim": "",
        }}, make_item())
        self.assertEqual(result.event.event_type, "other")
        self.assertIsNone(result.event.event_time)
        self.assertEqual(result.event.core_claim, "摘要")

    def test_rule_analyzer_emits_fallback_event(self):
        result = RuleBasedAnalyzer().analyze(make_item())
        self.assertEqual(result.event.event_type, "other")
        self.assertEqual(result.event.organization, None)
        self.assertEqual(result.event.event_time, "2026-08-21")
        self.assertTrue(result.event.core_claim)

    def test_store_persists_and_updates_event_json(self):
        directory = tempfile.TemporaryDirectory()
        try:
            store = SQLiteStore(Path(directory.name) / "runtime.db")
            store.save_item(make_item())
            first = AnalysisResult(
                "notify", "S", "AI 前沿信息", "摘要", "重点", "查看", 0.9,
                event=EventFeatures(
                    event_type="model_release", organization="DeepSeek", product="V4",
                    version="V4", core_claim="发布 V4", event_time="2026-08-21",
                ),
            )
            store.save_analysis(make_item().item_id, first, "test-model", "test-prompt")
            row = store.connection.execute("SELECT event_json FROM analyses WHERE item_id=?", (make_item().item_id,)).fetchone()
            self.assertEqual(json.loads(row["event_json"])["product"], "V4")

            second = AnalysisResult(
                "notify", "A", "AI 应用", "更新摘要", "新的重点", "测试", 0.8,
                event=EventFeatures(event_type="api_update", product="API", core_claim="更新 API"),
            )
            store.save_analysis(make_item().item_id, second, "test-model-2", "test-prompt-2")
            row = store.connection.execute("SELECT priority, event_json FROM analyses WHERE item_id=?", (make_item().item_id,)).fetchone()
            self.assertEqual(row["priority"], "A")
            self.assertEqual(json.loads(row["event_json"])["event_type"], "api_update")
        finally:
            store.close()
            directory.cleanup()

    def test_old_analyses_table_is_migrated(self):
        directory = tempfile.TemporaryDirectory()
        try:
            path = Path(directory.name) / "runtime.db"
            connection = sqlite3.connect(path)
            connection.execute("""CREATE TABLE analyses (
                item_id TEXT PRIMARY KEY, decision TEXT NOT NULL, priority TEXT NOT NULL,
                category TEXT NOT NULL, summary TEXT NOT NULL, why_it_matters TEXT NOT NULL,
                suggested_action TEXT NOT NULL, confidence REAL NOT NULL,
                display_title TEXT NOT NULL DEFAULT '', raw_json TEXT NOT NULL,
                model_name TEXT NOT NULL DEFAULT 'unknown', prompt_version TEXT NOT NULL DEFAULT 'unknown',
                created_at TEXT NOT NULL
            )""")
            connection.commit()
            connection.close()
            store = SQLiteStore(path)
            columns = {row[1] for row in store.connection.execute("PRAGMA table_info(analyses)")}
            self.assertIn("event_json", columns)
            self.assertEqual(store.connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0], 0)
        finally:
            store.close()
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
