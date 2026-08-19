import tempfile
import unittest
from datetime import timezone
from pathlib import Path

from telegram_poc import FeedItem, format_message, load_state, parse_feed, save_state


RSS_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>New &amp; useful model</title>
      <link>https://example.com/model</link>
      <guid>model-1</guid>
      <pubDate>Tue, 18 Aug 2026 08:00:00 GMT</pubDate>
      <description><![CDATA[<p>A practical <b>release</b>.</p>]]></description>
    </item>
  </channel>
</rss>
"""


ATOM_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Agent update</title>
    <id>agent-1</id>
    <link rel="alternate" href="https://example.com/agent" />
    <updated>2026-08-18T09:00:00Z</updated>
    <summary type="html">A better workflow.</summary>
  </entry>
</feed>
"""


class FeedParsingTests(unittest.TestCase):
    def test_parses_rss(self):
        items = parse_feed(RSS_SAMPLE, {"name": "Test RSS", "category": "模型"})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "New & useful model")
        self.assertEqual(items[0].summary, "A practical release .")
        self.assertEqual(items[0].published_at.tzinfo, timezone.utc)

    def test_parses_atom(self):
        items = parse_feed(ATOM_SAMPLE, {"name": "Test Atom", "category": "Agent"})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://example.com/agent")
        self.assertEqual(items[0].summary, "A better workflow.")

    def test_message_escapes_html(self):
        item = FeedItem(
            item_id="1",
            source="A&B",
            category="测试",
            title="<Model>",
            url="https://example.com/?a=1&b=2",
            summary="Use <carefully>",
            published_at=None,
        )
        message = format_message(item)
        self.assertIn("&lt;Model&gt;", message)
        self.assertIn("A&amp;B", message)
        self.assertIn("a=1&amp;b=2", message)


class StateTests(unittest.TestCase):
    def test_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            save_state(path, {"a", "b"})
            self.assertEqual(load_state(path), {"a", "b"})


if __name__ == "__main__":
    unittest.main()

