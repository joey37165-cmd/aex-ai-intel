import unittest
from datetime import datetime, timezone

from app.adapters.sources.sitemap import parse_article, parse_sitemap
from app.domain.models import ContentItem


SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.anthropic.com/news/new-model</loc><lastmod>2026-08-18T10:00:00Z</lastmod></url>
  <url><loc>https://www.anthropic.com/news/news260813</loc></url>
  <url><loc>https://www.anthropic.com/research/paper</loc><lastmod>2026-08-19T10:00:00Z</lastmod></url>
  <url><loc>https://attacker.example/news/injection</loc><lastmod>2026-08-20T10:00:00Z</lastmod></url>
</urlset>"""

ARTICLE = b"""<html><head>
<title>Fallback title</title>
<meta name="description" content="Official model announcement &amp; API details.">
<meta property="og:image" content="/images/model.png">
</head><body><h1>Introducing Claude Test</h1></body></html>"""


def source():
    return {
        "id": "anthropic",
        "name": "Anthropic News",
        "category": "模型、产品与研究",
        "sitemap_url": "https://www.anthropic.com/sitemap.xml",
        "include_path_prefix": "/news/",
        "allowed_hosts": ["www.anthropic.com"],
    }


class SitemapAdapterTests(unittest.TestCase):
    def test_sitemap_filters_path_and_untrusted_hosts(self):
        items = parse_sitemap(SITEMAP, source())
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].url, "https://www.anthropic.com/news/new-model")
        self.assertEqual(items[0].published_at, datetime(2026, 8, 18, 10, tzinfo=timezone.utc))
        self.assertEqual(items[0].summary, "")

    def test_article_metadata_enriches_new_candidate(self):
        item = ContentItem(
            item_id="stable", source_id="anthropic", source_name="Anthropic News",
            category="模型、产品与研究", title="new model",
            url="https://www.anthropic.com/news/new-model", summary="", published_at=None,
        )
        enriched = parse_article(ARTICLE, item)
        self.assertEqual(enriched.item_id, "stable")
        self.assertEqual(enriched.title, "Introducing Claude Test")
        self.assertEqual(enriched.summary, "Official model announcement & API details.")
        self.assertEqual(enriched.image_url, "https://www.anthropic.com/images/model.png")

    def test_path_date_can_be_used_when_sitemap_has_no_lastmod(self):
        configured = source() | {"date_path_regex": r"news(?P<date>\d{6})/?$", "date_path_format": "%y%m%d"}
        item = next(item for item in parse_sitemap(SITEMAP, configured) if item.url.endswith("news260813"))
        self.assertEqual(item.published_at, datetime(2026, 8, 13, tzinfo=timezone.utc))

    def test_sitemap_can_filter_paths_with_a_configured_regex(self):
        configured = source() | {"include_path_regex": r"^/news/(?:new-model|news\d+)/?$"}
        payload = SITEMAP.replace(
            b"</urlset>",
            b"<url><loc>https://www.anthropic.com/news/tag/models</loc>"
            b"<lastmod>2026-08-19T11:00:00Z</lastmod></url></urlset>",
        )

        items = parse_sitemap(payload, configured)

        self.assertEqual(
            [item.url for item in items],
            ["https://www.anthropic.com/news/new-model", "https://www.anthropic.com/news/news260813"],
        )

    def test_article_rejects_canonical_for_a_different_page(self):
        item = ContentItem(
            item_id="stale", source_id="deepseek", source_name="DeepSeek News",
            category="模型", title="stale", url="https://api-docs.deepseek.com/news/stale",
            summary="", published_at=None,
        )
        page = b'<html><head><link rel="canonical" href="https://api-docs.deepseek.com/"></head></html>'
        with self.assertRaisesRegex(ValueError, "canonical"):
            parse_article(page, item)


if __name__ == "__main__":
    unittest.main()
