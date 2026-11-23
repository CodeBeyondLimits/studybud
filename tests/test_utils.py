import sys
import unittest
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.export import build_revision_markdown
from utils.gemini import GeminiServiceError, _validate_pack
from utils.pdf_processor import PDFExtractionError, extract_pdf_text


VALID_PACK = {
    "summary": ["Point one", "Point two", "Point three", "Point four", "Point five"],
    "quiz": [
        {
            "question": f"Question {number}",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "A",
            "explanation": "A is correct.",
        }
        for number in range(1, 6)
    ],
    "key_terms": [
        {"term": f"Term {number}", "meaning": "Meaning", "explanation": "Explanation"}
        for number in range(1, 4)
    ],
}


class RevisionPackTests(unittest.TestCase):
    def test_valid_pack(self):
        self.assertEqual(_validate_pack(VALID_PACK)["summary"], VALID_PACK["summary"])

    def test_rejects_wrong_summary_count(self):
        invalid = dict(VALID_PACK)
        invalid["summary"] = ["Only one"]
        with self.assertRaises(GeminiServiceError):
            _validate_pack(invalid)

    def test_rejects_answer_outside_options(self):
        invalid = dict(VALID_PACK)
        invalid["quiz"] = [dict(question) for question in VALID_PACK["quiz"]]
        invalid["quiz"][0]["correct_answer"] = "Z"
        with self.assertRaises(GeminiServiceError):
            _validate_pack(invalid)

    def test_markdown_export(self):
        markdown = build_revision_markdown("chapter.pdf", VALID_PACK)
        self.assertIn("# STUDYBUD Revision Pack", markdown)
        self.assertIn("chapter.pdf", markdown)
        self.assertIn("Question 5", markdown)

    def test_invalid_pdf_is_handled(self):
        with self.assertRaises(PDFExtractionError):
            extract_pdf_text(io.BytesIO(b"not a pdf"))


if __name__ == "__main__":
    unittest.main()
