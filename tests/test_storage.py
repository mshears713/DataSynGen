"""Tests for run, sample, and failure storage."""
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.exceptions import NotFoundError
from app.models.failure import Failure, FailureCategory
from app.models.llm import ModelMetadata
from app.models.run import Run, RunConfig, RunEvent, RunStatus
from app.models.sample import Sample, SampleStatus, SampleUpdate, ValidationResult
from app.models.spec import GenerationSpec, ValueKind
from app.storage.run_store import RunStore
from app.storage.sample_store import SampleStore


def make_run(run_id: str = None, target: int = 10) -> Run:
    return Run(
        run_id=run_id or str(uuid4())[:8],
        run_config=RunConfig(
            generation_model_ref="fast_model",
            validation_model_ref="validator_model",
            generation_prompt_ref="gen_prompt_v1",
            validation_prompt_ref="val_prompt_v1",
            generation_profile_ref="fast_profile",
            validation_profile_ref="strict_profile",
        ),
        target_count=target,
    )


def make_spec(spec_id: str = None) -> GenerationSpec:
    return GenerationSpec(
        spec_id=spec_id or "abc123",
        measurement_phrase="outer diameter",
        value_kind=ValueKind.exact,
        value_nominal=65.0,
        unit_norm="mm",
    )


def make_sample(run_id: str, spec_id: str = "abc123") -> Sample:
    return Sample(
        sample_id=str(uuid4()),
        run_id=run_id,
        spec_id=spec_id,
        spec=make_spec(spec_id),
        generated_text="Outer diameter is 65 mm.",
        raw_llm_output="Outer diameter is 65 mm.",
        status=SampleStatus.valid,
        schema_validation=ValidationResult(passed=True),
        model_metadata=ModelMetadata(
            model_ref="fast_model",
            model_name="mock/fast",
            provider="mock",
            prompt_ref="gen_prompt_v1",
            prompt_version=1,
            task="generation",
        ),
    )


def make_failure(run_id: str, spec_id: str = "abc123") -> Failure:
    return Failure(
        failure_id=str(uuid4()),
        run_id=run_id,
        failure_category=FailureCategory.wrong_value,
        failure_details="Value mismatch",
        original_spec=make_spec(spec_id),
        generated_text="Outer diameter is 55 mm.",
    )


class TestRunStore:
    def test_save_and_load_run(self, run_store: RunStore):
        run = make_run("run_001")
        run_store.save_run(run)
        loaded = run_store.load_run("run_001")
        assert loaded.run_id == "run_001"
        assert loaded.status == RunStatus.created

    def test_load_nonexistent_raises(self, run_store: RunStore):
        with pytest.raises(NotFoundError):
            run_store.load_run("does_not_exist")

    def test_load_all_runs(self, run_store: RunStore):
        run_store.save_run(make_run("run_a"))
        run_store.save_run(make_run("run_b"))
        runs = run_store.load_all_runs()
        ids = [r.run_id for r in runs]
        assert "run_a" in ids
        assert "run_b" in ids

    def test_update_run_status(self, run_store: RunStore):
        run = make_run("run_upd")
        run_store.save_run(run)
        run.status = RunStatus.running
        run_store.save_run(run)
        loaded = run_store.load_run("run_upd")
        assert loaded.status == RunStatus.running

    def test_append_and_load_events(self, run_store: RunStore):
        run = make_run("run_events")
        run_store.save_run(run)
        event = RunEvent(
            event_id=str(uuid4()),
            run_id="run_events",
            kind="run_started",
            message="Pipeline started",
        )
        run_store.append_event(event)
        events = run_store.load_events("run_events")
        assert len(events) == 1
        assert events[0].kind == "run_started"

    def test_recover_stale_running_runs(self, run_store: RunStore):
        run = make_run("run_stale")
        run.status = RunStatus.running
        run_store.save_run(run)
        recovered = run_store.recover_stale_running_runs()
        assert "run_stale" in recovered
        loaded = run_store.load_run("run_stale")
        assert loaded.status == RunStatus.paused


class TestSampleStore:
    def test_append_and_load_sample(self, sample_store: SampleStore, run_store: RunStore):
        run = make_run("run_s1")
        run_store.save_run(run)
        sample = make_sample("run_s1", "spec_1")
        sample_store.append_sample(sample)
        samples, total = sample_store.load_samples("run_s1")
        assert total == 1
        assert samples[0].spec_id == "spec_1"

    def test_sample_filter_by_status(self, sample_store: SampleStore, run_store: RunStore):
        run = make_run("run_filter")
        run_store.save_run(run)
        valid_sample = make_sample("run_filter", "spec_v")
        failed_sample = make_sample("run_filter", "spec_f")
        failed_sample.status = SampleStatus.failed
        sample_store.append_sample(valid_sample)
        sample_store.append_sample(failed_sample)

        valids, total_v = sample_store.load_samples("run_filter", status=SampleStatus.valid)
        assert total_v == 1
        assert valids[0].status == SampleStatus.valid

    def test_get_processed_spec_ids(self, sample_store: SampleStore, run_store: RunStore):
        run = make_run("run_specids")
        run_store.save_run(run)
        sample_store.append_sample(make_sample("run_specids", "spec_x"))
        sample_store.append_sample(make_sample("run_specids", "spec_y"))
        ids = sample_store.get_processed_spec_ids("run_specids")
        assert "spec_x" in ids
        assert "spec_y" in ids

    def test_resume_skips_processed(self, sample_store: SampleStore, run_store: RunStore):
        run = make_run("run_resume")
        run_store.save_run(run)
        sample_store.append_sample(make_sample("run_resume", "spec_done"))
        done_ids = sample_store.get_processed_spec_ids("run_resume")
        # Simulate resume: should skip spec_done
        all_specs = ["spec_done", "spec_new"]
        remaining = [s for s in all_specs if s not in done_ids]
        assert remaining == ["spec_new"]

    def test_update_sample(self, sample_store: SampleStore, run_store: RunStore):
        run = make_run("run_upd_s")
        run_store.save_run(run)
        sample = make_sample("run_upd_s")
        sample_store.append_sample(sample)
        update = SampleUpdate(notes="great sample", include_in_export=False)
        updated = sample_store.update_sample("run_upd_s", sample.sample_id, update)
        assert updated.notes == "great sample"
        assert updated.include_in_export is False

    def test_append_and_load_failure(self, sample_store: SampleStore, run_store: RunStore):
        run = make_run("run_fail")
        run_store.save_run(run)
        failure = make_failure("run_fail")
        sample_store.append_failure(failure)
        failures, total = sample_store.load_failures("run_fail")
        assert total == 1
        assert failures[0].failure_category == FailureCategory.wrong_value

    def test_load_failure_by_category(self, sample_store: SampleStore, run_store: RunStore):
        run = make_run("run_fail_cat")
        run_store.save_run(run)
        f1 = make_failure("run_fail_cat")
        f1.failure_category = FailureCategory.missing_unit
        f2 = make_failure("run_fail_cat")
        f2.failure_category = FailureCategory.wrong_value
        sample_store.append_failure(f1)
        sample_store.append_failure(f2)
        filtered, total = sample_store.load_failures(
            "run_fail_cat", category=FailureCategory.missing_unit
        )
        assert total == 1
        assert filtered[0].failure_category == FailureCategory.missing_unit

    def test_empty_run_returns_empty(self, sample_store: SampleStore):
        samples, total = sample_store.load_samples("nonexistent_run")
        assert total == 0
        assert samples == []
