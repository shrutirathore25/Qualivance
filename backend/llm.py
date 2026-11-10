"""
llm.py - the only file that talks to Groq.

* GroqLLM   : real calls (server-side only; the key never leaves the backend).
* MockLLM   : fixed fictional answers, so everything can be tested without a key or credits.
* LLMError  : every failure becomes one of these, with a message that is safe to show in
              the UI. Messages never contain the API key, stack traces or the report text.
"""
import copy
import json
import logging
import os
import re
import time
from typing import Any, Callable, Optional

log = logging.getLogger("rca.llm")

# Groq retired llama-3.3-70b-versatile on 2026-08-16. Always confirm with check_groq.py.
DEFAULT_MODEL = "openai/gpt-oss-120b"


class LLMError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def extract_json(raw: Optional[str]) -> dict:
    """Pull one JSON object out of the model's reply (tolerates ``` fences and stray prose)."""
    if not raw or not raw.strip():
        raise ValueError("empty reply")
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.IGNORECASE)
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    obj = json.loads(s[start:end + 1])
    if not isinstance(obj, dict):
        raise ValueError("JSON is not an object")
    return obj


def map_error(e: Exception) -> LLMError:
    """Turn any provider/network exception into a safe, user-readable LLMError."""
    if isinstance(e, LLMError):
        return e
    try:
        import groq
    except Exception:  # pragma: no cover
        return LLMError("unknown", "The AI service failed unexpectedly. Please try again.")
    if isinstance(e, groq.APITimeoutError):
        return LLMError("timeout", "The AI service took too long to respond. Please try again.", 504)
    if isinstance(e, groq.APIConnectionError):
        return LLMError("connection", "Could not reach the AI service. Check your internet connection and try again.", 502)
    if isinstance(e, (groq.AuthenticationError, groq.PermissionDeniedError)):
        return LLMError("auth", "The AI service rejected the server's credentials. Check GROQ_API_KEY in backend/.env.", 502)
    if isinstance(e, groq.RateLimitError):
        return LLMError("rate_limit", "The AI service is busy (rate limit reached). Wait a moment and try again.", 429)
    if isinstance(e, groq.NotFoundError):
        return LLMError("model_unavailable", "The configured AI model is not available. Update GROQ_MODEL in backend/.env (run check_groq.py to see valid models).", 502)
    if isinstance(e, groq.BadRequestError):
        return LLMError("bad_request", "The AI service rejected the request. Check GROQ_MODEL in backend/.env (run check_groq.py).", 502)
    if isinstance(e, groq.APIStatusError):
        return LLMError("provider_error", "The AI service had a problem. Please try again shortly.", 502)
    return LLMError("unknown", "The AI service failed unexpectedly. Please try again.")


class GroqLLM:
    is_mock = False

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 client: Any = None, max_attempts: int = 2, timeout: float = 60.0):
        self.model = model or os.getenv("GROQ_MODEL") or DEFAULT_MODEL
        self.max_attempts = max(1, max_attempts)       # bounded retries for bad JSON
        self._json_mode = True                          # switched off if the model rejects it
        # gpt-oss models accept reasoning_effort; "low" is faster and uses fewer tokens per minute.
        effort = (os.getenv("GROQ_REASONING_EFFORT") or "").strip().lower()
        if not effort and self.model.startswith("openai/gpt-oss"):
            effort = "low"
        self._effort = effort if effort in {"low", "medium", "high"} else None
        self._sleep = time.sleep                        # replaced in tests
        self.max_rate_waits = 2                         # bounded waits on rate-limit errors
        if client is None:
            key = api_key or os.getenv("GROQ_API_KEY")
            if not key:
                raise LLMError("no_api_key", "GROQ_API_KEY is not set. Add it to backend/.env.", 500)
            from groq import Groq
            client = Groq(api_key=key, timeout=timeout, max_retries=1)
        self.client = client

    def _create(self, system: str, user: str, json_mode: bool) -> str:
        kwargs = dict(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
            max_completion_tokens=6000,   # reasoning models spend part of this thinking
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if self._effort:
            kwargs["reasoning_effort"] = self._effort
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def _call(self, system: str, user: str) -> str:
        import groq
        waits = 0
        while True:
            try:
                return self._create(system, user, self._json_mode)
            except groq.RateLimitError as e:
                # Wait (bounded) and try again; the limit is per minute, so a short pause usually clears it.
                if waits >= self.max_rate_waits:
                    raise
                waits += 1
                try:
                    delay = float(e.response.headers.get("retry-after", ""))
                except Exception:
                    delay = 8.0 * waits
                self._sleep(min(max(delay, 1.0), 20.0))
            except groq.BadRequestError:
                # Some models reject optional settings. Drop them one at a time; the prompt and
                # extract_json() still enforce JSON.
                if self._effort:
                    self._effort = None
                elif self._json_mode:
                    self._json_mode = False
                else:
                    raise

    def complete_json(self, task: str, system: str, user: str) -> dict:
        retry_note = "\n\nYour previous reply was not valid JSON. Reply with ONE JSON object only."
        for attempt in range(self.max_attempts):
            try:
                raw = self._call(system, user if attempt == 0 else user + retry_note)
            except Exception as e:
                err = map_error(e)
                log.warning("LLM call failed task=%s code=%s", task, err.code)   # never log the report text
                raise err
            try:
                return extract_json(raw)
            except ValueError:
                log.warning("LLM returned invalid JSON task=%s attempt=%d", task, attempt + 1)
        raise LLMError("invalid_json", "The AI returned an unreadable answer. Please try again.")


class MockLLM:
    """Deterministic stand-in. `responses` maps a task name to a dict, or to a function(user_text) -> dict."""
    is_mock = True

    def __init__(self, responses: Optional[dict] = None):
        from mock_fixtures import MOCK_LLM_RESPONSES
        self.responses = dict(MOCK_LLM_RESPONSES)
        if responses:
            self.responses.update(responses)
        self.calls: list[str] = []

    def complete_json(self, task: str, system: str, user: str) -> dict:
        self.calls.append(task)
        r = self.responses[task]
        out = r(user) if callable(r) else copy.deepcopy(r)
        if isinstance(out, Exception):
            raise out
        return out


def get_llm():
    """AI_MODE=mock in backend/.env gives the fixed demo answers; otherwise real Groq."""
    if (os.getenv("AI_MODE") or "").strip().lower() == "mock":
        return MockLLM()
    return GroqLLM()
