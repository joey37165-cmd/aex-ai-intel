import unittest
from datetime import datetime, timezone

from app.adapters.sources.gemini_changelog import parse_gemini_changelog


PAGE = b"""<html><body>
<h1>Release notes</h1>
<h2 id="08-13-2026">August 13, 2026</h2>
<ul><li><p><strong>Gemini 3.7 Flash generally available (GA)</strong>: Released our latest model.</p>
<ul><li><strong>Gemini 3.7 Flash</strong>: Better coding and agents.</li></ul></li></ul>
<h2 id="07-30-2026">July 30, 2026</h2>
<ul><li><p><strong>Robotics update</strong>: Added new endpoints.</p></li></ul>
</body></html>"""


def source():
    return {
        "id": "gemini-changelog",
        "name": "Gemini API Changelog",
        "category": "模型与 API 更新",
        "page_url": "https://ai.google.dev/gemini-api/docs/changelog",
    }


class GeminiChangelogAdapterTests(unittest.TestCase):
    def test_each_top_level_update_becomes_an_item(self):
        items = parse_gemini_changelog(PAGE, source())

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "Gemini 3.7 Flash generally available (GA)")
        self.assertEqual(items[0].published_at, datetime(2026, 8, 13, tzinfo=timezone.utc))
        self.assertIn("Better coding and agents", items[0].summary)
        self.assertEqual(items[0].url, "https://ai.google.dev/gemini-api/docs/changelog#08-13-2026")

    def test_content_change_produces_a_new_stable_id(self):
        original = parse_gemini_changelog(PAGE, source())[0]
        changed = parse_gemini_changelog(PAGE.replace(b"Better coding", b"Much better coding"), source())[0]
        repeated = parse_gemini_changelog(PAGE, source())[0]

        self.assertNotEqual(original.item_id, changed.item_id)
        self.assertEqual(original.item_id, repeated.item_id)


if __name__ == "__main__":
    unittest.main()
