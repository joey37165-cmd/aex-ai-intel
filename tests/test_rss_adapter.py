import unittest

from app.adapters.sources.parser import parse_feed


SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><item>
<title>New model</title><link>https://example.com/model</link><guid>m1</guid>
<enclosure url="https://cdn.example.com/model.jpg" type="image/jpeg" />
<pubDate>Tue, 18 Aug 2026 08:00:00 GMT</pubDate>
<description><![CDATA[<p>Useful <b>release</b>.</p>]]></description>
</item></channel></rss>"""

KEYWORD_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item><title>AI Agent release</title><link>https://example.com/ai</link><guid>ai</guid>
<description>Build workflows with an agent.</description></item>
<item><title>Air quality update</title><link>https://example.com/air</link><guid>air</guid>
<description>General product news.</description></item>
</channel></rss>"""


class FormalRSSParserTests(unittest.TestCase):
    def test_formal_adapter_parser_matches_feed_contract(self):
        items = parse_feed(SAMPLE, {"name": "Formal RSS", "category": "模型"})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "New model")
        self.assertEqual(items[0].url, "https://example.com/model")
        self.assertEqual(items[0].category, "模型")
        self.assertEqual(items[0].image_url, "https://cdn.example.com/model.jpg")

    def test_include_keywords_filters_without_matching_substrings(self):
        items = parse_feed(
            KEYWORD_SAMPLE,
            {"name": "Product discovery", "category": "AI 应用", "include_keywords": ["ai", "agent"]},
        )

        self.assertEqual([item.title for item in items], ["AI Agent release"])


if __name__ == "__main__":
    unittest.main()
