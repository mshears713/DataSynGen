"""Tests for API endpoints."""
import time

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    def test_health_check_ok(self, app_client: TestClient):
        resp = app_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["config_loaded"] is True
        assert data["mock_llm"] is True
        assert "timestamp" in data


class TestConfigEndpoints:
    def test_get_config(self, app_client: TestClient):
        resp = app_client.get("/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "measurement_phrases" in data
        assert "models" in data
        assert "prompts" in data

    def test_get_config_raw(self, app_client: TestClient):
        resp = app_client.get("/config/raw")
        assert resp.status_code == 200
        assert "measurement_extraction" in resp.text

    def test_validate_valid_config(self, app_client: TestClient):
        raw = app_client.get("/config/raw").text
        resp = app_client.post(
            "/config/validate",
            content=raw.encode(),
            headers={"Content-Type": "text/plain"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    def test_validate_invalid_config(self, app_client: TestClient):
        resp = app_client.post(
            "/config/validate",
            content=b"{ bad: yaml: :",
            headers={"Content-Type": "text/plain"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False

    def test_list_prompts(self, app_client: TestClient):
        resp = app_client.get("/config/prompts")
        assert resp.status_code == 200
        prompts = resp.json()
        assert isinstance(prompts, list)
        assert len(prompts) > 0
        assert "ref" in prompts[0]

    def test_list_models(self, app_client: TestClient):
        resp = app_client.get("/config/models")
        assert resp.status_code == 200
        models = resp.json()
        assert isinstance(models, list)

    def test_list_task_profiles(self, app_client: TestClient):
        resp = app_client.get("/config/task-profiles")
        assert resp.status_code == 200
        profiles = resp.json()
        assert isinstance(profiles, list)

    def test_list_task_routing(self, app_client: TestClient):
        resp = app_client.get("/config/task-routing")
        assert resp.status_code == 200
        routing = resp.json()
        assert isinstance(routing, list)


class TestRunEndpoints:
    def test_create_run(self, app_client: TestClient):
        resp = app_client.post("/runs", json={"target_count": 5, "name": "test run"})
        assert resp.status_code == 201
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "created"
        assert data["target_count"] == 5

    def test_list_runs(self, app_client: TestClient):
        app_client.post("/runs", json={"target_count": 3})
        resp = app_client.get("/runs")
        assert resp.status_code == 200
        runs = resp.json()
        assert isinstance(runs, list)
        assert len(runs) >= 1

    def test_get_run(self, app_client: TestClient):
        create_resp = app_client.post("/runs", json={"target_count": 3})
        run_id = create_resp.json()["run_id"]
        resp = app_client.get(f"/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == run_id

    def test_get_nonexistent_run(self, app_client: TestClient):
        resp = app_client.get("/runs/nonexistent_run_xyz")
        assert resp.status_code == 404

    def test_list_runs_filter_status(self, app_client: TestClient):
        resp = app_client.get("/runs?status=created")
        assert resp.status_code == 200

    def test_list_runs_invalid_status(self, app_client: TestClient):
        resp = app_client.get("/runs?status=invalid_status")
        assert resp.status_code == 400

    def test_run_metrics_endpoint(self, app_client: TestClient):
        create_resp = app_client.post("/runs", json={"target_count": 3})
        run_id = create_resp.json()["run_id"]
        resp = app_client.get(f"/runs/{run_id}/metrics")
        assert resp.status_code == 200
        metrics = resp.json()
        assert "samples_attempted" in metrics
        assert "samples_valid" in metrics

    def test_run_events_endpoint(self, app_client: TestClient):
        create_resp = app_client.post("/runs", json={"target_count": 3})
        run_id = create_resp.json()["run_id"]
        resp = app_client.get(f"/runs/{run_id}/events")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_pause_non_running_run_fails(self, app_client: TestClient):
        create_resp = app_client.post("/runs", json={"target_count": 3})
        run_id = create_resp.json()["run_id"]
        resp = app_client.post(f"/runs/{run_id}/pause")
        assert resp.status_code == 409

    def test_resume_non_paused_run_fails(self, app_client: TestClient):
        create_resp = app_client.post("/runs", json={"target_count": 3})
        run_id = create_resp.json()["run_id"]
        resp = app_client.post(f"/runs/{run_id}/resume")
        assert resp.status_code == 409

    def test_cancel_created_run_fails(self, app_client: TestClient):
        create_resp = app_client.post("/runs", json={"target_count": 3})
        run_id = create_resp.json()["run_id"]
        resp = app_client.post(f"/runs/{run_id}/cancel")
        assert resp.status_code == 409


class TestSampleEndpoints:
    def test_list_samples_empty_run(self, app_client: TestClient):
        create_resp = app_client.post("/runs", json={"target_count": 3})
        run_id = create_resp.json()["run_id"]
        resp = app_client.get(f"/runs/{run_id}/samples")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["samples"] == []

    def test_list_failures_empty_run(self, app_client: TestClient):
        create_resp = app_client.post("/runs", json={"target_count": 3})
        run_id = create_resp.json()["run_id"]
        resp = app_client.get(f"/runs/{run_id}/failures")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_list_samples_nonexistent_run(self, app_client: TestClient):
        resp = app_client.get("/runs/no_such_run/samples")
        assert resp.status_code == 404

    def test_invalid_sample_status_filter(self, app_client: TestClient):
        create_resp = app_client.post("/runs", json={"target_count": 3})
        run_id = create_resp.json()["run_id"]
        resp = app_client.get(f"/runs/{run_id}/samples?status=invalid")
        assert resp.status_code == 400


class TestMetricsEndpoints:
    def test_metrics_summary(self, app_client: TestClient):
        resp = app_client.get("/metrics/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "run_count" in data
        assert "total_samples_attempted" in data


class TestExportEndpoints:
    def test_list_exports_empty(self, app_client: TestClient):
        resp = app_client.get("/exports")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_export_nonexistent_run(self, app_client: TestClient):
        resp = app_client.post(
            "/exports",
            json={"run_ids": ["nonexistent_run"], "format": "jsonl"},
        )
        assert resp.status_code == 404

    def test_get_nonexistent_export(self, app_client: TestClient):
        resp = app_client.get("/exports/doesnotexist")
        assert resp.status_code == 404
