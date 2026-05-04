import asyncio
import time
from typing import Any

import httpx

from app.core.exceptions import LLMCallError
from app.core.logging_config import get_logger
from app.models.config import AppConfig, ModelEntry, TaskProfile, PromptEntry
from app.models.llm import LLMResponse

logger = get_logger(__name__)


class TokenRouterService:
    """LLM service that calls a TokenRouter (OpenAI-compatible) API."""

    def __init__(self, base_url: str, api_key: str, config: AppConfig):
        self._base_url = base_url.rstrip("/")
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
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        last_error: Exception | None = None
        for attempt in range(profile.retry_count):
            try:
                return await self._call(
                    messages=messages,
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
                    f"LLM call failed (attempt {attempt + 1}/{profile.retry_count}), "
                    f"retrying in {wait}s: {e.message}"
                )
                await asyncio.sleep(wait)
            except Exception as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning(f"Unexpected LLM error (attempt {attempt + 1}): {e}")
                await asyncio.sleep(wait)

        raise LLMCallError(
            message="LLM call failed after all retries",
            detail=str(last_error),
            retryable=False,
        )

    async def _call(
        self,
        messages: list[dict],
        model: str,
        profile: TaskProfile,
        model_entry: ModelEntry,
        prompt_entry: PromptEntry,
        task: str,
        run_id: str,
        sample_id: str | None,
    ) -> LLMResponse:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": profile.temperature,
            "max_tokens": profile.max_tokens,
        }

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=profile.timeout) as client:
            try:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
            except httpx.TimeoutException as e:
                raise LLMCallError(
                    message="LLM request timed out",
                    detail=str(e),
                    retryable=True,
                )
            except httpx.RequestError as e:
                raise LLMCallError(
                    message="LLM request failed",
                    detail=str(e),
                    retryable=True,
                )

        latency_ms = (time.monotonic() - start) * 1000

        if resp.status_code >= 500:
            raise LLMCallError(
                message=f"LLM API server error: {resp.status_code}",
                detail=resp.text[:500],
                retryable=True,
            )
        if resp.status_code >= 400:
            raise LLMCallError(
                message=f"LLM API client error: {resp.status_code}",
                detail=resp.text[:500],
                retryable=False,
            )

        raw_json: dict[str, Any] = resp.json()
        text = ""
        try:
            text = raw_json["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as e:
            raise LLMCallError(
                message="Unexpected LLM response format",
                detail=str(e),
                retryable=False,
            )

        usage = raw_json.get("usage", {})
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        cost_usd = self._estimate_cost(model, input_tokens, output_tokens)

        logger.info(
            f"LLM call completed task={task} model={model} run={run_id} "
            f"latency={latency_ms:.0f}ms in={input_tokens} out={output_tokens}"
        )

        return LLMResponse(
            text=text.strip(),
            raw=resp.text,
            model_name=model,
            provider=model_entry.provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )

    def _resolve_task(self, task: str) -> tuple[ModelEntry, PromptEntry, TaskProfile]:
        route = self._config.tasks.get(task)
        if not route:
            # Fall back to generation task
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
        # Rough cost estimates per 1M tokens (input/output)
        # These are approximations; real costs depend on provider pricing
        cost_table = {
            "google/gemini-flash": (0.075, 0.30),
            "openai/gpt-4.1": (2.0, 8.0),
            "anthropic/claude-sonnet": (3.0, 15.0),
        }
        rates = cost_table.get(model)
        if not rates or input_tokens is None or output_tokens is None:
            return None
        input_rate, output_rate = rates
        return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
