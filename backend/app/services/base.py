from typing import Protocol, runtime_checkable

from app.models.llm import LLMResponse


@runtime_checkable
class LLMService(Protocol):
    async def complete(
        self,
        prompt: str,
        system: str,
        task: str,
        run_id: str,
        sample_id: str | None = None,
    ) -> LLMResponse: ...
