import unittest
from datetime import datetime, timezone

from app.adapters.sources.changelog import parse_changelog


PAGE = b"""<html><body><article>
<h1>Change Log</h1>
<h2 id="date-2026-08-13">Date: 2026-08-13<a class="hash-link">zero</a></h2>
<h3 id="model-update">Model Update<a class="hash-link">zero</a></h3>
<p>A new model is available through the API.</p><ul><li>Agent support</li></ul>
<h3 id="pricing-update">Pricing Update</h3><p>New off-peak pricing.</p>
<h2 id="date-2026-07-31">Date: 2026-07-31</h2>
<h3 id="api-update">API Update</h3><p>Responses API support.</p>
</article></body></html>"""


def source():
    return {
        "id": "deepseek-changelog", "name": "DeepSeek API Change Log",
        "category": "模型与 API 更新", "page_url": "https://api-docs.deepseek.com/updates",
    }


class ChangelogAdapterTests(unittest.TestCase):
    def test_each_heading_becomes_an_independent_item(self):
        items = parse_changelog(PAGE, source())
        self.assertEqual([item.title for item in items], ["Model Update", "Pricing Update", "API Update"])
        self.assertEqual(items[0].published_at, datetime(2026, 8, 13, tzinfo=timezone.utc))
        self.assertEqual(items[0].url, "https://api-docs.deepseek.com/updates#model-update")
        self.assertIn("Agent support", items[0].summary)
        self.assertNotIn("zero", items[0].title)

    def test_content_change_produces_a_new_stable_id(self):
        original = parse_changelog(PAGE, source())[0]
        changed = parse_changelog(PAGE.replace(b"Agent support", b"Better agent support"), source())[0]
        repeated = parse_changelog(PAGE, source())[0]
        self.assertNotEqual(original.item_id, changed.item_id)
        self.assertEqual(original.item_id, repeated.item_id)


if __name__ == "__main__":
    unittest.main()
