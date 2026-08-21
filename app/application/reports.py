from __future__ import annotations

import html
import json
from dataclasses import asdict, replace
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.application.pipeline import render_digest
from app.domain.models import DigestCandidate, DigestReport, ReportWindow
from app.ports.repositories import ReportRepository


WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _send_time(value: str) -> time:
    try:
        hour, minute = (int(part) for part in value.split(":", 1))
        return time(hour, minute)
    except (TypeError, ValueError):
        raise ValueError(f"无效的报告发送时间: {value}")


def _latest_boundary(now_local: datetime, section: dict[str, Any], report_type: str) -> datetime:
    scheduled_time = _send_time(str(section.get("send_at", "09:00")))
    boundary = datetime.combine(now_local.date(), scheduled_time, tzinfo=now_local.tzinfo)
    if report_type == "daily":
        if now_local < boundary:
            boundary -= timedelta(days=1)
        return boundary

    weekday = WEEKDAYS.get(str(section.get("weekday", "monday")).lower())
    if weekday is None:
        raise ValueError(f"无效的周报星期配置: {section.get('weekday')}")
    boundary -= timedelta(days=(boundary.weekday() - weekday) % 7)
    if now_local < boundary:
        boundary -= timedelta(days=7)
    return boundary


def due_report_windows(config: dict[str, Any], now: datetime | None = None) -> list[ReportWindow]:
    zone = ZoneInfo(str(config.get("timezone", "Asia/Shanghai")))
    current = _aware_utc(now or datetime.now(timezone.utc))
    now_local = current.astimezone(zone)
    windows: list[ReportWindow] = []
    for report_type, duration in (("daily", timedelta(days=1)), ("weekly", timedelta(days=7))):
        section = config.get(report_type, {})
        if not bool(section.get("enabled", False)):
            continue
        period_end_local = _latest_boundary(now_local, section, report_type)
        catchup_hours = max(0, int(section.get("catchup_hours", 24)))
        if current - period_end_local.astimezone(timezone.utc) > timedelta(hours=catchup_hours):
            continue
        period_end = period_end_local.astimezone(timezone.utc)
        period_start = (period_end_local - duration).astimezone(timezone.utc)
        windows.append(ReportWindow(
            report_id=f"{report_type}:{period_end.isoformat()}",
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
        ))
    return windows


def _period_label(window: ReportWindow, timezone_name: str) -> str:
    zone = ZoneInfo(timezone_name)
    start = window.period_start.astimezone(zone)
    end = window.period_end.astimezone(zone)
    return f"{start:%Y-%m-%d %H:%M} 至 {end:%Y-%m-%d %H:%M}"


def _candidate(row) -> DigestCandidate:
    occurred_at = datetime.fromisoformat(str(row["occurred_at"]))
    return DigestCandidate(
        item_id=str(row["item_id"]),
        source_name=str(row["source_name"]),
        title=str(row["title"]),
        url=str(row["url"]),
        category=str(row["category"]),
        priority=str(row["priority"]),
        summary=str(row["summary"]),
        why_it_matters=str(row["why_it_matters"]),
        occurred_at=_aware_utc(occurred_at),
    )


def _deduplicate(items: list[DigestCandidate]) -> list[DigestCandidate]:
    seen: set[str] = set()
    result: list[DigestCandidate] = []
    for item in items:
        key = item.url.strip().lower() or item.item_id
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _source_links(items: list[DigestCandidate], limit: int = 6) -> str:
    lines = []
    for index, item in enumerate(items[:limit], start=1):
        url = html.escape(item.url, quote=True)
        title = html.escape(item.title[:80].strip())
        lines.append(f'{index}. <a href="{url}">{title}</a>')
    return "\n".join(lines)


def _payload(report: DigestReport) -> dict[str, str]:
    return {key: str(value) for key, value in asdict(report).items()}


def _report_from_payload(value: str) -> DigestReport:
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("报告 payload 必须是 JSON 对象")
    return DigestReport(**{field: str(data.get(field, "")) for field in DigestReport.__dataclass_fields__})


def run_reports_tick(
    store: ReportRepository,
    config: dict[str, Any],
    generator,
    notifier,
    now: datetime | None = None,
    template_provider=None,
) -> dict[str, int]:
    enabled_types = {
        report_type for report_type in ("daily", "weekly")
        if bool(config.get(report_type, {}).get("enabled", False))
    }
    rows = {
        str(row["report_id"]): row
        for row in store.retryable_reports()
        if str(row["report_type"]) in enabled_types
    }
    for window in due_report_windows(config, now):
        row = store.ensure_report(
            window.report_id,
            window.report_type,
            window.period_start.isoformat(),
            window.period_end.isoformat(),
        )
        if row["status"] != "sent":
            rows[window.report_id] = row

    result = {"generated": 0, "sent": 0, "errors": 0}
    timezone_name = str(config.get("timezone", "Asia/Shanghai"))
    for row in sorted(rows.values(), key=lambda value: str(value["period_end"])):
        report_id = str(row["report_id"])
        try:
            if row["payload_json"]:
                report = _report_from_payload(str(row["payload_json"]))
            else:
                window = ReportWindow(
                    report_id=report_id,
                    report_type=str(row["report_type"]),
                    period_start=_aware_utc(datetime.fromisoformat(str(row["period_start"]))),
                    period_end=_aware_utc(datetime.fromisoformat(str(row["period_end"]))),
                )
                section = config.get(window.report_type, {})
                max_items = max(1, min(int(section.get("max_items", 40)), 100))
                candidate_rows = store.report_candidates(
                    window.period_start.isoformat(),
                    window.period_end.isoformat(),
                    min(max_items * 4, 100),
                )
                candidates = _deduplicate([_candidate(candidate_row) for candidate_row in candidate_rows])[:max_items]
                report = generator.generate(window, candidates)
                report = replace(
                    report,
                    period_label=_period_label(window, timezone_name),
                    source_links=_source_links(candidates),
                )
                store.save_report_payload(report_id, _payload(report), generator.prompt_version)
                result["generated"] += 1
            message_id = notifier.send(render_digest(report, template_provider=template_provider))
            store.mark_report_sent(report_id, message_id)
            result["sent"] += 1
        except Exception as exc:
            store.mark_report_retry(report_id, str(exc), int(row["attempts"]) + 1)
            result["errors"] += 1
    return result
