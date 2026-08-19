import unittest
from datetime import datetime, timezone

from app.adapters.sources.openai_changelog import parse_openai_changelog


PAGE = b"""<html><body>
<h1>Changelog</h1>
<h3>August, 2026</h3>
<div class="grid grid-cols-[3rem_1fr] items-start">
  <div><div class="Badge" data-variant="outline">Aug 13</div></div>
  <div>
    <div><div class="Badge" data-variant="soft"><span>Announcement</span></div></div>
    <div class="ChangelogMarkdown"><p>Announced Ultrafast mode for frontier models.</p></div>
  </div>
</div>
<div class="grid grid-cols-[3rem_1fr] items-start">
  <div><div class="Badge" data-variant="outline">Aug 7</div></div>
  <div>
    <div><div class="Badge" data-variant="soft">Feature</div><div class="Badge" data-variant="soft">gpt-test</div></div>
    <div class="ChangelogMarkdown"><p>Released a new test model.</p><p>It supports tools.</p></div>
  </div>
</div>
<h3>July, 2026</h3>
<div class="grid grid-cols-[3rem_1fr] items-start">
  <div><div class="Badge" data-variant="outline">Jul 30</div></div>
  <div><div class="ChangelogMarkdown"><p>Reduced API pricing.</p></div></div>
</div>
</body></html>"""


def source():
    return {
        "id": "openai-changelog", "name": "OpenAI Developer Changelog",
        "category": "模型与 API 更新", "page_url": "https://developers.openai.com/api/docs/changelog",
    }


class OpenAIChangelogAdapterTests(unittest.TestCase):
    def test_cards_become_independent_dated_items(self):
        items = parse_openai_changelog(PAGE, source())
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].published_at, datetime(2026, 8, 13, tzinfo=timezone.utc))
        self.assertEqual(items[0].title, "Announced Ultrafast mode for frontier models.")
        self.assertIn("[Announcement]", items[0].summary)
        self.assertIn("[Feature, gpt-test]", items[1].summary)
        self.assertEqual(items[2].published_at, datetime(2026, 7, 30, tzinfo=timezone.utc))

    def test_content_change_produces_a_new_id(self):
        original = parse_openai_changelog(PAGE, source())[0]
        changed = parse_openai_changelog(PAGE.replace(b"frontier models", b"selected models"), source())[0]
        repeated = parse_openai_changelog(PAGE, source())[0]
        self.assertNotEqual(original.item_id, changed.item_id)
        self.assertEqual(original.item_id, repeated.item_id)


if __name__ == "__main__":
    unittest.main()
