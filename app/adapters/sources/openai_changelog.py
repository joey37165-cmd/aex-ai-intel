from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

from app.adapters.sources.parser import USER_AGENT, html_to_text, make_item_id
from app.domain.models import ContentItem


MONTH_PATTERN = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December),\s*(20\d{2})$"
)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html_to_text(value or "")).strip()


def _title_from_summary(summary: str) -> str:
    first_sentence = re.split(r"(?<=[.!?])\s+", summary, maxsplit=1)[0]
    if len(first_sentence) <= 180:
        return first_sentence
    return f"{first_sentence[:179].rstrip()}…"


class _OpenAIChangelogParser(HTMLParser):
    def __init__(self, source: dict) -> None:
        super().__init__()
        self.source = source
        self.items: list[ContentItem] = []
        self.seen_changelog_heading = False
        self.heading_level = ""
        self.heading_parts: list[str] = []
        self.current_month = ""
        self.current_year = ""
        self.entry_depth = 0
        self.badge_depth = 0
        self.badge_parts: list[str] = []
        self.badges: list[str] = []
        self.markdown_depth = 0
        self.markdown_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        css_class = values.get("class", "")
        if self.entry_depth:
            if tag == "div":
                self.entry_depth += 1
                if self.badge_depth:
                    self.badge_depth += 1
                if self.markdown_depth:
                    self.markdown_depth += 1
                if values.get("data-variant") in {"outline", "soft"}:
                    self.badge_depth = 1
                    self.badge_parts = []
                if "ChangelogMarkdown" in css_class:
                    self.markdown_depth = 1
            return
        if tag == "h1":
            self.heading_level = tag
            self.heading_parts = []
        elif tag == "h3" and self.seen_changelog_heading:
            self.heading_level = tag
            self.heading_parts = []
        elif tag == "div" and "grid-cols-[3rem_1fr]" in css_class and self.current_year:
            self.entry_depth = 1
            self.badges = []
            self.markdown_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self.entry_depth and tag == "div":
            if self.badge_depth:
                self.badge_depth -= 1
                if self.badge_depth == 0:
                    badge = _clean(" ".join(self.badge_parts))
                    if badge:
                        self.badges.append(badge)
                    self.badge_parts = []
            if self.markdown_depth:
                self.markdown_depth -= 1
            self.entry_depth -= 1
            if self.entry_depth == 0:
                self._flush_entry()
            return
        if tag == self.heading_level:
            value = _clean(" ".join(self.heading_parts))
            if tag == "h1" and value == "Changelog":
                self.seen_changelog_heading = True
            elif tag == "h3":
                match = MONTH_PATTERN.match(value)
                if match:
                    self.current_month, self.current_year = match.groups()
            self.heading_level = ""
            self.heading_parts = []

    def handle_data(self, data: str) -> None:
        value = _clean(data)
        if not value:
            return
        if self.heading_level:
            self.heading_parts.append(value)
        if self.badge_depth:
            self.badge_parts.append(value)
        if self.markdown_depth:
            self.markdown_parts.append(value)

    def _flush_entry(self) -> None:
        if not self.badges or not self.markdown_parts:
            return
        date_badge = self.badges[0]
        try:
            published = datetime.strptime(
                f"{date_badge} {self.current_year}", "%b %d %Y"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            return
        body = _clean(" ".join(self.markdown_parts))
        if not body:
            return
        labels = self.badges[1:]
        summary = f"[{', '.join(labels)}] {body}" if labels else body
        limit = max(500, min(int(self.source.get("summary_max_chars", 8000)), 20000))
        summary = summary[:limit]
        digest = hashlib.sha256(summary.encode("utf-8")).hexdigest()
        external_id = f"{published.date().isoformat()}\n{'|'.join(labels)}\n{digest}"
        url = str(self.source["page_url"])
        title = _title_from_summary(body)
        self.items.append(ContentItem(
            item_id=make_item_id(self.source["name"], external_id, url, title),
            source_id=self.source["id"],
            source_name=self.source["name"],
            category=self.source.get("category", "AI 情报"),
            title=title,
            url=url,
            summary=summary,
            published_at=published,
        ))


def parse_openai_changelog(payload: bytes, source: dict) -> list[ContentItem]:
    parser = _OpenAIChangelogParser(source)
    parser.feed(payload.decode("utf-8", errors="replace"))
    parser.close()
    parser.items.sort(key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    max_items = max(1, min(int(source.get("max_items", 500)), 2000))
    return parser.items[:max_items]


class OpenAIChangelogSourceAdapter:
    def fetch(self, source: dict) -> list[ContentItem]:
        page_url = str(source.get("page_url", "")).strip()
        if not page_url.startswith(("http://", "https://")):
            raise ValueError(f"{source.get('name', '未命名来源')} 缺少有效 page_url")
        request = urllib.request.Request(page_url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=float(source.get("timeout_seconds", 25))) as response:
                return parse_openai_changelog(response.read(), source)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{source['name']} Changelog 返回 HTTP {exc.code}") from exc
