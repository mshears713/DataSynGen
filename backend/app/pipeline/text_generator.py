from app.core.logging_config import get_logger
from app.models.config import AppConfig
from app.models.llm import LLMResponse, ModelMetadata
from app.models.spec import GenerationSpec
from app.services.base import LLMService

logger = get_logger(__name__)


class TextGenerator:
    def __init__(self, llm_service: LLMService, config: AppConfig):
        self._llm = llm_service
        self._config = config

    async def generate(
        self,
        spec: GenerationSpec,
        run_id: str,
        sample_id: str,
    ) -> tuple[str, str, ModelMetadata]:
        """Returns (generated_text, raw_llm_output, model_metadata)."""
        user_prompt, system_prompt = self._build_prompt(spec)

        response: LLMResponse = await self._llm.complete(
            prompt=user_prompt,
            system=system_prompt,
            task="generation",
            run_id=run_id,
            sample_id=sample_id,
        )

        route = self._config.tasks["generation"]
        prompt_entry = self._config.prompts[route.prompt_ref]
        model_entry = self._config.models[route.model_ref]

        metadata = ModelMetadata(
            model_ref=route.model_ref,
            model_name=model_entry.model,
            provider=model_entry.provider,
            prompt_ref=route.prompt_ref,
            prompt_version=prompt_entry.version,
            task="generation",
            latency_ms=response.latency_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=response.cost_usd,
        )

        return response.text, response.raw, metadata

    def _build_prompt(self, spec: GenerationSpec) -> tuple[str, str]:
        route = self._config.tasks.get("generation")
        if route:
            prompt_entry = self._config.prompts.get(route.prompt_ref)
            if prompt_entry:
                template_vars = self._build_template_vars(spec)
                try:
                    user_prompt = prompt_entry.template.format(**template_vars)
                    return user_prompt, "You are a dataset generation assistant. Output only the requested utterance."
                except KeyError as e:
                    logger.warning(f"Prompt template missing key {e}, using fallback")

        # Fallback prompt
        return self._fallback_prompt(spec), "You are a dataset generation assistant."

    def _build_template_vars(self, spec: GenerationSpec) -> dict:
        def fmt(v: float | None) -> str:
            return str(v) if v is not None else "None"

        return {
            "measurement_phrase": spec.measurement_phrase,
            "value_kind": spec.value_kind.value,
            "value_nominal": fmt(spec.value_nominal),
            "value_min": fmt(spec.value_min),
            "value_max": fmt(spec.value_max),
            "value_tolerance": fmt(spec.value_tolerance),
            "unit_norm": spec.unit_norm,
        }

    def _fallback_prompt(self, spec: GenerationSpec) -> str:
        lines = [
            "Generate a single natural-language utterance that expresses the following measurement.",
            "Output only the utterance. No quotes, no labels.",
            "",
            "Measurement details:",
            f"- Phrase: {spec.measurement_phrase}",
            f"- Value kind: {spec.value_kind.value}",
            f"- Nominal value: {spec.value_nominal}",
            f"- Min value: {spec.value_min}",
            f"- Max value: {spec.value_max}",
            f"- Tolerance: {spec.value_tolerance}",
            f"- Unit: {spec.unit_norm}",
        ]
        return "\n".join(lines)
