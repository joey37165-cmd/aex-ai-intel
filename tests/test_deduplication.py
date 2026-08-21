import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.application.pipeline import process_item
from app.domain.deduplication import are_semantic_duplicates
from app.domain.models import AnalysisResult, ContentItem
from app.infrastructure.store import SQLiteStore


class FakeNotifier:
    def __init__(self):
        self.messages = []

    def send(self, text):
        self.messages.append(text)
        return str(len(self.messages))


class NotifyAnalyzer:
    model_name = "test"
    prompt_version = "dedup-test"

    def analyze(self, item):
        return AnalysisResult(
            decision="notify",
            priority="S",
            category="AI 前沿信息",
            summary=item.summary,
            why_it_matters="同一事件去重测试",
            suggested_action="关注",
            confidence=0.99,
            display_title=item.title,
        )


class DeduplicationTests(unittest.TestCase):
    def test_deepseek_multimodal_variants_are_duplicates(self):
        titles = [
            "DeepSeek 推出 V4-Flash 视觉模型，API 新增多模态图像输入支持",
            "DeepSeek 发布 V4-Flash-Vision-Exp 多模态实验模型并上线 API 平台",
            "DeepSeek 发布多模态实验模型 V4 Flash Vision EXP，文本能力持平 V4 Flash",
        ]
        for index, title in enumerate(titles):
            for other in titles[index + 1:]:
                self.assertTrue(are_semantic_duplicates(title, "", other, ""))

    def test_same_model_different_event_is_not_duplicate(self):
        self.assertFalse(are_semantic_duplicates(
            "DeepSeek V4 Flash API 新增价格方案", "价格与计费更新",
            "DeepSeek V4 Flash Vision 多模态模型发布", "视觉模型能力更新",
        ))

    def test_pipeline_suppresses_second_cross_source_notification(self):
        directory = tempfile.TemporaryDirectory()
        try:
            store = SQLiteStore(Path(directory.name) / "runtime.db")
            notifier = FakeNotifier()
            analyzer = NotifyAnalyzer()
            published = datetime(2026, 8, 21, 2, tzinfo=timezone.utc)
            first = ContentItem(
                item_id="deepseek-first", source_id="source-a", source_name="Source A",
                category="模型", title="DeepSeek 推出 V4-Flash 视觉模型，API 新增多模态图像输入支持",
                url="https://example.com/first", summary="DeepSeek 发布多模态视觉模型并上线 API。",
                published_at=published,
            )
            second = ContentItem(
                item_id="deepseek-second", source_id="source-b", source_name="Source B",
                category="模型", title="DeepSeek 发布 V4-Flash-Vision-Exp 多模态实验模型并上线 API 平台",
                url="https://example.com/second", summary="DeepSeek 发布多模态视觉实验模型并上线 API。",
                published_at=published + timedelta(minutes=20),
            )
            first_outcome = process_item(store, first, analyzer, notifier)
            second_outcome = process_item(store, second, analyzer, notifier)

            self.assertTrue(first_outcome.sent)
            self.assertTrue(second_outcome.analyzed)
            self.assertFalse(second_outcome.sent)
            self.assertEqual(len(notifier.messages), 1)
            row = store.connection.execute(
                "SELECT decision, raw_json FROM analyses WHERE item_id=?", (second.item_id,)
            ).fetchone()
            self.assertEqual(row["decision"], "ignore")
            raw = json.loads(row["raw_json"])
            self.assertEqual(raw["_deduplication"]["reason"], "semantic_duplicate")
            self.assertEqual(raw["_deduplication"]["duplicate_of_item_id"], first.item_id)
            self.assertEqual(store.pending_deliveries(), [])
        finally:
            store.close()
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
