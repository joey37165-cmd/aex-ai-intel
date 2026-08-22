"""Stable state values shared by the application and persistence layers."""

from __future__ import annotations


class ItemStatus:
    DISCOVERED = "discovered"
    BASELINED = "baselined"
    NOTIFY = "notify"
    IGNORE = "ignore"
    SENT = "sent"


class DeliveryStatus:
    PENDING = "pending"
    RETRY = "retry"
    SENT = "sent"


class ReportStatus:
    PENDING = "pending"
    READY = "ready"
    RETRY = "retry"
    SENT = "sent"


class TemplateStatus:
    PUBLISHED = "published"
    DRAFT = "draft"


ITEM_STATUSES = frozenset({
    ItemStatus.DISCOVERED,
    ItemStatus.BASELINED,
    ItemStatus.NOTIFY,
    ItemStatus.IGNORE,
    ItemStatus.SENT,
})
DELIVERY_STATUSES = frozenset({DeliveryStatus.PENDING, DeliveryStatus.RETRY, DeliveryStatus.SENT})
REPORT_STATUSES = frozenset({ReportStatus.PENDING, ReportStatus.READY, ReportStatus.RETRY, ReportStatus.SENT})
