"""Anthropic-native LLM service (uses /v1/messages API format)."""
import asyncio
import time
from typing import Any

import httpx

from app.core.exceptions import LLMCallError
from app.core.logging_config import get_logger
from app.models.config import AppConfig, ModelEntry, TaskProfile, PromptEntry
from app.models.llm import LLMResponse

logger = get_logger(__name__)

# Map config model refs to Anthropic model IDs
_ANTHROPIC_MODEL_MAP = {
    "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-opus-4-7": "claude-opus-4-7",
    # Allow any model that starts with "claude-" to pass through
}

# Cost estimates per 1M tokens (input/output) in USD
_COST_TABLE = {
    "claude-haiku-4-5-20251001": (0.80, 4.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-7": (15.0, 75.0),
}


class AnthropicLLMService:
    """LLM service that calls the Anthropic /v1/messages API directly."""

    def __init__(self, base_url: str, api_key: str, config: AppConfig):
        url = base_url.rstrip("/")
        # Ensure the URL includes /v1
        if not url.endswith("/v1"):
            url = url + "/v1"
        self._base_url = url
        self._api_key = api_key
        self._config = config

    async def complete(
        self,
        prompt: str,
        system: str,
        task: str,
        run_id: str,
        sample_id: str | None = None,
    ) -> LLMResponse:
        model_entry, prompt_entry, profile = self._resolve_task(task)
        last_error: Exception | None = None

        for attempt in range(profile.retry_count):
            try:
                return await self._call(
                    prompt=prompt,
                    system=system,
                    model=model_entry.model,
                    profile=profile,
                    model_entry=model_entry,
                    prompt_entry=prompt_entry,
                    task=task,
                    run_id=run_id,
                    sample_id=sample_id,
                )
            except LLMCallError as e:
                last_error = e
                if not e.retryable:
                    raise
                wait = 2 ** attempt
                logger.warning(
                    f"Anthropic call failed (attempt {attempt + 1}/{profile.retry_count}), "
                    f"retrying in {wait}s: {e.message}"
                )
                await asyncio.sleep(wait)
            except Exception as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning(f"Unexpected Anthropic error (attempt {attempt + 1}): {e}")
                await asyncio.sleep(wait)

        raise LLMCallError(
            message="Anthropic call failed after all retries",
            detail=str(last_error),
            retryable=False,
        )

    async def _call(
        self,
        prompt: str,
        system: str,
        model: str,
        profile: TaskProfile,
        model_entry: ModelEntry,
        prompt_entry: PromptEntry,
        task: str,
        run_id: str,
        sample_id: str | None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": profile.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        if profile.temperature is not None:
            payload["temperature"] = profile.temperature

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=profile.timeout) as client:
            try:
                resp = await client.post(
                    f"{self._base_url}/messages",
                    json=payload,
                    headers=headers,
                )
            except httpx.TimeoutException as e:
                raise LLMCallError(
                    message="Anthropic request timed out",
                    detail=str(e),
                    retryable=True,
                )
            except httpx.RequestError as e:
                raise LLMCallError(
                    message="Anthropic request failed",
                    detail=str(e),
                    retryable=True,
                )

        latency_ms = (time.monotonic() - start) * 1000

        if resp.status_code >= 500:
            raise LLMCallError(
                message=f"Anthropic server error: {resp.status_code}",
                detail=resp.text[:500],
                retryable=True,
            )
        if resp.status_code >= 400:
            raise LLMCallError(
                message=f"Anthropic client error: {resp.status_code}",
                detail=resp.text[:500],
                retryable=False,
            )

        raw_json: dict[str, Any] = resp.json()
        text = ""
        try:
            content = raw_json["content"]
            for block in content:
                if block.get("type") == "text":
                    text = block["text"] or ""
                    break
        except (KeyError, IndexError, TypeError) as e:
            raise LLMCallError(
                message="Unexpected Anthropic response format",
                detail=str(e),
                retryable=False,
            )

        usage = raw_json.get("usage", {})
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        cost_usd = self._estimate_cost(model, input_tokens, output_tokens)

        logger.info(
            f"Anthropic call task={task} model={model} run={run_id} "
            f"latency={latency_ms:.0f}ms in={input_tokens} out={output_tokens}"
        )

        return LLMResponse(
            text=text.strip(),
            raw=resp.text,
            model_name=model,
            provider="anthropic",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )

    def _resolve_task(self, task: str) -> tuple[ModelEntry, PromptEntry, TaskProfile]:
        route = self._config.tasks.get(task)
        if not route:
            route = self._config.tasks.get("generation")
        if not route:
            raise LLMCallError(
                message=f"No task routing for '{task}'",
                retryable=False,
            )
        model_entry = self._config.models[route.model_ref]
        prompt_entry = self._config.prompts[route.prompt_ref]
        profile = self._config.profiles[route.profile_ref]
        return model_entry, prompt_entry, profile

    def _estimate_cost(
        self, model: str, input_tokens: int | None, output_tokens: int | None
    ) -> float | None:
        rates = _COST_TABLE.get(model)
        if not rates or input_tokens is None or output_tokens is None:
            return None
        input_rate, output_rate = rates
        return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
