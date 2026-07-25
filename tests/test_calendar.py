import unittest
from modules.calendar_service import normalize_title, is_ai_processed, format_frontmatter

class TestCalendarService(unittest.TestCase):

    def test_normalize_title(self):
        self.assertEqual(normalize_title("Natasha's Birthday!"), "natashasbirthday")
        self.assertEqual(normalize_title("Book Colosseum Tickets"), "bookcolosseumtickets")
        self.assertEqual(normalize_title("  BOOK COLOSSEUM TICKETS  "), "bookcolosseumtickets")
        self.assertEqual(normalize_title(""), "")

    def test_is_ai_processed(self):
        processed_event = {
            "description": "---\nai_processed: true\nai_source: email\nai_model: gemini-3.6-flash\nai_updated: 2026-07-25\n---\n\nDetails here"
        }
        unprocessed_event = {
            "description": "Just a normal description"
        }
        legacy_event = {
            "description": "---\nai_processed: true\nai_source: email\n---\n\nMissing model tag"
        }
        empty_event = {}

        self.assertTrue(is_ai_processed(processed_event))
        self.assertFalse(is_ai_processed(unprocessed_event))
        self.assertFalse(is_ai_processed(legacy_event))
        self.assertFalse(is_ai_processed(empty_event))

    def test_format_frontmatter(self):
        fm = format_frontmatter(source="test_source", model="gemini-3.6-flash", date_str="2026-07-25")
        self.assertIn("ai_processed: true", fm)
        self.assertIn("ai_source: test_source", fm)
        self.assertIn("ai_model: gemini-3.6-flash", fm)
        self.assertIn("ai_updated: 2026-07-25", fm)

if __name__ == "__main__":
    unittest.main()
