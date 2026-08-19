from __future__ import annotations

import argparse
import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from app.adapters.langfuse.prompts import build_prompt_provider
from app.adapters.llm.deepseek import RuleBasedAnalyzer, build_analyzer
from app.adapters.sources.rss import RSSSourceAdapter
from app.adapters.sources.changelog import DocusaurusChangelogSourceAdapter
from app.adapters.sources.email import EmailSourceAdapter
from app.adapters.sources.sitemap import SitemapSourceAdapter
from app.adapters.sources.openai_changelog import OpenAIChangelogSourceAdapter
from app.adapters.sources.gemini_changelog import GeminiChangelogSourceAdapter
from app.adapters.sources.x import XSourceAdapter
from app.adapters.telegram.bot import build_notifier
from app.application.pipeline import process_item, render_digest, render_message, send_pending
from app.domain.models import AnalysisResult, ContentItem, DigestReport
from app.domain.policies import NotificationPolicy
from app.infrastructure.store import SQLiteStore
from app.infrastructure.config import load_dotenv
from app.ports.interfaces import ContentEnricher


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "sources.json"
DEFAULT_PUBLISHING_CONFIG = ROOT / "config" / "publishing.json"
DEFAULT_DB = ROOT / "data" / "runtime.db"
STOP = False


def load_sources(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [source for source in data.get("sources", []) if source.get("enabled", True)]


def load_notification_policy(path: Path) -> NotificationPolicy:
    data = json.loads(path.read_text(encoding="utf-8"))
    telegram = data.get("telegram", {})
    priorities = frozenset(str(value).upper() for value in telegram.get("allowed_priorities", ["S", "A"]))
    confidence = float(telegram.get("min_confidence", 0.75))
    if not priorities.issubset({"S", "A", "B"}):
        raise ValueError("publishing.json 中 allowed_priorities 只能包含 S、A、B")
    if not 0 <= confidence <= 1:
        raise ValueError("publishing.json 中 min_confidence 必须在 0 到 1 之间")
    return NotificationPolicy(priorities, confidence)


def build_source_adapter(source: dict):
    source_type = str(source.get("source_type", "rss")).lower()
    if source_type == "rss":
        return RSSSourceAdapter()
    if source_type == "docusaurus_changelog":
        return DocusaurusChangelogSourceAdapter()
    if source_type == "openai_changelog":
        return OpenAIChangelogSourceAdapter()
    if source_type == "gemini_changelog":
        return GeminiChangelogSourceAdapter()
    if source_type == "email":
        return EmailSourceAdapter()
    if source_type == "sitemap":
        return SitemapSourceAdapter()
    if source_type == "x":
        return XSourceAdapter()
    raise ValueError(f"不支持的 source_type: {source_type}")


def run_once(
    store: SQLiteStore,
    sources: list[dict],
    analyzer,
    notifier=None,
    baseline=False,
    notification_policy: NotificationPolicy | None = None,
) -> dict[str, int]:
    job_id = store.begin_job()
    discovered = analyzed = sent = errors = 0
    last_error = None
    if not baseline and notifier is not None:
        sent += send_pending(store, notifier)
    for source in sources:
        adapter = build_source_adapter(source)
        first_poll_baseline = (
            not baseline
            and bool(source.get("baseline_on_first_poll", False))
            and store.item_count() > 0
            and not store.source_state_exists(source["id"])
        )
        source_item_count = 0
        source_error = None
        try:
            for item in adapter.fetch(source):
                source_item_count += 1
                if baseline or first_poll_baseline:
                    if store.save_item(item, status="baselined"):
                        discovered += 1
                    continue
                if store.item_status(item.item_id) is not None:
                    continue
                try:
                    if isinstance(adapter, ContentEnricher):
                        item = adapter.enrich(item, source)
                    outcome = process_item(store, item, analyzer, notifier, notification_policy)
                    discovered += int(outcome.created)
                    analyzed += int(outcome.analyzed)
                    sent += int(outcome.sent)
                    errors += int(outcome.failed)
                except Exception as exc:
                    errors += 1
                    last_error = f"{source.get('name', source.get('id'))} / {item.title}: {exc}"
                    source_error = last_error
                    print(f"[WARN] {last_error}")
        except Exception as exc:
            errors += 1
            last_error = f"{source.get('name', source.get('id'))}: {exc}"
            source_error = last_error
            print(f"[WARN] {last_error}")
        finally:
            store.mark_source_result(
                source["id"], int(source.get("poll_interval_minutes", 30)), source_item_count, source_error
            )
    store.finish_job(job_id, discovered, analyzed, sent, errors, last_error)
    return {"discovered": discovered, "analyzed": analyzed, "sent": sent, "errors": errors}


def daemon(store: SQLiteStore, sources: list[dict], analyzer, notifier, notification_policy: NotificationPolicy) -> None:
    interval = int(os.environ.get("WORKER_TICK_SECONDS", "15"))
    while not STOP:
        result = run_daemon_tick(store, sources, analyzer, notifier, notification_policy)
        if result is not None:
            print(f"[INFO] run={result}")
        for _ in range(interval):
            if STOP:
                break
            time.sleep(1)


def run_daemon_tick(
    store: SQLiteStore,
    sources: list[dict],
    analyzer,
    notifier,
    notification_policy: NotificationPolicy | None = None,
) -> dict[str, int] | None:
    due_sources = [source for source in sources if store.source_is_due(source["id"])]
    if due_sources:
        return run_once(store, due_sources, analyzer, notifier, notification_policy=notification_policy)

    sent = send_pending(store, notifier)
    if sent:
        return {"discovered": 0, "analyzed": 0, "sent": sent, "errors": 0}
    return None


def main() -> int:
    global STOP
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Aex AI 情报自动推送 Worker")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--publishing-config", type=Path, default=DEFAULT_PUBLISHING_CONFIG)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--once", action="store_true", help="运行一轮")
    parser.add_argument("--bootstrap", action="store_true", help="建立历史基线，不发送")
    parser.add_argument("--daemon", action="store_true", help="常驻自动轮询")
    parser.add_argument("--dry-run", action="store_true", help="分析并入队，但不发送 Telegram")
    parser.add_argument("--status", action="store_true", help="显示运行状态")
    parser.add_argument("--review", action="store_true", help="显示待人工复核的内容")
    parser.add_argument("--limit", type=int, default=50, help="--review 最多显示条数")
    parser.add_argument("--prompt-status", action="store_true", help="检查当前 Prompt 来源和版本")
    parser.add_argument("--preview-template", action="store_true", help="预览 Telegram HTML 模板，不发送")
    parser.add_argument("--preview-digest", action="store_true", help="预览日报/周报共用模板，不发送")
    args = parser.parse_args()
    sources = load_sources(args.config)
    notification_policy = load_notification_policy(args.publishing_config)
    store = SQLiteStore(args.db)
    if args.status:
        print(json.dumps(store.status_summary(), ensure_ascii=False, indent=2))
        store.close()
        return 0
    if args.review:
        rows = [dict(row) for row in store.review_items(args.limit)]
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        store.close()
        return 0
    if args.prompt_status:
        _, version = build_prompt_provider().get_prompt()
        print(json.dumps({"prompt_version": version, "remote": version.startswith("langfuse:")}, ensure_ascii=False, indent=2))
        store.close()
        return 0
    if args.preview_template:
        sample = ContentItem(
            item_id="preview", source_id="preview", source_name="OpenAI News", category="模型",
            title="示例：某 AI 公司发布新一代模型与 API",
            url="https://example.com/ai-release",
            summary="新模型开放 API，并在推理能力、上下文长度和调用成本方面进行了更新。",
            published_at=datetime.now(timezone.utc),
        )
        result = AnalysisResult(
            decision="notify", priority="S", category="AI 前沿信息",
            summary="新模型及 API 正式开放，关键能力、上下文和价格均有变化。",
            why_it_matters="可能直接影响模型选型、现有工作流成本和后续内容选题。",
            suggested_action="立即查看官方说明并评估是否需要测试或迁移。", confidence=0.95,
        )
        print(render_message(sample, result))
        store.close()
        return 0
    if args.preview_digest:
        report = DigestReport(
            report_title="AI 日报", period_label="2026-08-19",
            overview="今日收集到的高价值 AI 信息摘要。",
            frontier_items="1. 新模型和 API 更新\n2. 重要研究与行业变化",
            application_items="1. Agent 工作流\n2. 值得关注的 GitHub AI 项目",
            key_takeaways="模型能力持续提升，实际应用和工作流正在加速落地。",
        )
        print(render_digest(report))
        store.close()
        return 0
    analyzer = RuleBasedAnalyzer() if args.bootstrap else build_analyzer()
    notifier = None if args.bootstrap or args.dry_run else build_notifier()

    def stop_handler(signum, frame):
        global STOP
        STOP = True
        print(f"[INFO] received signal {signum}, stopping after current work")

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    try:
        if args.bootstrap:
            print(f"[INFO] bootstrap={run_once(store, sources, analyzer, baseline=True)}")
        elif args.daemon:
            if store.item_count() == 0:
                print("[INFO] empty database; establishing baseline without sending")
                print(f"[INFO] bootstrap={run_once(store, sources, analyzer, baseline=True)}")
            daemon(store, sources, analyzer, notifier, notification_policy)
        else:
            if store.item_count() == 0:
                print("[INFO] empty database; establishing baseline without sending")
                print(f"[INFO] bootstrap={run_once(store, sources, analyzer, baseline=True)}")
            else:
                print(f"[INFO] run={run_once(store, sources, analyzer, notifier, notification_policy=notification_policy)}")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
