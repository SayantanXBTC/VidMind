"""LLM clients used for summaries, chapters and Ask the Video.

Two providers share one interface (is_available / chat_json):
  - ClaudeService: the Anthropic API. Used for public deployments: fast,
    handles many users at once, no GPU needed.
  - OllamaService: a local model served by Ollama. Keeps everything on this
    machine; good for personal use.

LLM_PROVIDER picks one ("anthropic", "ollama", "none", or "auto" = Claude
when an Anthropic key is configured, else Ollama). When the chosen provider
is unavailable, callers fall back to the small Hugging Face models, so the
app still works — just with lower-quality output.
"""
import json
import logging
import threading
import time
from typing import Callable, Optional

import anthropic
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_AVAILABILITY_TTL_SECONDS = 30.0


class LLMError(Exception):
    """Raised when the LLM is unreachable or returns unusable output."""


class OllamaService:
    name = "ollama"

    @property
    def single_pass_max_words(self) -> int:
        return settings.LLM_SINGLE_PASS_MAX_WORDS

    def __init__(self) -> None:
        self._available: Optional[bool] = None
        self._checked_at = 0.0
        self._lock = threading.Lock()
        # Some models reject the `think` flag; remember that after the first refusal.
        self._send_think_flag = True

    @property
    def model(self) -> str:
        return settings.OLLAMA_MODEL

    def is_available(self) -> bool:
        with self._lock:
            if self._available is not None and time.monotonic() - self._checked_at < _AVAILABILITY_TTL_SECONDS:
                return self._available
            self._available = self._probe()
            self._checked_at = time.monotonic()
            return self._available

    def _probe(self) -> bool:
        try:
            resp = httpx.get(f"{settings.OLLAMA_URL}/api/tags", timeout=3.0)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama not reachable at %s (%s); using fallback models", settings.OLLAMA_URL, exc)
            return False
        names = {m.get("name") for m in resp.json().get("models", [])}
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        if wanted not in names:
            logger.warning(
                "Ollama model %s not found (have: %s). Run `ollama pull %s`; using fallback models",
                self.model,
                ", ".join(sorted(n for n in names if n)) or "none",
                self.model,
            )
            return False
        return True

    def chat_json(
        self,
        system: str,
        user: str,
        schema: dict,
        *,
        max_tokens: int = 2048,
        expected_tokens: Optional[int] = None,
        on_progress: Optional[Callable[[float], None]] = None,
    ) -> dict:
        """Run one chat completion constrained to `schema` and return the parsed JSON.

        Streams the response so on_progress(fraction) can report generation
        progress (fraction in [0, 1), estimated against expected_tokens).
        """
        payload = {
            "model": self.model,
            "stream": True,
            "format": schema,
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {
                "temperature": settings.LLM_TEMPERATURE,
                "num_ctx": settings.OLLAMA_NUM_CTX,
                "num_predict": max_tokens,
            },
        }
        if self._send_think_flag:
            payload["think"] = False

        try:
            content = self._stream(payload, expected_tokens or max_tokens, on_progress)
        except LLMError as exc:
            if self._send_think_flag and "think" in str(exc).lower():
                self._send_think_flag = False
                payload.pop("think", None)
                content = self._stream(payload, expected_tokens or max_tokens, on_progress)
            else:
                raise

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model returned invalid JSON: {exc}") from exc

    def _stream(
        self,
        payload: dict,
        expected_tokens: int,
        on_progress: Optional[Callable[[float], None]],
    ) -> str:
        parts: list[str] = []
        tokens = 0
        started = time.monotonic()
        try:
            with httpx.stream(
                "POST",
                f"{settings.OLLAMA_URL}/api/chat",
                json=payload,
                timeout=httpx.Timeout(settings.LLM_TIMEOUT_SECONDS, connect=5.0),
            ) as resp:
                if resp.status_code != 200:
                    body = resp.read().decode("utf-8", errors="replace")
                    raise LLMError(f"Ollama returned {resp.status_code}: {body[:300]}")
                for line in resp.iter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    if event.get("error"):
                        raise LLMError(f"Ollama error: {event['error']}")
                    piece = (event.get("message") or {}).get("content") or ""
                    if piece:
                        parts.append(piece)
                        tokens += 1
                        if on_progress and tokens % 25 == 0:
                            on_progress(min(tokens / max(expected_tokens, 1), 0.95))
                    if event.get("done"):
                        if event.get("done_reason") == "length":
                            raise LLMError("Model output was cut off (num_predict too small)")
                        break
        except httpx.HTTPError as exc:
            with self._lock:
                self._available = None  # force a re-probe next time
            raise LLMError(f"Ollama request failed: {exc}") from exc

        logger.info(
            "LLM call: model=%s tokens=%d seconds=%.1f",
            self.model,
            tokens,
            time.monotonic() - started,
        )
        return "".join(parts)


def _strict_schema(schema: dict) -> dict:
    """Adapt a JSON schema for Claude structured outputs: every object gets
    additionalProperties: false and lists all properties as required, and
    array-length constraints (unsupported there) are dropped — callers trim
    lists themselves."""
    if not isinstance(schema, dict):
        return schema
    out = {k: v for k, v in schema.items() if k not in ("maxItems", "minItems")}
    if out.get("type") == "object" and "properties" in out:
        out["properties"] = {k: _strict_schema(v) for k, v in out["properties"].items()}
        out["required"] = list(out["properties"].keys())
        out["additionalProperties"] = False
    if "items" in out:
        out["items"] = _strict_schema(out["items"])
    return out


class ClaudeService:
    """Anthropic API provider with structured (JSON-schema) outputs."""

    name = "anthropic"
    # Claude's 1M-token context fits even very long transcripts in one call.
    single_pass_max_words = 150_000

    def __init__(self) -> None:
        self._client: Optional[anthropic.Anthropic] = None
        self._auth_failed = False

    @property
    def model(self) -> str:
        return settings.ANTHROPIC_MODEL

    def is_available(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY) and not self._auth_failed

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(
                api_key=settings.ANTHROPIC_API_KEY,
                timeout=settings.LLM_TIMEOUT_SECONDS,
                max_retries=3,
            )
        return self._client

    def chat_json(
        self,
        system: str,
        user: str,
        schema: dict,
        *,
        max_tokens: int = 2048,
        expected_tokens: Optional[int] = None,
        on_progress: Optional[Callable[[float], None]] = None,
    ) -> dict:
        # Thinking tokens count toward max_tokens, so leave generous headroom;
        # streaming keeps long generations clear of HTTP timeouts.
        budget = max(16_000, max_tokens * 4)
        expected_chars = (expected_tokens or max_tokens) * 4
        started = time.monotonic()
        received = 0
        try:
            with self._get_client().beta.messages.stream(
                model=self.model,
                max_tokens=budget,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": settings.ANTHROPIC_EFFORT,
                    "format": {"type": "json_schema", "schema": _strict_schema(schema)},
                },
                # Re-runs the request on Anthropic's recommended model if a
                # safety classifier declines it, instead of failing the video.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                for text in stream.text_stream:
                    received += len(text)
                    if on_progress:
                        on_progress(min(received / max(expected_chars, 1), 0.95))
                message = stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            self._auth_failed = True
            raise LLMError("Anthropic API key was rejected") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Anthropic rate limit reached") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"Couldn't reach the Anthropic API: {exc}") from exc

        if message.stop_reason == "refusal":
            raise LLMError("Claude declined this request")
        if message.stop_reason == "max_tokens":
            raise LLMError("Claude's output was cut off (max_tokens reached)")

        content = "".join(block.text for block in message.content if block.type == "text")
        usage = message.usage
        logger.info(
            "LLM call: model=%s in=%d out=%d seconds=%.1f",
            message.model,
            usage.input_tokens,
            usage.output_tokens,
            time.monotonic() - started,
        )
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Claude returned invalid JSON: {exc}") from exc


class _DisabledService:
    name = "none"
    single_pass_max_words = 0

    def is_available(self) -> bool:
        return False

    def chat_json(self, *args, **kwargs) -> dict:
        raise LLMError("No LLM provider is configured")


def _select_provider():
    provider = settings.LLM_PROVIDER
    if provider == "auto":
        provider = "anthropic" if settings.ANTHROPIC_API_KEY else "ollama"
    if provider == "anthropic":
        return ClaudeService()
    if provider == "ollama":
        return OllamaService()
    return _DisabledService()


llm_service = _select_provider()
logger.info("LLM provider: %s", llm_service.name)
