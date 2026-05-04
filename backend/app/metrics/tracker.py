import json
from pathlib import Path

from app.models.metrics import BenchmarkComparison, BenchmarkRow, RunMetrics
from app.models.run import Run
from app.storage.paths import failures_path, samples_path
from app.storage.run_store import RunStore
from app.storage.sample_store import SampleStore


class MetricsTracker:
    def __init__(self, run_store: RunStore, sample_store: SampleStore, data_dir: Path):
        self._run_store = run_store
        self._sample_store = sample_store
        self._data_dir = data_dir

    def compute_run_metrics(self, run_id: str) -> RunMetrics:
        metrics = RunMetrics(run_id=run_id)

        # Aggregate from samples.jsonl
        total_latency = 0.0
        latency_count = 0
        schema_valid = 0
        semantic_valid = 0

        sp = samples_path(self._data_dir, run_id)
        if sp.exists():
            with open(sp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue

                    metrics.samples_attempted += 1
                    status = d.get("status", "")
                    if status == "valid":
                        metrics.samples_valid += 1
                    else:
                        metrics.samples_failed += 1

                    # Schema validation
                    sv = d.get("schema_validation", {})
                    if sv.get("passed"):
                        schema_valid += 1

                    # Semantic validation
                    sem = d.get("semantic_validation")
                    if sem and sem.get("passed"):
                        semantic_valid += 1

                    # Cost and tokens
                    meta = d.get("model_metadata", {})
                    cost = meta.get("cost_usd") or 0.0
                    metrics.cost_usd_total += cost

                    lat = meta.get("latency_ms")
                    if lat is not None:
                        total_latency += lat
                        latency_count += 1

                    in_tok = meta.get("input_tokens") or 0
                    out_tok = meta.get("output_tokens") or 0
                    metrics.total_input_tokens += in_tok
                    metrics.total_output_tokens += out_tok

                    # Model/prompt usage
                    model_ref = meta.get("model_ref", "unknown")
                    prompt_ref = meta.get("prompt_ref", "unknown")
                    metrics.model_usage[model_ref] = metrics.model_usage.get(model_ref, 0) + 1
                    metrics.prompt_usage[prompt_ref] = metrics.prompt_usage.get(prompt_ref, 0) + 1

        # Aggregate from failures.jsonl
        fp = failures_path(self._data_dir, run_id)
        if fp.exists():
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        cat = d.get("failure_category", "unknown")
                        metrics.failure_breakdown[cat] = (
                            metrics.failure_breakdown.get(cat, 0) + 1
                        )
                    except Exception:
                        continue

        # Compute rates
        attempted = metrics.samples_attempted
        if attempted > 0:
            metrics.schema_valid_rate = schema_valid / attempted
            metrics.semantic_match_rate = semantic_valid / attempted
            metrics.overall_valid_rate = metrics.samples_valid / attempted

        if metrics.samples_valid > 0 and metrics.cost_usd_total > 0:
            metrics.cost_per_valid_sample = metrics.cost_usd_total / metrics.samples_valid

        if latency_count > 0:
            metrics.avg_latency_ms = total_latency / latency_count

        return metrics

    def compute_cross_run_summary(self, run_ids: list[str] | None = None) -> dict:
        if run_ids is None:
            runs = self._run_store.load_all_runs()
            run_ids = [r.run_id for r in runs]

        total_samples = 0
        total_valid = 0
        total_cost = 0.0
        all_failure_breakdown: dict[str, int] = {}

        for rid in run_ids:
            m = self.compute_run_metrics(rid)
            total_samples += m.samples_attempted
            total_valid += m.samples_valid
            total_cost += m.cost_usd_total
            for cat, count in m.failure_breakdown.items():
                all_failure_breakdown[cat] = all_failure_breakdown.get(cat, 0) + count

        return {
            "run_count": len(run_ids),
            "total_samples_attempted": total_samples,
            "total_valid_samples": total_valid,
            "overall_valid_rate": total_valid / total_samples if total_samples else 0.0,
            "total_cost_usd": total_cost,
            "failure_breakdown": all_failure_breakdown,
        }

    def compute_benchmark(self, run_ids: list[str]) -> BenchmarkComparison:
        rows: list[BenchmarkRow] = []

        for run_id in run_ids:
            try:
                run = self._run_store.load_run(run_id)
            except Exception:
                continue

            m = self.compute_run_metrics(run_id)
            rc = run.run_config

            rows.append(
                BenchmarkRow(
                    run_id=run_id,
                    run_name=run.name,
                    model_ref=rc.generation_model_ref,
                    model_name=self._resolve_model_name(run, rc.generation_model_ref),
                    prompt_ref=rc.generation_prompt_ref,
                    prompt_version=self._resolve_prompt_version(run, rc.generation_prompt_ref),
                    samples_attempted=m.samples_attempted,
                    samples_valid=m.samples_valid,
                    valid_rate=m.overall_valid_rate,
                    semantic_match_rate=m.semantic_match_rate,
                    cost_usd_total=m.cost_usd_total,
                    cost_per_valid=m.cost_per_valid_sample,
                    avg_latency_ms=m.avg_latency_ms,
                    failure_breakdown=m.failure_breakdown,
                )
            )

        return BenchmarkComparison(runs=rows)

    def _resolve_model_name(self, run: Run, model_ref: str) -> str:
        # Try to read from config snapshot
        try:
            from app.storage.paths import run_config_snapshot_path
            import yaml
            snap = run_config_snapshot_path(self._data_dir, run.run_id)
            if snap.exists():
                data = yaml.safe_load(snap.read_text())
                models = data.get("models", {})
                return models.get(model_ref, {}).get("model", model_ref)
        except Exception:
            pass
        return model_ref

    def _resolve_prompt_version(self, run: Run, prompt_ref: str) -> int:
        try:
            from app.storage.paths import run_config_snapshot_path
            import yaml
            snap = run_config_snapshot_path(self._data_dir, run.run_id)
            if snap.exists():
                data = yaml.safe_load(snap.read_text())
                prompts = data.get("prompts", {})
                return prompts.get(prompt_ref, {}).get("version", 1)
        except Exception:
            pass
        return 1
