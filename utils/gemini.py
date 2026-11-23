import hashlib
import json
import os
import random
import re
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, Mapping, Optional, Tuple

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

from utils.prompts import build_revision_prompt


DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_GEMINI_FALLBACK_MODEL = "gemini-3.6-flash"
MAX_503_RETRIES = 3
REQUEST_TIMEOUT_MS = 60_000
MODEL_CACHE_TTL_SECONDS = 600


class GeminiConfigurationError(Exception):
    pass


class GeminiServiceError(Exception):
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class _QuizQuestion(BaseModel):
    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    correct_answer: str
    explanation: str


class _KeyTerm(BaseModel):
    term: str
    meaning: str
    explanation: str


class _RevisionPack(BaseModel):
    summary: list[str] = Field(min_length=5, max_length=6)
    quiz: list[_QuizQuestion] = Field(min_length=5, max_length=5)
    key_terms: list[_KeyTerm] = Field(min_length=3, max_length=3)


_REQUEST_LOCK = threading.Lock()
_MODEL_CACHE: Dict[str, Tuple[float, set[str]]] = {}


def resolve_api_key(
    secrets: Mapping[str, str], environ: Mapping[str, str]
) -> str:
    secret_key = secrets.get("GEMINI_API_KEY", "").strip()
    if secret_key and "PASTE" not in secret_key.upper():
        return secret_key

    environment_key = environ.get("GEMINI_API_KEY", "").strip()
    if environment_key and "PASTE" not in environment_key.upper():
        return environment_key
    return ""


def get_model_configuration(environ: Mapping[str, str]) -> Tuple[str, Optional[str]]:
    primary = environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
    fallback = environ.get(
        "GEMINI_FALLBACK_MODEL", DEFAULT_GEMINI_FALLBACK_MODEL
    ).strip()
    if not primary:
        raise GeminiConfigurationError(
            "GEMINI_MODEL is empty. Set it to a supported Gemini Flash model."
        )
    return primary, fallback or None


def _truncate_text(text: str, max_chars: int = 35_000) -> str:
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
            "The AI returned an unreadable revision pack. Please try again."
        ) from exc


def _validate_pack(pack: Dict) -> Dict:
    if not isinstance(pack, dict):
        raise GeminiServiceError("The AI returned an invalid revision pack.")

    summary = pack.get("summary")
    quiz = pack.get("quiz")
    key_terms = pack.get("key_terms")

    if not isinstance(summary, list) or not 5 <= len(summary) <= 6:
        raise GeminiServiceError("The AI response did not contain five or six summary points.")
    if not all(isinstance(point, str) and point.strip() for point in summary):
        raise GeminiServiceError("The AI response contained an invalid summary point.")

    if not isinstance(quiz, list) or len(quiz) != 5:
        raise GeminiServiceError("The AI response did not contain five quiz questions.")
    for question in quiz:
        if not isinstance(question, dict):
            raise GeminiServiceError("The AI response contained an invalid quiz question.")
        options = question.get("options")
        if not isinstance(question.get("question"), str) or not question["question"].strip():
            raise GeminiServiceError("The AI response contained an invalid quiz question.")
        if (
            not isinstance(options, list)
            or len(options) != 4
            or len(set(options)) != 4
        ):
            raise GeminiServiceError("Each quiz question must have four unique options.")
        if not all(isinstance(option, str) and option.strip() for option in options):
            raise GeminiServiceError("The AI response contained an invalid quiz option.")
        if question.get("correct_answer") not in options:
            raise GeminiServiceError("A quiz answer did not match one of its options.")
        if not isinstance(question.get("explanation"), str) or not question["explanation"].strip():
            raise GeminiServiceError("The AI response omitted a quiz explanation.")

    if not isinstance(key_terms, list) or len(key_terms) != 3:
        raise GeminiServiceError("The AI response did not contain exactly three key terms.")
    for term in key_terms:
        if not isinstance(term, dict) or not all(
            isinstance(term.get(field), str) and term[field].strip()
            for field in ("term", "meaning", "explanation")
        ):
            raise GeminiServiceError("The AI response contained an incomplete key term.")

    return {"summary": summary, "quiz": quiz, "key_terms": key_terms}


def _http_status(exc: BaseException) -> Optional[int]:
    if isinstance(exc, errors.APIError):
        return exc.code
    return None


def _duration_seconds(value: object) -> Optional[float]:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)s\s*", value)
    return float(match.group(1)) if match else None


def _retry_after_seconds(exc: errors.APIError) -> Optional[int]:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if retry_after:
        try:
            return max(1, int(float(retry_after)))
        except ValueError:
            try:
                retry_time = parsedate_to_datetime(retry_after)
                if retry_time.tzinfo is None:
                    retry_time = retry_time.replace(tzinfo=timezone.utc)
                return max(1, int((retry_time - datetime.now(timezone.utc)).total_seconds()))
            except (TypeError, ValueError, OverflowError):
                pass

    details = getattr(exc, "details", {})
    if isinstance(details, dict):
        error_details = details.get("error", {}).get("details", [])
        if isinstance(error_details, list):
            for detail in error_details:
                if not isinstance(detail, dict):
                    continue
                retry_delay = detail.get("retryDelay") or detail.get("retry_delay")
                seconds = _duration_seconds(retry_delay)
                if seconds is not None:
                    return max(1, int(seconds + 0.999))
    return None


def _friendly_api_error(exc: errors.APIError) -> GeminiServiceError:
    status = _http_status(exc)
    if status == 400:
        return GeminiServiceError(
            "Gemini rejected the request. Check the configured model and try again."
        )
    if status in (401, 403):
        return GeminiServiceError(
            "Gemini access was denied. Check the centrally configured API key and its permissions."
        )
    if status == 404:
        return GeminiServiceError(
            "The configured Gemini model is unavailable. Check GEMINI_MODEL in your settings."
        )
    if status == 429:
        retry_after = _retry_after_seconds(exc)
        message = (
            "Gemini's request or usage quota has been reached. "
            "Please wait before trying again."
        )
        return GeminiServiceError(message, retry_after=retry_after)
    if status == 503:
        return GeminiServiceError(
            "Gemini is temporarily overloaded. Please try again shortly."
        )
    return GeminiServiceError(
        "Gemini could not create the revision pack. Please try again shortly."
    )


def _client(api_key: str) -> genai.Client:
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=REQUEST_TIMEOUT_MS,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def _list_supported_models(client: genai.Client, api_key: str) -> set[str]:
    fingerprint = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    cached = _MODEL_CACHE.get(fingerprint)
    now = time.monotonic()
    if cached and cached[0] > now:
        return cached[1]

    try:
        models = client.models.list()
        supported = {
            model.name.removeprefix("models/")
            for model in models
            if getattr(model, "name", None)
            and "generateContent" in (getattr(model, "supported_actions", None) or [])
        }
    except errors.APIError as exc:
        raise _friendly_api_error(exc) from exc
    except Exception as exc:
        raise GeminiServiceError(
            "Gemini model availability could not be checked. Please try again."
        ) from exc

    _MODEL_CACHE[fingerprint] = (now + MODEL_CACHE_TTL_SECONDS, supported)
    return supported


def _request_with_retries(
    client: genai.Client, model: str, prompt: str
):
    for retry_number in range(MAX_503_RETRIES + 1):
        try:
            return client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_RevisionPack,
                ),
            )
        except errors.APIError as exc:
            if _http_status(exc) != 503 or retry_number == MAX_503_RETRIES:
                raise
            delay = min(8.0, 2**retry_number) + random.uniform(0.0, 0.5)
            time.sleep(delay)


def generate_revision_pack(text: str, api_key: str) -> Dict:
    if not api_key:
        raise GeminiConfigurationError("Gemini is not configured. Please contact the app administrator.")
    if not text or not text.strip():
        raise GeminiConfigurationError("Add notes or upload a readable PDF before generating a pack.")

    primary_model, fallback_model = get_model_configuration(os.environ)
    prompt = build_revision_prompt(_truncate_text(text))

    with _REQUEST_LOCK:
        client = _client(api_key)
        available_models = _list_supported_models(client, api_key)
        if primary_model not in available_models:
            raise GeminiConfigurationError(
                "The configured primary Gemini model is not available for this API key. "
                "Set GEMINI_MODEL to a supported text-generation model."
            )

        try:
            response = _request_with_retries(client, primary_model, prompt)
        except errors.APIError as exc:
            if _http_status(exc) != 503:
                raise _friendly_api_error(exc) from exc
            if (
                not fallback_model
                or fallback_model == primary_model
                or fallback_model not in available_models
            ):
                raise _friendly_api_error(exc) from exc

            try:
                response = _request_with_retries(client, fallback_model, prompt)
            except errors.APIError as fallback_exc:
                raise _friendly_api_error(fallback_exc) from fallback_exc
        except Exception as exc:
            raise GeminiServiceError(
                "Gemini could not create the revision pack. Please try again shortly."
            ) from exc

    if not getattr(response, "text", None):
        raise GeminiServiceError("Gemini returned no revision pack. Please try again.")
    return _validate_pack(_extract_json(response.text))
