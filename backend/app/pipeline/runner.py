"""
PipelineRunner: orchestrates full run execution.

Creates spec list, skips already-processed specs (resumability),
checks pause/cancel events between samples, persists all results.
"""
import asyncio
from datetime import datetime
from uuid import uuid4

from app.core.logging_config import get_logger
from app.models.failure import Failure, FailureCategory
from app.models.run import Run, RunEvent, RunStatus
from app.models.sample import Sample, SampleStatus
from app.pipeline.executor import PipelineExecutor
from app.pipeline.spec_generator import SpecGenerator
from app.pipeline.stages import StageContext
from app.pipeline.task_registry import task_registry
from app.storage.run_store import RunStore
from app.storage.sample_store import SampleStore

logger = get_logger(__name__)


class PipelineRunner:
    def __init__(
        self,
        executor: PipelineExecutor,
        spec_generator: SpecGenerator,
        run_store: RunStore,
        sample_store: SampleStore,
    ):
        self._executor = executor
        self._spec_gen = spec_generator
        self._run_store = run_store
        self._sample_store = sample_store

    async def execute_run(
        self,
        run: Run,
        pause_event: asyncio.Event,
        cancel_event: asyncio.Event,
    ) -> None:
        run_id = run.run_id
        logger.info(f"Pipeline starting: run_id={run_id} target={run.target_count}")

        self._emit_event(run_id, "run_started", f"Pipeline started with target={run.target_count}")

        try:
            # Generate the full spec list deterministically
            specs = self._spec_gen.generate_specs(run.target_count, seed=run.seed)

            # Load already-processed spec IDs for resumability
            done_ids = self._sample_store.get_processed_spec_ids(run_id)
            remaining = [s for s in specs if s.spec_id not in done_ids]

            logger.info(
                f"run={run_id} total_specs={len(specs)} "
                f"already_done={len(done_ids)} remaining={len(remaining)}"
            )

            for spec in remaining:
                # Check cancel first
                if cancel_event.is_set():
                    logger.info(f"Run {run_id} cancelled")
                    run = self._run_store.load_run(run_id)
                    run.status = RunStatus.cancelled
                    run.updated_at = datetime.utcnow()
                    self._run_store.save_run(run)
                    self._emit_event(run_id, "run_cancelled", "Run cancelled by user")
                    return

                # Check pause
                if pause_event.is_set():
                    logger.info(f"Run {run_id} paused")
                    run = self._run_store.load_run(run_id)
                    run.status = RunStatus.paused
                    run.updated_at = datetime.utcnow()
                    self._run_store.save_run(run)
                    self._emit_event(run_id, "run_paused", "Run paused by user")
                    return

                # Process this spec
                sample_id = str(uuid4())
                ctx = StageContext(
                    spec=spec,
                    run_id=run_id,
                    sample_id=sample_id,
                    config=self._spec_gen._config,
                )

                ctx, is_valid = await self._executor.process_spec(ctx)

                # Build and store sample
                sample, failure = self._build_results(ctx, is_valid)
                self._sample_store.append_sample(sample)
                if failure:
                    self._sample_store.append_failure(failure)

                # Update run counters
                run = self._run_store.load_run(run_id)
                run.samples_attempted += 1
                if is_valid:
                    run.samples_valid += 1
                else:
                    run.samples_failed += 1
                if ctx.model_metadata and ctx.model_metadata.cost_usd:
                    run.cost_usd_total += ctx.model_metadata.cost_usd
                run.updated_at = datetime.utcnow()
                self._run_store.save_run(run)

                status_str = "valid" if is_valid else f"failed({ctx.failure_category})"
                self._emit_event(
                    run_id,
                    "sample_completed",
                    f"Sample {sample_id[:8]} {status_str}",
                    {"sample_id": sample_id, "valid": is_valid},
                )

                # Small yield to allow other coroutines to run
                await asyncio.sleep(0)

            # All specs processed
            run = self._run_store.load_run(run_id)
            run.status = RunStatus.completed
            run.completed_at = datetime.utcnow()
            run.updated_at = datetime.utcnow()
            self._run_store.save_run(run)
            self._emit_event(
                run_id,
                "run_completed",
                f"Run completed: {run.samples_valid} valid, {run.samples_failed} failed",
            )
            logger.info(f"Pipeline completed: run_id={run_id}")

        except Exception as e:
            logger.exception(f"Pipeline error for run {run_id}: {e}")
            try:
                run = self._run_store.load_run(run_id)
                run.status = RunStatus.failed
                run.updated_at = datetime.utcnow()
                self._run_store.save_run(run)
                self._emit_event(run_id, "run_failed", f"Pipeline error: {e}")
            except Exception:
                pass

    def _build_results(
        self, ctx: StageContext, is_valid: bool
    ) -> tuple[Sample, Failure | None]:
        from app.models.sample import ValidationResult

        status = SampleStatus.valid if is_valid else SampleStatus.failed
        schema_result = ctx.schema_result or ValidationResult(passed=True)
        semantic_result = ctx.semantic_result

        # Use placeholder metadata if generation failed before metadata was set
        if ctx.model_metadata is None:
            from app.models.llm import ModelMetadata
            ctx.model_metadata = ModelMetadata(
                model_ref="unknown",
                model_name="unknown",
                provider="unknown",
                prompt_ref="unknown",
                prompt_version=0,
                task="generation",
            )

        sample = Sample(
            sample_id=ctx.sample_id,
            run_id=ctx.run_id,
            spec_id=ctx.spec.spec_id,
            spec=ctx.spec,
            generated_text=ctx.generated_text or "",
            raw_llm_output=ctx.raw_llm_output or "",
            status=status,
            schema_validation=schema_result,
            semantic_validation=semantic_result,
            model_metadata=ctx.model_metadata,
            include_in_export=is_valid,
        )

        failure: Failure | None = None
        if not is_valid:
            failure = Failure(
                failure_id=str(uuid4()),
                sample_id=ctx.sample_id,
                run_id=ctx.run_id,
                failure_category=ctx.failure_category or FailureCategory.rejected,
                failure_details=ctx.failure_details,
                original_spec=ctx.spec,
                generated_text=ctx.generated_text,
                validator_output=ctx.semantic_result.extracted if ctx.semantic_result else None,
            )

        return sample, failure

    def _emit_event(
        self,
        run_id: str,
        kind: str,
        message: str,
        data: dict | None = None,
    ) -> None:
        event = RunEvent(
            event_id=str(uuid4()),
            run_id=run_id,
            kind=kind,
            message=message,
            data=data or {},
        )
        try:
            self._run_store.append_event(event)
        except Exception as e:
            logger.warning(f"Failed to emit event {kind} for run {run_id}: {e}")
