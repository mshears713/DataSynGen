"""Tests for LLM services (mock and TokenRouter)."""
import pytest

from app.models.llm import LLMResponse
from app.services.mock_llm import MockLLMService


class TestMockLLMService:
    @pytest.mark.asyncio
    async def test_complete_returns_response(self, mock_llm: MockLLMService):
        resp = await mock_llm.complete(
            prompt="- Phrase: outer diameter\n- Value kind: exact\n- Nominal value: 65.0\n- Unit: mm",
            system="Generate an utterance.",
            task="generation",
            run_id="test_run",
            sample_id="test_sample",
        )
        assert isinstance(resp, LLMResponse)
        assert resp.text
        assert resp.model_name == "mock/model"
        assert resp.provider == "mock"

    @pytest.mark.asyncio
    async def test_generation_task_returns_text(self, mock_llm: MockLLMService):
        resp = await mock_llm.complete(
            prompt="- Phrase: outer diameter\n- Value kind: exact\n- Nominal value: 65.0\n- Min value: None\n- Max value: None\n- Tolerance: None\n- Unit: mm",
            system="",
            task="generation",
            run_id="r1",
            sample_id="s1",
        )
        assert resp.text
        assert "diameter" in resp.text.lower() or "65" in resp.text

    @pytest.mark.asyncio
    async def test_validation_task_returns_json(self, mock_llm: MockLLMService):
        import json
        resp = await mock_llm.complete(
            prompt='Utterance: "Outer diameter is 65.0 mm."',
            system="",
            task="validation",
            run_id="r1",
            sample_id="s1",
        )
        assert resp.text
        data = json.loads(resp.text)
        assert "measurement_phrase" in data
        assert "unit_norm" in data

    @pytest.mark.asyncio
    async def test_mock_captures_metadata(self, mock_llm: MockLLMService):
        resp = await mock_llm.complete(
            prompt="test", system="", task="generation", run_id="r1"
        )
        assert resp.input_tokens is not None
        assert resp.output_tokens is not None
        assert resp.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_mock_fail_after(self):
        failing_mock = MockLLMService(fail_after=0)
        from app.core.exceptions import LLMCallError
        with pytest.raises(LLMCallError):
            await failing_mock.complete(
                prompt="test", system="", task="generation", run_id="r1"
            )

    @pytest.mark.asyncio
    async def test_range_spec_generation(self, mock_llm: MockLLMService):
        resp = await mock_llm.complete(
            prompt="- Phrase: width\n- Value kind: range\n- Nominal value: None\n- Min value: 10.0\n- Max value: 20.0\n- Tolerance: None\n- Unit: mm",
            system="",
            task="generation",
            run_id="r1",
            sample_id="s1",
        )
        assert resp.text
        # Should mention "between" or contain both numbers
        assert "10" in resp.text or "between" in resp.text.lower()

    def test_mock_does_not_expose_secrets(self, mock_llm: MockLLMService):
        # MockLLMService should not have any API key attribute
        assert not hasattr(mock_llm, "api_key")
        assert not hasattr(mock_llm, "_api_key")
