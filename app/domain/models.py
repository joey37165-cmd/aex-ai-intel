from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ContentItem:
    item_id: str
    source_id: str
    source_name: str
    category: str
    title: str
    url: str
    summary: str
    published_at: datetime | None
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    image_url: str | None = None


@dataclass(frozen=True)
class EventFeatures:
    event_type: str = "other"
    organization: str | None = None
    product: str | None = None
    version: str | None = None
    core_claim: str = ""
    event_time: str | None = None


@dataclass(frozen=True)
class AnalysisResult:
    decision: str
    priority: str
    category: str
    summary: str
    why_it_matters: str
    suggested_action: str
    confidence: float
    raw: dict[str, Any] = field(default_factory=dict)
    display_title: str = ""
    event: EventFeatures = field(default_factory=EventFeatures)


@dataclass(frozen=True)
class DeduplicationResult:
    relationship: str = "independent"
    confidence: float = 0.0
    reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DigestReport:
    report_title: str
    period_label: str
    overview: str
    frontier_items: str
    application_items: str
    key_takeaways: str
    source_links: str = ""


@dataclass(frozen=True)
class DigestCandidate:
    item_id: str
    source_name: str
    title: str
    url: str
    category: str
    priority: str
    summary: str
    why_it_matters: str
    occurred_at: datetime


@dataclass(frozen=True)
class ReportWindow:
    report_id: str
    report_type: str
    period_start: datetime
    period_end: datetime


@dataclass(frozen=True)
class ProcessOutcome:
    created: bool = False
    analyzed: bool = False
    sent: bool = False
    failed: bool = False
