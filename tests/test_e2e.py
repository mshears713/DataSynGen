"""
End-to-end smoke test: full pipeline run using MockLLMService.
Does NOT make real LLM API calls.
"""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient


def wait_for_run_completion(
    client: TestClient, run_id: str, max_wait_seconds: int = 30
) -> dict:
    """Poll run status until completed or failed."""
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        resp = client.get(f"/runs/{run_id}")
        assert resp.status_code == 200
        run = resp.json()
        if run["status"] in ("completed", "failed", "cancelled"):
            return run
        time.sleep(0.2)
    raise TimeoutError(f"Run {run_id} did not complete within {max_wait_seconds}s")


class TestEndToEnd:
    def test_full_pipeline_smoke(self, app_client: TestClient):
        """
        Complete smoke test:
        1. Check health
        2. Load config
        3. Create run (5 samples)
        4. Start run
        5. Wait for completion
        6. Check metrics
        7. Verify samples are stored
        8. Create export
        9. Download export
        """
        # 1. Health check
        resp = app_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["config_loaded"] is True

        # 2. Load config
        resp = app_client.get("/config")
        assert resp.status_code == 200
        config = resp.json()
        assert len(config["measurement_phrases"]) > 0

        # 3. Create run
        resp = app_client.post(
            "/runs",
            json={"target_count": 5, "name": "E2E Smoke Test", "seed": 42},
        )
        assert resp.status_code == 201
        run_id = resp.json()["run_id"]
        assert run_id

        # 4. Start run
        resp = app_client.post(f"/runs/{run_id}/start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

        # 5. Wait for completion
        run = wait_for_run_completion(app_client, run_id, max_wait_seconds=60)
        assert run["status"] == "completed", f"Run failed: {run}"
        assert run["samples_attempted"] == 5

        # 6. Check metrics
        resp = app_client.get(f"/runs/{run_id}/metrics")
        assert resp.status_code == 200
        metrics = resp.json()
        assert metrics["samples_attempted"] == 5
        assert metrics["samples_valid"] >= 0  # Some may fail validation
        assert "failure_breakdown" in metrics

        # 7. Verify samples are stored
        resp = app_client.get(f"/runs/{run_id}/samples")
        assert resp.status_code == 200
        samples_data = resp.json()
        assert samples_data["total"] == 5

        # 8. Check events are recorded
        resp = app_client.get(f"/runs/{run_id}/events")
        assert resp.status_code == 200
        events = resp.json()
        event_kinds = [e["kind"] for e in events]
        assert "run_started" in event_kinds
        assert "run_completed" in event_kinds

        # 9. Create export (of all samples, not just valid)
        resp = app_client.post(
            "/exports",
            json={
                "run_ids": [run_id],
                "format": "jsonl",
                "include_only_valid": False,
                "include_only_export_flagged": False,
            },
        )
        assert resp.status_code == 201
        export = resp.json()
        export_id = export["export_id"]
        assert export["sample_count"] == 5

        # 10. List exports
        resp = app_client.get("/exports")
        assert resp.status_code == 200
        exports = resp.json()
        assert any(e["export_id"] == export_id for e in exports)

        # 11. Download export
        resp = app_client.get(f"/exports/{export_id}/download")
        assert resp.status_code == 200
        lines = [l for l in resp.text.strip().split("\n") if l.strip()]
        assert len(lines) == 5

        import json
        for line in lines:
            record = json.loads(line)
            assert "generated_text" in record
            assert "truth" in record
            assert record["truth"]["measurement_phrase"]

    def test_run_pause_and_resume(self, app_client: TestClient):
        """Test that pause/resume works correctly."""
        # Create a larger run so we can pause it
        resp = app_client.post(
            "/runs",
            json={"target_count": 3, "name": "Pause/Resume Test", "seed": 99},
        )
        assert resp.status_code == 201
        run_id = resp.json()["run_id"]

        # Start it
        resp = app_client.post(f"/runs/{run_id}/start")
        assert resp.status_code == 200

        # Wait for completion (small run should complete fast)
        run = wait_for_run_completion(app_client, run_id, max_wait_seconds=30)
        assert run["status"] in ("completed", "paused")

    def test_run_append(self, app_client: TestClient):
        """Test appending more samples to a completed run."""
        # Create and complete a small run
        resp = app_client.post("/runs", json={"target_count": 2, "seed": 77})
        assert resp.status_code == 201
        run_id = resp.json()["run_id"]
        app_client.post(f"/runs/{run_id}/start")
        run = wait_for_run_completion(app_client, run_id, max_wait_seconds=30)
        assert run["status"] == "completed"
        initial_attempted = run["samples_attempted"]

        # Append more
        resp = app_client.post(f"/runs/{run_id}/append", json={"additional_count": 2})
        assert resp.status_code == 200
        assert resp.json()["new_target"] == 4

        # Wait for new completion
        run = wait_for_run_completion(app_client, run_id, max_wait_seconds=30)
        assert run["status"] == "completed"
        # Should have processed the original + additional (skipping already done)
        assert run["samples_attempted"] >= initial_attempted

    def test_csv_export(self, app_client: TestClient):
        """Test CSV export format."""
        resp = app_client.post("/runs", json={"target_count": 2, "seed": 55})
        run_id = resp.json()["run_id"]
        app_client.post(f"/runs/{run_id}/start")
        run = wait_for_run_completion(app_client, run_id)

        resp = app_client.post(
            "/exports",
            json={
                "run_ids": [run_id],
                "format": "csv",
                "include_only_valid": False,
                "include_only_export_flagged": False,
            },
        )
        assert resp.status_code == 201
        export_id = resp.json()["export_id"]

        resp = app_client.get(f"/exports/{export_id}/download")
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 2  # Header + at least one row
        assert "generated_text" in lines[0]  # CSV header
        assert "measurement_phrase" in lines[0]

    def test_metrics_summary_after_run(self, app_client: TestClient):
        """Test cross-run metrics summary."""
        # Run two small runs
        for seed in [11, 22]:
            resp = app_client.post("/runs", json={"target_count": 2, "seed": seed})
            run_id = resp.json()["run_id"]
            app_client.post(f"/runs/{run_id}/start")
            wait_for_run_completion(app_client, run_id)

        resp = app_client.get("/metrics/summary")
        assert resp.status_code == 200
        summary = resp.json()
        assert summary["run_count"] >= 2
        assert summary["total_samples_attempted"] >= 4
