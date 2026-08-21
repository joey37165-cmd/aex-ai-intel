"""Build source adapters from declarative source configuration."""

from __future__ import annotations

from app.adapters.sources.changelog import DocusaurusChangelogSourceAdapter
from app.adapters.sources.email import EmailSourceAdapter
from app.adapters.sources.gemini_changelog import GeminiChangelogSourceAdapter
from app.adapters.sources.openai_changelog import OpenAIChangelogSourceAdapter
from app.adapters.sources.rss import RSSSourceAdapter
from app.adapters.sources.sitemap import SitemapSourceAdapter
from app.adapters.sources.x import XSourceAdapter


SOURCE_ADAPTERS = {
    "rss": RSSSourceAdapter,
    "docusaurus_changelog": DocusaurusChangelogSourceAdapter,
    "openai_changelog": OpenAIChangelogSourceAdapter,
    "gemini_changelog": GeminiChangelogSourceAdapter,
    "email": EmailSourceAdapter,
    "sitemap": SitemapSourceAdapter,
    "x": XSourceAdapter,
}


def build_source_adapter(source: dict):
    source_type = str(source.get("source_type", "rss")).strip().lower()
    adapter_type = SOURCE_ADAPTERS.get(source_type)
    if adapter_type is None:
        raise ValueError(f"不支持的 source_type: {source_type}")
    return adapter_type()
