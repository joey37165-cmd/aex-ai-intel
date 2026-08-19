from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

from app.adapters.sources.parser import USER_AGENT, html_to_text, make_item_id
from app.domain.models import ContentItem


MONTH_DATE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{1,2}),\s*(20\d{2})$"
)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html_to_text(value or "")).strip().replace("\u200b", "")


def _title_from_body(body: str) -> str:
    first_sentence = re.split(r"(?<=[.!?])\s+", body, maxsplit=1)[0]
    if len(first_sentence) <= 180:
        return first_sentence
    return f"{first_sentence[:179].rstrip()}…"


class _GeminiChangelogParser(HTMLParser):
    def __init__(self, source: dict) -> None:
        super().__init__()
        self.source = source
        self.items: list[ContentItem] = []
        self.heading = False
        self.heading_parts: list[str] = []
        self.current_date: datetime | None = None
        self.li_depth = 0
        self.current_parts: list[str] = []
        self.strong_depth = 0
        self.current_title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h2":
            self.heading = True
            self.heading_parts = []
            return
        if tag == "li":
            if self.li_depth == 0:
                self.current_parts = []
                self.current_title_parts = []
            self.li_depth += 1
            return
        if tag == "strong" and self.li_depth == 1 and not self.current_title_parts:
            self.strong_depth = 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2" and self.heading:
            value = _clean(" ".join(self.heading_parts))
            match = MONTH_DATE.match(value)
            self.current_date = (
                datetime.strptime(value, "%B %d, %Y").replace(tzinfo=timezone.utc)
                if match
                else self.current_date
            )
            self.heading = False
            self.heading_parts = []
            return
        if tag == "strong" and self.strong_depth:
            self.strong_depth = 0
            return
        if tag == "li" and self.li_depth:
            self.li_depth -= 1
            if self.li_depth == 0:
                self._flush()

    def handle_data(self, data: str) -> None:
        value = _clean(data)
        if not value:
            return
        if self.heading:
            self.heading_parts.append(value)
        if self.li_depth:
            self.current_parts.append(value)
        if self.strong_depth:
            self.current_title_parts.append(value)

    def close(self) -> None:
        super().close()
        if self.li_depth:
            self.li_depth = 0
            self._flush()

    def _flush(self) -> None:
        if self.current_date is None or not self.current_parts:
            self.current_parts = []
            self.current_title_parts = []
            return
        body = _clean(" ".join(self.current_parts))
        if not body:
            return
        title = _clean(" ".join(self.current_title_parts)) or _title_from_body(body)
        limit = max(500, min(int(self.source.get("summary_max_chars", 8000)), 20000))
        summary = body[:limit]
        digest = hashlib.sha256(summary.encode("utf-8")).hexdigest()
        date_value = self.current_date.date().isoformat()
        url = f"{str(self.source['page_url']).rstrip('/')}#{self.current_date.strftime('%m-%d-%Y')}"
        external_id = f"{date_value}\n{title}\n{digest}"
        self.items.append(ContentItem(
            item_id=make_item_id(self.source["name"], external_id, url, title),
            source_id=self.source["id"],
            source_name=self.source["name"],
            category=self.source.get("category", "AI 情报"),
            title=title,
            url=url,
            summary=summary,
            published_at=self.current_date,
        ))
        self.current_parts = []
        self.current_title_parts = []


def parse_gemini_changelog(payload: bytes, source: dict) -> list[ContentItem]:
    parser = _GeminiChangelogParser(source)
    parser.feed(payload.decode("utf-8", errors="replace"))
    parser.close()
    parser.items.sort(key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    max_items = max(1, min(int(source.get("max_items", 500)), 2000))
    return parser.items[:max_items]


class GeminiChangelogSourceAdapter:
    def fetch(self, source: dict) -> list[ContentItem]:
        page_url = str(source.get("page_url", "")).strip()
        if not page_url.startswith(("http://", "https://")):
            raise ValueError(f"{source.get('name', '未命名来源')} 缺少有效 page_url")
        request = urllib.request.Request(page_url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=float(source.get("timeout_seconds", 25))) as response:
                return parse_gemini_changelog(response.read(), source)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{source['name']} Changelog 返回 HTTP {exc.code}") from exc
