import unittest

from backend.agents import handle_query
from backend.database import connect, init_db


class CampusAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_next_class_routes_to_schedule(self) -> None:
        result = handle_query("student-001", "Where is my next class?")
        self.assertEqual(result["intent"], "schedule")
        self.assertEqual(result["records"][0]["title"], "Introduction to Computer Science")
        self.assertTrue(result["reflected"])

    def test_fuzzy_book_search_finds_catalog_record(self) -> None:
        result = handle_query("student-001", "find intro to algorithms book")
        self.assertEqual(result["intent"], "library")
        self.assertEqual(result["records"][0]["title"], "Introduction to Algorithms")

    def test_catalog_context_routes_partial_title_to_library(self) -> None:
        result = handle_query("student-001", "intro to comp sci", "library")
        self.assertEqual(result["intent"], "library")
        self.assertEqual(result["records"][0]["title"], "Introduction to Computer Science")

    def test_navigation_resolves_alias(self) -> None:
        result = handle_query("student-001", "Where is the CS building?")
        self.assertEqual(result["intent"], "navigation")
        self.assertEqual(result["records"][0]["name"], "North Hall")

    def test_unclear_request_uses_error_path(self) -> None:
        result = handle_query("student-001", "Can you help me?")
        self.assertEqual(result["intent"], "unclear")
        self.assertIn("schedule", result["answer"])

    def test_reminder_request_is_persisted(self) -> None:
        result = handle_query("student-001", "Set a reminder 10 minutes before my next class")
        self.assertIn("Reminder set", result["answer"])
        with connect() as db:
            reminder = db.execute("SELECT * FROM reminders ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIsNotNone(reminder)
        self.assertEqual(reminder["student_id"], "student-001")


if __name__ == "__main__":
    unittest.main()