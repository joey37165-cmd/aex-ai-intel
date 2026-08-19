from __future__ import annotations

import hashlib
import html
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any


USER_AGENT = "Aex-AI-Intel/0.1"


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)

    def text(self) -> str:
        return " ".join(self.parts)


@dataclass(frozen=True)
class FeedItem:
    item_id: str
    source: str
    category: str
    title: str
    url: str
    summary: str
    published_at: datetime | None
    image_url: str | None = None


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def direct_child_text(node: ET.Element, names: set[str]) -> str:
    for child in list(node):
        if local_name(child.tag) in names:
            return "".join(child.itertext()).strip()
    return ""


def entry_link(node: ET.Element) -> str:
    for child in list(node):
        if local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href", "").strip()
        rel = child.attrib.get("rel", "alternate")
        if href and rel in {"alternate", ""}:
            return href
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return ""


def entry_image(node: ET.Element, article_url: str) -> str | None:
    for element in node.iter():
        name = local_name(element.tag)
        if name not in {"enclosure", "content", "thumbnail", "image"}:
            continue
        candidate = element.attrib.get("url") or element.attrib.get("href") or ""
        candidate = urllib.parse.urljoin(article_url, candidate.strip())
        if candidate.startswith(("http://", "https://")):
            return candidate
    return None


def html_to_text(value: str) -> str:
    parser = TextExtractor()
    try:
        parser.feed(value)
    except Exception:
        return re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(parser.text())).strip()


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def make_item_id(source: str, external_id: str, url: str, title: str) -> str:
    basis = external_id or url or title
    return hashlib.sha256(f"{source}\n{basis}".encode("utf-8")).hexdigest()


def parse_feed(payload: bytes, source: dict[str, Any]) -> list[FeedItem]:
    root = ET.fromstring(payload)
    nodes = [node for node in root.iter() if local_name(node.tag) in {"item", "entry"}]
    include_keywords = [
        str(keyword).strip().casefold()
        for keyword in source.get("include_keywords", [])
        if str(keyword).strip()
    ]
    items: list[FeedItem] = []
    for node in nodes:
        title = html_to_text(direct_child_text(node, {"title"}))
        url = entry_link(node)
        external_id = direct_child_text(node, {"guid", "id"})
        summary = html_to_text(direct_child_text(node, {"description", "summary", "content", "encoded"}))
        published_at = parse_datetime(direct_child_text(node, {"pubdate", "published", "updated", "date"}))
        image_url = entry_image(node, url)
        if include_keywords:
            searchable = f"{title} {summary}".casefold()
            if not any(
                re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", searchable, flags=re.IGNORECASE)
                for keyword in include_keywords
            ):
                continue
        if title and url:
            items.append(FeedItem(
                item_id=make_item_id(source["name"], external_id, url, title),
                source=source["name"], category=source.get("category", "AI 情报"), title=title,
                url=url, summary=summary, published_at=published_at, image_url=image_url,
            ))
    return sorted(items, key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def fetch_feed(source: dict[str, Any]) -> list[FeedItem]:
    feed_url = source.get("feed_url") or source.get("url")
    if not feed_url:
        raise ValueError(f"{source.get('name', '未命名来源')} 缺少 feed_url")
    request = urllib.request.Request(feed_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return parse_feed(response.read(), source)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{source['name']} 返回 HTTP {exc.code}") from exc
