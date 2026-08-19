from __future__ import annotations

import html
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import replace
from datetime import datetime, timezone
from html.parser import HTMLParser

from app.adapters.sources.parser import USER_AGENT, local_name, make_item_id, parse_datetime
from app.domain.models import ContentItem


class _ArticleMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.page_title: list[str] = []
        self.heading: list[str] = []
        self.metadata: dict[str, str] = {}
        self._in_title = False
        self._in_h1 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
        elif tag == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            if key in {"og:title", "og:description", "og:image", "description"}:
                self.metadata[key] = values.get("content", "").strip()
        elif tag == "link" and values.get("rel", "").lower() == "canonical":
            self.metadata["canonical"] = values.get("href", "").strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.page_title.append(data)
        if self._in_h1:
            self.heading.append(data)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _placeholder_title(url: str) -> str:
    slug = urllib.parse.urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    return _clean(slug.replace("-", " ")) or url


def _normalized_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    path = parsed.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def _published_at(values: dict[str, str], url: str, source: dict):
    published = parse_datetime(values.get("lastmod", ""))
    if published is not None:
        return published
    pattern = str(source.get("date_path_regex", "")).strip()
    date_format = str(source.get("date_path_format", "")).strip()
    if not pattern or not date_format:
        return None
    match = re.search(pattern, urllib.parse.urlparse(url).path)
    if not match:
        return None
    value = match.groupdict().get("date") or match.group(1)
    try:
        return datetime.strptime(value, date_format).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _allowed_article_url(url: str, sitemap_url: str, source: dict) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    allowed_hosts = source.get("allowed_hosts") or [urllib.parse.urlparse(sitemap_url).hostname]
    normalized = {str(host).strip().lower() for host in allowed_hosts if host}
    return parsed.hostname.lower() in normalized


def parse_sitemap(payload: bytes, source: dict) -> list[ContentItem]:
    sitemap_url = str(source.get("sitemap_url", "")).strip()
    root = ET.fromstring(payload)
    include_path = str(source.get("include_path_prefix", "")).strip()
    include_path_regex = str(source.get("include_path_regex", "")).strip()
    items: list[ContentItem] = []
    for node in root.iter():
        if local_name(node.tag) != "url":
            continue
        values = {local_name(child.tag): "".join(child.itertext()).strip() for child in list(node)}
        url = values.get("loc", "")
        if not _allowed_article_url(url, sitemap_url, source):
            continue
        path = urllib.parse.urlparse(url).path
        if include_path and not path.startswith(include_path):
            continue
        if include_path_regex and not re.search(include_path_regex, path):
            continue
        items.append(ContentItem(
            item_id=make_item_id(source["name"], url, url, ""),
            source_id=source["id"],
            source_name=source["name"],
            category=source.get("category", "AI 情报"),
            title=_placeholder_title(url),
            url=url,
            summary="",
            published_at=_published_at(values, url, source),
        ))
    items.sort(key=lambda item: item.published_at or parse_datetime("1970-01-01T00:00:00Z"), reverse=True)
    max_items = max(1, min(int(source.get("max_items", 500)), 5000))
    return items[:max_items]


def parse_article(payload: bytes, item: ContentItem) -> ContentItem:
    parser = _ArticleMetadataParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    canonical = urllib.parse.urljoin(item.url, parser.metadata.get("canonical", "").strip())
    if canonical and _normalized_url(canonical) != _normalized_url(item.url):
        raise ValueError(f"文章 canonical 与发现 URL 不一致：{canonical}")
    title = _clean("".join(parser.heading)) or _clean(parser.metadata.get("og:title", ""))
    if not title:
        title = _clean("".join(parser.page_title)) or item.title
    summary = _clean(parser.metadata.get("description", "") or parser.metadata.get("og:description", ""))
    raw_image_url = parser.metadata.get("og:image", "").strip()
    image_url = urllib.parse.urljoin(item.url, raw_image_url) if raw_image_url else item.image_url
    return replace(item, title=title, summary=summary, image_url=image_url)


class SitemapSourceAdapter:
    def fetch(self, source: dict) -> list[ContentItem]:
        sitemap_url = str(source.get("sitemap_url", "")).strip()
        if not sitemap_url:
            raise ValueError(f"{source.get('name', '未命名来源')} 缺少 sitemap_url")
        request = urllib.request.Request(sitemap_url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=float(source.get("timeout_seconds", 25))) as response:
                return parse_sitemap(response.read(), source)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{source['name']} Sitemap 返回 HTTP {exc.code}") from exc

    def enrich(self, item: ContentItem, source: dict) -> ContentItem:
        sitemap_url = str(source.get("sitemap_url", "")).strip()
        if not _allowed_article_url(item.url, sitemap_url, source):
            raise ValueError(f"{source.get('name', source.get('id'))} 文章 URL 不在允许域名内")
        request = urllib.request.Request(item.url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(
                request, timeout=float(source.get("article_timeout_seconds", 25))
            ) as response:
                return parse_article(response.read(), item)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{source['name']} 文章返回 HTTP {exc.code}") from exc
