import json
import re
from typing import Dict

from google import genai
from google.genai import types


class GeminiConfigurationError(Exception):
    pass


class GeminiServiceError(Exception):
    pass


SYSTEM_INSTRUCTION = (
    "You are a concise academic study assistant. Use simple, exam-focused language. "
    "Do not add anything outside the requested JSON object."
)


def _truncate_text(text: str, max_chars: int = 35000) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[Document truncated for processing]"


def _extract_json(text: str) -> Dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise GeminiServiceError(
            "The AI returned an unreadable response. Please try again."
        ) from exc


def _validate_pack(pack: Dict) -> Dict:
    if not isinstance(pack, dict):
        raise GeminiServiceError("The AI returned an invalid revision pack.")

    summary = pack.get("summary")
    quiz = pack.get("quiz")
    key_terms = pack.get("key_terms")

    if not isinstance(summary, list) or not 5 <= len(summary) <= 6:
        raise GeminiServiceError("The summary must contain exactly five or six bullet points.")
    if not all(isinstance(point, str) and point.strip() for point in summary):
        raise GeminiServiceError("The summary contains an invalid bullet point.")

    if not isinstance(quiz, list) or len(quiz) != 5:
        raise GeminiServiceError("The quiz must contain exactly five questions.")
    for question in quiz:
        if not isinstance(question, dict):
            raise GeminiServiceError("The quiz contains an invalid question.")
        options = question.get("options")
        if not isinstance(question.get("question"), str):
            raise GeminiServiceError("The quiz contains an invalid question.")
        if not isinstance(options, list) or len(options) != 4:
            raise GeminiServiceError("Each quiz question must contain four options.")
        if not all(isinstance(option, str) and option.strip() for option in options):
            raise GeminiServiceError("A quiz option is invalid.")
        if question.get("correct_answer") not in options:
            raise GeminiServiceError("A quiz answer is not among its options.")
        if not isinstance(question.get("explanation"), str):
            raise GeminiServiceError("A quiz explanation is missing.")

    if not isinstance(key_terms, list) or len(key_terms) != 3:
        raise GeminiServiceError("The response must contain exactly three key terms.")
    for term in key_terms:
        if not isinstance(term, dict):
            raise GeminiServiceError("The key terms contain an invalid entry.")
        if not all(isinstance(term.get(field), str) and term[field].strip()
                   for field in ("term", "meaning", "explanation")):
            raise GeminiServiceError("A key term is incomplete.")

    return {
        "summary": summary,
        "quiz": quiz,
        "key_terms": key_terms,
    }


def generate_revision_pack(text: str, api_key: str) -> Dict:
    if not api_key:
        raise GeminiConfigurationError("GEMINI_API_KEY is not configured.")
    if not text or not text.strip():
        raise GeminiConfigurationError("No source text was provided.")

    prompt = f"""
Create a revision pack from the study material below.

Return one valid JSON object with this exact shape:
{{
  "summary": ["bullet 1", "bullet 2", "bullet 3", "bullet 4", "bullet 5"],
  "quiz": [
    {{
      "question": "question text",
      "options": ["option A", "option B", "option C", "option D"],
      "correct_answer": "one exact option",
      "explanation": "brief reason"
    }}
  ],
  "key_terms": [
    {{
      "term": "term",
      "meaning": "simple meaning",
      "explanation": "brief explanation"
    }}
  ]
}}

Requirements:
- summary: exactly 5 or 6 concise, exam-focused bullet points
- quiz: exactly 5 multiple-choice questions, with exactly 4 unique options each
- key_terms: exactly 3 important terms
- correct_answer must exactly match one options value
- No markdown fences or text outside the JSON object

STUDY MATERIAL:
{_truncate_text(text)}
"""

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
    except Exception as exc:
        message = str(exc).lower()
        if "429" in message or "quota" in message or "resource_exhausted" in message:
            raise GeminiServiceError(
                "Gemini quota has been reached. Check the API quota and try again later."
            ) from exc
        if "503" in message or "unavailable" in message or "high demand" in message:
            raise GeminiServiceError(
                "Gemini is temporarily unavailable due to high demand. Please try again shortly."
            ) from exc
        if "401" in message or "403" in message or "api key" in message:
            raise GeminiServiceError(
                "Gemini authentication failed. Please verify the centrally configured API key."
            ) from exc
        raise GeminiServiceError(
            "Gemini could not generate this revision pack. Please try again."
        ) from exc

    if not getattr(response, "text", None):
        raise GeminiServiceError("Gemini returned no generated content.")
    return _validate_pack(_extract_json(response.text))
