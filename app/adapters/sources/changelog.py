from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

from app.adapters.sources.parser import USER_AGENT, html_to_text, make_item_id
from app.domain.models import ContentItem


class _DocusaurusChangelogParser(HTMLParser):
    def __init__(self, source: dict) -> None:
        super().__init__()
        self.source = source
        self.items: list[ContentItem] = []
        self.article_depth = 0
        self.current_date = ""
        self.current_title = ""
        self.current_anchor = ""
        self.current_parts: list[str] = []
        self.heading_level = ""
        self.heading_parts: list[str] = []
        self.ignore_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag == "article":
            self.article_depth += 1
            return
        if self.article_depth == 0:
            return
        if tag in {"script", "style"}:
            self.ignore_depth += 1
            return
        if tag == "a" and "hash-link" in values.get("class", ""):
            self.ignore_depth += 1
            return
        if tag in {"h2", "h3"}:
            if tag == "h2":
                self._flush()
            elif self.current_title:
                self._flush()
            self.heading_level = tag
            self.heading_parts = []
            self.current_anchor = values.get("id", "") if tag == "h3" else ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "article":
            self._flush()
            self.article_depth = max(0, self.article_depth - 1)
            return
        if self.article_depth == 0:
            return
        if tag in {"script", "style"} and self.ignore_depth:
            self.ignore_depth -= 1
            return
        if tag == "a" and self.ignore_depth:
            self.ignore_depth -= 1
            return
        if tag == self.heading_level:
            value = _clean(" ".join(self.heading_parts))
            if tag == "h2":
                match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", value)
                self.current_date = match.group(1) if match else ""
            elif tag == "h3":
                self.current_title = value
            self.heading_level = ""
            self.heading_parts = []

    def handle_data(self, data: str) -> None:
        if self.article_depth == 0 or self.ignore_depth:
            return
        value = _clean(data)
        if not value:
            return
        if self.heading_level:
            self.heading_parts.append(value)
        elif self.current_title:
            self.current_parts.append(value)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        if not self.current_date or not self.current_title:
            self.current_title = ""
            self.current_parts = []
            return
        summary = _clean(" ".join(self.current_parts))
        limit = max(500, min(int(self.source.get("summary_max_chars", 8000)), 20000))
        summary = summary[:limit]
        digest = hashlib.sha256(summary.encode("utf-8")).hexdigest()
        external_id = f"{self.current_date}\n{self.current_title}\n{digest}"
        base_url = str(self.source["page_url"])
        url = f"{base_url.rstrip('/')}#{urllib.parse.quote(self.current_anchor)}" if self.current_anchor else base_url
        published = datetime.strptime(self.current_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        self.items.append(ContentItem(
            item_id=make_item_id(self.source["name"], external_id, url, self.current_title),
            source_id=self.source["id"],
            source_name=self.source["name"],
            category=self.source.get("category", "AI 情报"),
            title=self.current_title,
            url=url,
            summary=summary,
            published_at=published,
        ))
        self.current_title = ""
        self.current_anchor = ""
        self.current_parts = []


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html_to_text(value or "")).strip().replace("\u200b", "")


def parse_changelog(payload: bytes, source: dict) -> list[ContentItem]:
    parser = _DocusaurusChangelogParser(source)
    parser.feed(payload.decode("utf-8", errors="replace"))
    parser.close()
    parser.items.sort(key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    max_items = max(1, min(int(source.get("max_items", 100)), 1000))
    return parser.items[:max_items]


class DocusaurusChangelogSourceAdapter:
    def fetch(self, source: dict) -> list[ContentItem]:
        page_url = str(source.get("page_url", "")).strip()
        if not page_url.startswith(("http://", "https://")):
            raise ValueError(f"{source.get('name', '未命名来源')} 缺少有效 page_url")
        request = urllib.request.Request(page_url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=float(source.get("timeout_seconds", 25))) as response:
                return parse_changelog(response.read(), source)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{source['name']} Change Log 返回 HTTP {exc.code}") from exc
