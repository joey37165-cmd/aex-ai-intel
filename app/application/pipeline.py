from __future__ import annotations

import html
import os
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.domain.models import AnalysisResult, ContentItem, DigestReport, ProcessOutcome
from app.domain.policies import NotificationPolicy
from app.domain.status import ItemStatus
from app.infrastructure.store import SQLiteStore
from app.ports.interfaces import TemplateProvider


CHINA_TIMEZONE = timezone(timedelta(hours=8))
_EMOJI_RE = re.compile(
    "["
    "\\U0001F1E6-\\U0001F1FF"  # flags
    "\\U0001F300-\\U0001FAFF"  # pictographs and symbols
    "\\U00002300-\\U000023FF"  # technical symbols
    "\\U000025A0-\\U000027BF"  # shapes and dingbats
    "\\U00002B00-\\U00002BFF"  # miscellaneous symbols
    "\\u200d\\ufe0f\\u20e3"
    "]+"
)


def clean_display_title(value: str, limit: int = 300) -> str:
    text = _EMOJI_RE.sub("", value or "")
    text = re.sub(r"(?:\[\s*\]|【\s*】|\(\s*\)|（\s*）)", "", text)
    text = re.sub(r"\\s+", " ", text).strip(" -|:：")
    if len(text) > limit:
        text = f"{text[:limit - 1].rstrip()}…"
    return text or "AI 情报更新"


def normalize_category(value: str) -> str:
    text = str(value or "").strip().lower()
    app_terms = ("应用", "工具", "agent", "工作流", "workflow", "github", "变现")
    return "AI 应用" if any(term in text for term in app_terms) else "AI 前沿信息"


def format_time(value: str | None) -> str:
    if not value:
        return "时间未知"
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(CHINA_TIMEZONE).strftime("%Y-%m-%d %H:%M 北京时间")
    except ValueError:
        return value


DEFAULT_TEMPLATE = Path(__file__).resolve().parents[2] / "config" / "templates" / "telegram.html"
DEFAULT_DIGEST_TEMPLATE = Path(__file__).resolve().parents[2] / "config" / "templates" / "telegram_digest.html"


def _template_content(
    template_id: str,
    path: Path,
    fallback: str,
    template_provider: TemplateProvider | None,
) -> str:
    if template_provider is not None:
        try:
            published = template_provider.get_published_template(template_id)
            if published:
                return published
        except Exception:
            pass
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return fallback


def render_message(
    item: ContentItem,
    result: AnalysisResult,
    template_path: Path | None = None,
    template_provider: TemplateProvider | None = None,
) -> str:
    def esc(value: str, limit: int | None = None) -> str:
        text = re.sub(r"\s+", " ", value or "").strip()
        if limit and len(text) > limit:
            text = f"{text[:limit - 1].rstrip()}…"
        return html.escape(text)

    published = item.published_at.isoformat() if item.published_at else None
    values = {
        "header": esc(result.category),
        "category_line": esc(normalize_category(result.category)),
        "title": esc(clean_display_title(result.display_title or item.title)), "summary": esc(result.summary, 240),
        "why_it_matters": esc(result.why_it_matters), "suggested_action": esc(result.suggested_action),
        "source": esc(item.source_name, 100), "time": format_time(published),
        "url": html.escape(item.url, quote=True),
        "my_x_link": _creator_x_link(),
        "links_line": _links_line(item.url),
    }
    template = _template_content(
        "realtime",
        template_path or DEFAULT_TEMPLATE,
        "<b>【{category_line}】{title}</b>\n\n{summary}\n\n<b>【重点】</b>\n{why_it_matters}\n\n{links_line}",
        template_provider,
    )
    return template.format(**values)


def render_digest(
    report: DigestReport,
    template_path: Path | None = None,
    template_provider: TemplateProvider | None = None,
) -> str:
    def esc(value: str, limit: int | None = None) -> str:
        text = str(value or "").strip()
        if limit and len(text) > limit:
            text = f"{text[:limit - 1].rstrip()}…"
        return html.escape(text)

    template = _template_content(
        "digest",
        template_path or DEFAULT_DIGEST_TEMPLATE,
        (
            "<b>{report_title} · {period_label}</b>\n\n{overview}\n\n"
            "<b>AI 前沿信息</b>\n{frontier_items}\n\n"
            "<b>AI 应用</b>\n{application_items}\n\n"
            "<b>关键观察</b>\n{key_takeaways}\n\n{source_links}\n{my_x_link}"
        ),
        template_provider,
    )
    values = {
        "report_title": esc(report.report_title, 40),
        "period_label": esc(report.period_label, 80),
        "overview": esc(report.overview, 500),
        "frontier_items": esc(report.frontier_items, 1800),
        "application_items": esc(report.application_items, 1800),
        "key_takeaways": esc(report.key_takeaways, 1000),
        "source_links": report.source_links,
        "my_x_link": _creator_x_link(),
    }
    rendered = template.format(**values)
    if len(rendered) > 4000 and values["source_links"]:
        values["source_links"] = ""
        rendered = template.format(**values)
    return rendered


def _creator_x_link() -> str:
    value = os.environ.get("CREATOR_X_URL", "").strip() or "https://x.com/axe0x0"
    if not value.startswith(("https://x.com/", "https://twitter.com/")):
        return ""
    return f'<a href="{html.escape(value, quote=True)}">𝕏 Aex0x0</a>'


def _links_line(article_url: str) -> str:
    original = f'<a href="{html.escape(article_url, quote=True)}">🔗 阅读原文</a>'
    creator = _creator_x_link()
    return f"{original} · {creator}" if creator else original


def deliver_message(notifier, item: ContentItem, text: str) -> str:
    if item.image_url and hasattr(notifier, "send_photo") and len(text) <= 1024:
        return notifier.send_photo(item.image_url, text)
    return notifier.send(text)


def process_item(
    store: SQLiteStore,
    item: ContentItem,
    analyzer,
    notifier=None,
    notification_policy: NotificationPolicy | None = None,
    template_provider: TemplateProvider | None = None,
) -> ProcessOutcome:
    created = store.save_item(item)
    if not created and store.item_status(item.item_id) == "baselined":
        return ProcessOutcome()
    if not created and store.has_analysis(item.item_id):
        return ProcessOutcome()
    result = analyzer.analyze(item)
    result = (notification_policy or NotificationPolicy()).apply(result)
    store.save_analysis(
        item.item_id,
        result,
        model_name=getattr(analyzer, "model_name", "unknown"),
        prompt_version=getattr(analyzer, "prompt_version", "unknown"),
    )
    if result.decision != ItemStatus.NOTIFY:
        return ProcessOutcome(created=created, analyzed=True)
    duplicate = store.find_recent_notification_duplicate(item)
    if duplicate is not None:
        raw = dict(result.raw)
        raw["_deduplication"] = {
            "reason": "semantic_duplicate",
            "duplicate_of_item_id": duplicate["item_id"],
            "duplicate_source": duplicate["source_name"],
        }
        result = replace(result, decision="ignore", raw=raw)
        store.save_analysis(
            item.item_id,
            result,
            model_name=getattr(analyzer, "model_name", "unknown"),
            prompt_version=getattr(analyzer, "prompt_version", "unknown"),
        )
        return ProcessOutcome(created=created, analyzed=True)
    store.queue_delivery(item.item_id)
    if notifier is None:
        return ProcessOutcome(created=created, analyzed=True)
    for row in store.pending_deliveries():
        if row["item_id"] != item.item_id:
            continue
        try:
            message_id = deliver_message(
                notifier, item, render_message(item, result, template_provider=template_provider)
            )
            store.mark_sent(item.item_id, message_id)
            return ProcessOutcome(created=created, analyzed=True, sent=True)
        except Exception as exc:
            store.mark_retry(item.item_id, str(exc), int(row["attempts"]) + 1)
            return ProcessOutcome(created=created, analyzed=True, failed=True)
    return ProcessOutcome(created=created, analyzed=True)


def send_pending(
    store: SQLiteStore,
    notifier,
    template_provider: TemplateProvider | None = None,
) -> int:
    sent = 0
    for row in store.pending_deliveries():
        item = ContentItem(
            item_id=row["item_id"], source_id="stored", source_name=row["source_name"],
            category=row["analysis_category"], title=row["title"], url=row["url"], summary=row["analysis_summary"],
            published_at=datetime.fromisoformat(row["published_at"]) if row["published_at"] else None,
            image_url=row["image_url"],
        )
        result = AnalysisResult(
            decision="notify", priority=row["priority"], category=row["analysis_category"],
            summary=row["analysis_summary"], why_it_matters=row["why_it_matters"],
            suggested_action=row["suggested_action"], confidence=1.0,
            display_title=row["display_title"] or row["title"],
        )
        try:
            message_id = deliver_message(
                notifier, item, render_message(item, result, template_provider=template_provider)
            )
            store.mark_sent(row["item_id"], message_id)
            sent += 1
        except Exception as exc:
            store.mark_retry(row["item_id"], str(exc), int(row["attempts"]) + 1)
    return sent
