"""
PipelineExecutor: runs a list of stages for each spec.
Handles the retry loop for transient failures (e.g., empty output).
"""
from app.pipeline.stages import PipelineStage, StageContext, StageResult


class PipelineExecutor:
    def __init__(self, stages: list[PipelineStage], max_retries: int = 2):
        self._stages = stages
        self._max_retries = max_retries

    async def process_spec(self, ctx: StageContext) -> tuple[StageContext, bool]:
        """
        Run all stages for the given spec context.
        Returns (final_ctx, is_valid).
        Handles retry internally for 'retry' stage results.
        """
        for attempt in range(self._max_retries + 1):
            ctx.attempt = attempt
            result = await self._run_stages(ctx)

            if result.status == "stop_valid":
                return ctx, True
            elif result.status == "stop_failed":
                ctx.failure_category = result.failure_category
                ctx.failure_details = result.failure_details
                return ctx, False
            elif result.status == "retry":
                if attempt < self._max_retries:
                    continue
                # Exhausted retries
                ctx.failure_category = result.failure_category
                ctx.failure_details = (
                    result.failure_details
                    + f" (failed after {self._max_retries + 1} attempts)"
                )
                return ctx, False

        # Should not reach here
        return ctx, False

    async def _run_stages(self, ctx: StageContext) -> StageResult:
        for stage in self._stages:
            result = await stage.run(ctx)
            if result.status != "continue":
                return result
        # All stages returned 'continue' — treat as valid
        from app.pipeline.stages import StageResult as SR
        return SR(status="stop_valid")
