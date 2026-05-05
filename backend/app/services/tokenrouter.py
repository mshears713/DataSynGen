import asyncio
import time
from typing import Any

import httpx

from app.core.exceptions import LLMCallError
from app.core.logging_config import get_logger
from app.models.config import AppConfig, ModelEntry, TaskProfile, PromptEntry
from app.models.llm import LLMResponse

logger = get_logger(__name__)

# Endpoint suffix for each API mode
_ENDPOINT_SUFFIX: dict[str, str] = {
    "openai_chat":  "/chat/completions",
    "native_route": "/route",
    "responses":    "/responses",
}


class TokenRouterService:
    """LLM service that calls a TokenRouter (OpenAI-compatible) API.

    Supports three API modes controlled by TOKENROUTER_API_MODE:
      openai_chat  — POST {base_url}/chat/completions  {model, messages}
      native_route — POST {base_url}/route             {prompt}
      responses    — POST {base_url}/responses         {model, input}
    """

    def __init__(self, base_url: str, api_key: str, config: AppConfig, mode: str = "openai_chat"):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._config = config
        self._mode = mode if mode in _ENDPOINT_SUFFIX else "openai_chat"
        self._endpoint = self._base_url + _ENDPOINT_SUFFIX[self._mode]

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
                    f"retrying in {wait}s: task={task} model={model_entry.model} run={run_id} — {e.message}"
                )
                await asyncio.sleep(wait)
            except Exception as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning(
                    f"Unexpected LLM error (attempt {attempt + 1}/{profile.retry_count}): "
                    f"task={task} model={model_entry.model} run={run_id} — {type(e).__name__}: {e}"
                )
                await asyncio.sleep(wait)

        raise LLMCallError(
            message=f"LLM call failed after {profile.retry_count} attempts: {last_error}",
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
        payload = self._build_payload(messages, model, profile)

        logger.info(
            f"LLM request starting: task={task} model={model} mode={self._mode} "
            f"run={run_id} sample={sample_id or 'n/a'} endpoint={self._endpoint} timeout={profile.timeout}s"
        )

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=profile.timeout) as client:
            try:
                resp = await client.post(
                    self._endpoint,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
            except httpx.TimeoutException as e:
                msg = f"TokenRouter request timed out after {profile.timeout}s: task={task} model={model}"
                logger.error(f"{msg} run={run_id}")
                raise LLMCallError(message=msg, detail=str(e), retryable=True)
            except httpx.RequestError as e:
                msg = f"TokenRouter connection failed ({type(e).__name__}): {self._base_url}"
                logger.error(f"{msg} run={run_id}: {e}")
                raise LLMCallError(message=msg, detail=str(e), retryable=True)

        latency_ms = (time.monotonic() - start) * 1000

        if resp.status_code >= 500:
            body_excerpt = resp.text[:400]
            if resp.status_code == 503:
                msg = (
                    f"TokenRouter HTTP 503 Service Unavailable: task={task} model={model} mode={self._mode}"
                    f" — model may not be supported on this route or the provider is temporarily down."
                    f" Try model gpt-4o or check TOKENROUTER_API_MODE / run the smoke test."
                )
            else:
                msg = f"TokenRouter HTTP {resp.status_code} server error: task={task} model={model}"
            logger.error(f"{msg} run={run_id} body={body_excerpt}")
            raise LLMCallError(message=msg, detail=body_excerpt, retryable=True)

        if resp.status_code >= 400:
            body_excerpt = resp.text[:400]
            if resp.status_code == 401:
                msg = f"TokenRouter HTTP 401 Unauthorized — check TOKENROUTER_API_KEY (task={task})"
            elif resp.status_code == 403:
                msg = f"TokenRouter HTTP 403 Forbidden — API key lacks permission for task={task} model={model}"
            elif resp.status_code == 404:
                is_html = "<html" in body_excerpt.lower()
                if is_html:
                    msg = (
                        f"TokenRouter HTTP 404 Not Found (HTML response) — wrong base URL or endpoint. "
                        f"Current: {self._endpoint} mode={self._mode}. "
                        f"Run the smoke test to find the working variant."
                    )
                else:
                    msg = (
                        f"TokenRouter HTTP 404 Not Found — model '{model}' may not exist on this router "
                        f"(task={task} mode={self._mode})"
                    )
            elif resp.status_code == 422:
                msg = f"TokenRouter HTTP 422 Unprocessable — bad request for task={task} model={model}: {body_excerpt[:200]}"
            elif resp.status_code == 429:
                msg = f"TokenRouter HTTP 429 Too Many Requests — rate limited (task={task} model={model})"
            else:
                msg = f"TokenRouter HTTP {resp.status_code} client error: task={task} model={model}"
            logger.error(f"{msg} run={run_id} body={body_excerpt}")
            raise LLMCallError(message=msg, detail=body_excerpt, retryable=False)

        raw_json: dict[str, Any] = resp.json()
        text = self._extract_text(raw_json, task, model)

        usage = raw_json.get("usage", {})
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
        output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
        cost_usd = self._estimate_cost(model, input_tokens, output_tokens)

        logger.info(
            f"LLM request succeeded: task={task} model={model} mode={self._mode} run={run_id} "
            f"latency={latency_ms:.0f}ms in={input_tokens} out={output_tokens} cost={cost_usd}"
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

    # ------------------------------------------------------------------
    # Payload construction
    # ------------------------------------------------------------------

    def _build_payload(self, messages: list[dict], model: str, profile: TaskProfile) -> dict[str, Any]:
        if self._mode == "openai_chat":
            return {
                "model": model,
                "messages": messages,
                "temperature": profile.temperature,
                "max_tokens": profile.max_tokens,
            }

        if self._mode == "native_route":
            parts = []
            for m in messages:
                if m["role"] == "system":
                    parts.append(f"System: {m['content']}")
                else:
                    parts.append(m["content"])
            return {
                "prompt": "\n\n".join(parts),
                "temperature": profile.temperature,
                "max_tokens": profile.max_tokens,
            }

        if self._mode == "responses":
            sys_content = next((m["content"] for m in messages if m["role"] == "system"), None)
            user_content = next((m["content"] for m in messages if m["role"] == "user"), "")
            payload: dict[str, Any] = {
                "model": model,
                "input": user_content,
                "max_tokens": profile.max_tokens,
            }
            if sys_content:
                payload["instructions"] = sys_content
            return payload

        # Unreachable — mode is validated in __init__
        raise ValueError(f"Unhandled mode: {self._mode}")

    # ------------------------------------------------------------------
    # Response text extraction
    # ------------------------------------------------------------------

    def _extract_text(self, raw_json: dict[str, Any], task: str, model: str) -> str:
        if self._mode == "openai_chat":
            try:
                return raw_json["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError) as e:
                raise LLMCallError(
                    message=f"TokenRouter response parse error: missing choices[0].message.content (task={task} model={model})",
                    detail=str(e),
                    retryable=False,
                )

        if self._mode == "responses":
            # OpenAI Responses API: output[0].content[0].text
            try:
                return raw_json["output"][0]["content"][0]["text"]
            except (KeyError, IndexError, TypeError):
                pass
            try:
                return raw_json["output"][0]["text"]
            except (KeyError, IndexError, TypeError):
                pass
            # Graceful fallback to openai_chat shape
            try:
                return raw_json["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError):
                pass
            raise LLMCallError(
                message=f"TokenRouter responses: cannot parse text from response (task={task} model={model}). Keys: {list(raw_json.keys())}",
                retryable=False,
            )

        if self._mode == "native_route":
            for key in ("response", "text", "output", "result", "completion"):
                val = raw_json.get(key)
                if isinstance(val, str) and val:
                    return val
            # Fallback to openai_chat shape
            try:
                return raw_json["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError):
                pass
            raise LLMCallError(
                message=f"TokenRouter native_route: cannot parse text from response (task={task} model={model}). Keys: {list(raw_json.keys())}",
                retryable=False,
            )

        raise ValueError(f"Unhandled mode: {self._mode}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_task(self, task: str) -> tuple[ModelEntry, PromptEntry, TaskProfile]:
        route = self._config.tasks.get(task)
        if not route:
            route = self._config.tasks.get("generation")
        if not route:
            raise LLMCallError(
                message=f"No task routing for '{task}' and no 'generation' fallback",
                retryable=False,
            )
        model_entry = self._config.models[route.model_ref]
        prompt_entry = self._config.prompts[route.prompt_ref]
        profile = self._config.profiles[route.profile_ref]
        return model_entry, prompt_entry, profile

    def _estimate_cost(
        self, model: str, input_tokens: int | None, output_tokens: int | None
    ) -> float | None:
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
