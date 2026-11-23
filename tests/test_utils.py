import io
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.genai import errors
from pypdf import PdfReader

from utils.export import (
    build_revision_markdown,
    build_revision_pdf,
    build_revision_text,
)
from utils.gemini import (
    DEFAULT_GEMINI_FALLBACK_MODEL,
    DEFAULT_GEMINI_MODEL,
    GeminiConfigurationError,
    GeminiServiceError,
    _MODEL_CACHE,
    _validate_pack,
    generate_revision_pack,
    get_model_configuration,
    resolve_api_key,
)
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


def _api_model(name):
    return SimpleNamespace(name=f"models/{name}", supported_actions=["generateContent"])


def _response(pack=VALID_PACK):
    return SimpleNamespace(text=json.dumps(pack))


def _api_error(status, details=None):
    payload = {
        "error": {
            "code": status,
            "message": "simulated API error",
            "status": "UNAVAILABLE" if status == 503 else "RESOURCE_EXHAUSTED",
        }
    }
    if details:
        payload["error"].update(details)
    return errors.APIError(status, payload)


class RevisionPackTests(unittest.TestCase):
    def setUp(self):
        _MODEL_CACHE.clear()

    def test_api_key_secret_precedes_environment_fallback(self):
        self.assertEqual(
            resolve_api_key(
                {"GEMINI_API_KEY": " secret-key "},
                {"GEMINI_API_KEY": "environment-key"},
            ),
            "secret-key",
        )
        self.assertEqual(
            resolve_api_key(
                {"GEMINI_API_KEY": "PASTE_A_KEY"},
                {"GEMINI_API_KEY": "environment-key"},
            ),
            "environment-key",
        )

    def test_model_configuration_defaults_and_environment_override(self):
        self.assertEqual(
            get_model_configuration({}),
            (DEFAULT_GEMINI_MODEL, DEFAULT_GEMINI_FALLBACK_MODEL),
        )
        self.assertEqual(
            get_model_configuration(
                {"GEMINI_MODEL": "custom-primary", "GEMINI_FALLBACK_MODEL": ""}
            ),
            ("custom-primary", None),
        )

    def test_valid_pack_and_exact_output_counts(self):
        pack = _validate_pack(VALID_PACK)
        self.assertEqual(len(pack["summary"]), 5)
        self.assertEqual(len(pack["quiz"]), 5)
        self.assertTrue(all(len(item["options"]) == 4 for item in pack["quiz"]))
        self.assertEqual(len(pack["key_terms"]), 3)

    def test_rejects_wrong_summary_count_and_duplicate_options(self):
        invalid = dict(VALID_PACK)
        invalid["summary"] = ["Only one"]
        with self.assertRaises(GeminiServiceError):
            _validate_pack(invalid)

        invalid = dict(VALID_PACK)
        invalid["quiz"] = [dict(question) for question in VALID_PACK["quiz"]]
        invalid["quiz"][0]["options"] = ["A", "A", "C", "D"]
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

    def test_text_export_contains_complete_pack(self):
        text = build_revision_text("chapter.pdf", VALID_PACK)
        self.assertIn("Source: chapter.pdf", text)
        self.assertIn("Question 5", text)
        self.assertIn("Correct answer: A", text)
        self.assertIn("Term 3", text)

    def test_pdf_export_is_readable_and_contains_complete_pack(self):
        pdf = build_revision_pdf("chapter.pdf", VALID_PACK)
        pages = PdfReader(io.BytesIO(pdf)).pages
        extracted_text = "\n".join(page.extract_text() or "" for page in pages)
        self.assertIn("chapter.pdf", extracted_text)
        self.assertIn("Question 5", extracted_text)
        self.assertIn("Term 3", extracted_text)

    def test_invalid_pdf_is_handled(self):
        with self.assertRaises(PDFExtractionError):
            extract_pdf_text(io.BytesIO(b"not a pdf"))

    @patch.dict(os.environ, {"GEMINI_MODEL": "gemini-3.8-flash", "GEMINI_FALLBACK_MODEL": ""})
    @patch("utils.gemini.time.sleep")
    @patch("utils.gemini.random.uniform", return_value=0.25)
    @patch("utils.gemini.genai.Client")
    def test_retries_503_three_times_then_succeeds(
        self, client_class, _jitter, sleep
    ):
        client = client_class.return_value
        client.models.list.return_value = [_api_model("gemini-3.8-flash")]
        client.models.generate_content.side_effect = [
            _api_error(503),
            _api_error(503),
            _api_error(503),
            _response(),
        ]

        result = generate_revision_pack("source notes", "test-key")

        self.assertEqual(result, VALID_PACK)
        self.assertEqual(client.models.generate_content.call_count, 4)
        self.assertEqual(sleep.call_count, 3)

    @patch.dict(
        os.environ,
        {"GEMINI_MODEL": "primary", "GEMINI_FALLBACK_MODEL": "secondary"},
    )
    @patch("utils.gemini.time.sleep")
    @patch("utils.gemini.genai.Client")
    def test_503_retries_primary_then_uses_verified_fallback(
        self, client_class, sleep
    ):
        client = client_class.return_value
        client.models.list.return_value = [
            _api_model("primary"),
            _api_model("secondary"),
        ]
        client.models.generate_content.side_effect = [
            _api_error(503),
            _api_error(503),
            _api_error(503),
            _api_error(503),
            _response(),
        ]

        result = generate_revision_pack("source notes", "test-key")

        self.assertEqual(result, VALID_PACK)
        self.assertEqual(client.models.generate_content.call_count, 5)
        self.assertEqual(
            [call.kwargs["model"] for call in client.models.generate_content.call_args_list],
            ["primary"] * 4 + ["secondary"],
        )
        self.assertEqual(sleep.call_count, 3)

    @patch.dict(os.environ, {"GEMINI_MODEL": "primary", "GEMINI_FALLBACK_MODEL": "secondary"})
    @patch("utils.gemini.time.sleep")
    @patch("utils.gemini.genai.Client")
    def test_all_503_attempts_end_with_retryable_overload_message(
        self, client_class, sleep
    ):
        client = client_class.return_value
        client.models.list.return_value = [
            _api_model("primary"),
            _api_model("secondary"),
        ]
        client.models.generate_content.side_effect = [_api_error(503) for _ in range(8)]

        with self.assertRaisesRegex(GeminiServiceError, "temporarily overloaded"):
            generate_revision_pack("source notes", "test-key")

        self.assertEqual(client.models.generate_content.call_count, 8)
        self.assertEqual(sleep.call_count, 6)

    @patch.dict(os.environ, {"GEMINI_MODEL": "missing", "GEMINI_FALLBACK_MODEL": ""})
    @patch("utils.gemini.genai.Client")
    def test_rejects_primary_model_not_available_to_key(self, client_class):
        client = client_class.return_value
        client.models.list.return_value = [_api_model("available")]

        with self.assertRaisesRegex(GeminiConfigurationError, "not available"):
            generate_revision_pack("source notes", "test-key")
        client.models.generate_content.assert_not_called()

    @patch.dict(os.environ, {"GEMINI_MODEL": "primary", "GEMINI_FALLBACK_MODEL": ""})
    @patch("utils.gemini.genai.Client")
    def test_429_surfaces_retry_after_without_repeating_request(self, client_class):
        client = client_class.return_value
        client.models.list.return_value = [_api_model("primary")]
        client.models.generate_content.side_effect = _api_error(
            429,
            {"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "8s"}]},
        )

        with self.assertRaises(GeminiServiceError) as raised:
            generate_revision_pack("source notes", "test-key")

        self.assertIn("quota", str(raised.exception).lower())
        self.assertEqual(raised.exception.retry_after, 8)
        self.assertEqual(client.models.generate_content.call_count, 1)

    @patch.dict(os.environ, {"GEMINI_MODEL": "primary", "GEMINI_FALLBACK_MODEL": ""})
    @patch("utils.gemini.genai.Client")
    def test_400_is_friendly_and_does_not_retry(self, client_class):
        client = client_class.return_value
        client.models.list.return_value = [_api_model("primary")]
        client.models.generate_content.side_effect = _api_error(400)

        with self.assertRaisesRegex(GeminiServiceError, "rejected the request"):
            generate_revision_pack("source notes", "test-key")
        self.assertEqual(client.models.generate_content.call_count, 1)

    @patch.dict(os.environ, {"GEMINI_MODEL": "primary", "GEMINI_FALLBACK_MODEL": ""})
    @patch("utils.gemini.genai.Client")
    def test_401_and_403_explain_key_or_permission_problem(self, client_class):
        for status in (401, 403):
            with self.subTest(status=status):
                client = client_class.return_value
                client.models.list.return_value = [_api_model("primary")]
                client.models.generate_content.side_effect = _api_error(status)

                with self.assertRaisesRegex(GeminiServiceError, "API key"):
                    generate_revision_pack("source notes", "test-key")


if __name__ == "__main__":
    unittest.main()
