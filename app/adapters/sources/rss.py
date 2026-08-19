from __future__ import annotations

from collections.abc import Iterable

from app.domain.models import ContentItem
from app.adapters.sources.parser import fetch_feed


class RSSSourceAdapter:
    """RSS/Atom adapter reusing the verified PoC parser during migration."""

    def fetch(self, source: dict) -> Iterable[ContentItem]:
        for item in fetch_feed(source):
            yield ContentItem(
                item_id=item.item_id,
                source_id=source["id"],
                source_name=item.source,
                category=item.category,
                title=item.title,
                url=item.url,
                summary=item.summary,
                published_at=item.published_at,
                image_url=item.image_url,
            )
