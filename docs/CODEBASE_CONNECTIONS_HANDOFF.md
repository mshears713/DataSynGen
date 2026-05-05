# Measurement Dataset Foundry Codebase Handoff

Generated on 2026-05-05.

This document is for an agent or copilot that cannot see the code. It does not repeat the product vision from the README or PRDs. Instead, it explains what is currently implemented, how the frontend and backend are actually connected, where the first-run path is, and where the current repo is out of sync with itself.

## Summary Plan

The current repo is split into two working surfaces:

1. The backend is a FastAPI application in `backend/`. It owns configuration, run creation, background pipeline execution, local file storage, LLM calls, validation, metrics, benchmarks, and exports.
2. The frontend is a Vite React app in `frontend/`. It owns the visual operations console and reads backend-shaped JSON through one typed API client.
3. The real connection between them is HTTP. The frontend does not import backend code. It calls endpoints such as `/health`, `/runs`, `/samples`, `/failures`, `/metrics/live`, `/config/models`, `/config/prompts`, `/benchmarks`, and `/exports`.
4. The backend intentionally adapts its internal Python/Pydantic models into camelCase objects expected by the frontend. This adapter layer is essential to understand because stored backend files and frontend API responses do not use the same field names.
5. The backend pipeline can run a generation batch, especially in mock mode. The frontend currently displays backend data, but many write actions in the UI are not wired to POST/PATCH endpoints yet.
6. The biggest first-run risks are port mismatch, stale tests, and config/runtime drift after editing config without restarting the backend.

Useful immediate areas for future work:

- Backend: make config edits rebuild pipeline services or require an explicit restart warning; clean up task registry entries; align API tests with UI-shaped responses or add separate raw/backend response endpoints.
- Frontend: wire create/start/pause/resume/append/export/review actions to API mutations; fix the default backend port; remove hardcoded "mock mode" status text; make Settings reload or recompute the API client after the base URL changes.
- Integration: decide whether the frontend should target port 8000, 8003, or a configurable default, then make `.env`, `client.ts`, CORS, docs, and dev scripts agree.

## Current Runtime Shape

The backend starts in `backend/main.py`. On startup, FastAPI runs a lifespan function that builds almost all backend services once and attaches them to `app.state`.

The startup sequence is:

1. Load settings from `backend/.env` via `backend/app/core/settings.py`.
2. Resolve `DATA_DIR`. If it is relative, `main.py` treats it as relative to the backend folder.
3. Ensure local storage folders exist: `data/runs`, `data/configs`, and `data/exports`.
4. Load `backend/data/configs/dataset_config.yaml` through `ConfigStore`.
5. Create file-backed stores: `RunStore`, `SampleStore`, and `ExportStore`.
6. Recover stale runs that were left in `running` status by marking them `paused`.
7. Choose an LLM service:
   - `MockLLMService` when `MOCK_LLM=true`
   - `TokenRouterService` when `MOCK_LLM=false`
8. Build validators, generators, pipeline stages, runner, metrics tracker, and exporter.
9. Attach all of those instances to `app.state`.
10. Register the API routers.

The most important consequence: most backend services are constructed once at startup. If the YAML config is changed through `/config`, `ConfigStore` updates its cached config, but `SpecGenerator`, `TextGenerator`, `SemanticValidator`, `TokenRouterService`, and `SchemaValidator` still hold the config object they received during startup. Run creation may see the new config because it asks `ConfigStore`, but the actual pipeline services may keep using the old config until the backend restarts. This is one of the most important troubleshooting facts in the repo right now.

## Startup Commands And Ports

Backend startup is intended to happen from the `backend/` folder:

```powershell
.\dev.ps1
```

`backend/dev.ps1` reads `API_HOST` and `API_PORT` from `backend/.env`, maps them to Uvicorn's `UVICORN_HOST` and `UVICORN_PORT`, and runs:

```text
uvicorn main:app --reload
```

There is also a direct Python path in `backend/main.py`:

```text
python main.py
```

However, this machine did not have `python` or `py` available on PATH during inspection, and the bundled Codex Python did not have `pytest` installed.

The frontend starts from `frontend/`:

```powershell
npm.cmd run dev
```

The Vite dev server is configured in `frontend/vite.config.ts` to use port `8080`.

The current port story is inconsistent:

- `frontend/src/api/client.ts` defaults to `http://localhost:8000`.
- `backend/.env.example` says `API_PORT=8003`.
- `backend/app/core/settings.py` has a code default of `api_port=8001`.
- `frontend/vite.config.ts` serves the UI on `8080`.
- `backend/.env.example` CORS includes `http://localhost:3000` and `http://localhost:5173`, while the settings default also includes `http://localhost:8080`.

For a first run, either set the frontend API base URL to the actual backend URL, or make the backend listen on the frontend's default. The easiest path is usually:

1. Start the backend with `backend/dev.ps1`.
2. Confirm the printed backend port.
3. Open the frontend Settings screen and set the API base URL to that port.
4. Reload the frontend page after saving, because `API_BASE` is read once when `frontend/src/api/client.ts` is imported.

## Backend API Surface

Routers are registered in `backend/main.py`.

Implemented endpoint groups:

- `GET /health`
- `/config`
- `/runs`
- Global `/samples` and `/failures`
- Per-run `/runs/{run_id}/samples` and `/runs/{run_id}/failures`
- `/metrics`
- `/exports`
- `/benchmarks`

The backend has two naming layers:

- Internal models and files use snake_case, such as `run_id`, `samples_attempted`, and `model_ref`.
- Several API responses use frontend-friendly camelCase, such as `id`, `createdAt`, `targetCount`, and `generationModel`.

Examples:

- `Run.run_id` becomes `Run.id` in frontend responses.
- `Run.samples_attempted` becomes `attempted`.
- `Run.cost_usd_total` becomes `estCostUsd`.
- `Sample.generated_text` becomes `generatedText`.
- `Sample.model_metadata.prompt_ref` becomes `promptVersion`, although it is actually a prompt reference string, not just a numeric version.

This mapping is done in helper functions like `_to_ui_run()` in `backend/app/api/runs.py`, `_sample_to_ui()` in `backend/app/api/samples.py`, and `_manifest_to_ui()` in `backend/app/api/exports.py`.

## Health Endpoint

`GET /health` returns a small object intended for the frontend ping.

It includes:

- `ok`
- `ts`
- `status`
- `config_loaded`
- `tokenrouter_configured`
- `storage_writable`
- `mock_llm`
- `timestamp`

`tokenrouter_configured` is true if a real API key is present or mock mode is enabled. The backend never returns the API key.

One subtle issue: the health check uses `settings.data_dir` directly when checking storage writability, while lifespan resolves relative `DATA_DIR` to the backend folder. If the server is launched from an unusual working directory, the health storage check can point somewhere different from the actual runtime data directory.

## YAML Configuration

The active config file is `backend/data/configs/dataset_config.yaml`.

The config is loaded by `ConfigStore` and validated into `AppConfig` from `backend/app/models/config.py`.

Important config sections currently used by code:

- `measurement_phrases`: source phrases for generated specs.
- `units.allowed`: allowed units.
- `value_kinds.allowed`: allowed value kinds.
- `models`: model registry keyed by internal refs such as `cheap_fast`.
- `prompts`: prompt registry keyed by refs such as `generator_clean_v1`.
- `profiles`: runtime parameters like temperature, max tokens, retry count, timeout.
- `tasks`: task routing for generation, validation, mutation, and summarization.
- `validation`: text length limits.
- `generation`: default batch size and empty-output retry count.
- `export`: default export format.

The config validator checks that every task route references an existing model, prompt, and profile. It also requires `measurement_phrases` to be non-empty.

Config API behavior:

- `GET /config` returns parsed config as JSON.
- `GET /config/raw` returns raw YAML.
- `PUT /config` accepts raw YAML, validates it, backs up the previous file, and writes the new file.
- `POST /config/validate` validates raw YAML without saving it.
- `/config/models`, `/config/prompts`, `/config/profiles`, and `/config/task-routing` expose UI-shaped slices of the YAML.

Config backups are kept in the config folder as `dataset_config.yaml.bak.<timestamp>`, with only the five newest backups retained.

When a run is created, the current raw YAML is copied into the run folder as `config_snapshot.yaml`.

Critical limitation: a config snapshot may show newer values than the live generator/validator services actually use if config was edited after backend startup.

## Backend Data Storage

The backend uses local files rather than a database.

Storage paths are centralized in `backend/app/storage/paths.py`.

The main data directory is normally:

```text
backend/data/
```

Expected layout after runs and exports exist:

```text
backend/data/
  configs/
    dataset_config.yaml
    dataset_config.yaml.bak.<timestamp>
  runs/
    <run_id>/
      metadata.json
      config_snapshot.yaml
      samples.jsonl
      failures.jsonl
      events.jsonl
  exports/
    <export_id>.jsonl
    <export_id>.csv
    <export_id>_manifest.json
```

`RunStore` owns run metadata and events. It writes `metadata.json` atomically via a temp file replacement. It appends events as JSONL.

`SampleStore` owns samples and failures. It appends samples to `samples.jsonl` and failures to `failures.jsonl`. Updating a sample rewrites the samples file with the changed record.

`ExportStore` owns export manifests. `Exporter` writes the actual JSONL or CSV export files.

There is no database indexing. Listing samples and failures means reading JSONL files and filtering in Python. That is fine for small v0 runs, but it will become a performance constraint for large datasets.

## Run Lifecycle

Runs are first-class objects represented by `Run` in `backend/app/models/run.py`.

Backend statuses:

- `created`
- `running`
- `paused`
- `completed`
- `failed`
- `cancelled`

Frontend statuses:

- `queued`
- `running`
- `paused`
- `completed`
- `failed`

The API maps backend `created` to frontend `queued`, and backend `cancelled` to frontend `failed`.

Run creation:

1. `POST /runs` receives a `RunCreate` body.
2. The endpoint loads current config from `ConfigStore`.
3. It fills missing model/prompt/profile choices from `config.tasks.generation` and `config.tasks.validation`.
4. It generates a run id like `run_YYYYMMDD_HHMMSS_<six chars>`.
5. It writes `metadata.json`.
6. It snapshots YAML into the run folder.
7. It returns a frontend-shaped run object.

Run start:

1. `POST /runs/{run_id}/start` loads the run.
2. It only allows starting from `created` or `paused`.
3. It creates pause/cancel events in the in-process task registry.
4. It marks the run `running`.
5. It starts `PipelineRunner.execute_run()` as an asyncio background task.
6. It returns immediately.

Pause and cancel are cooperative:

- Pause sets an event. The pipeline notices between samples, then marks the run `paused`.
- Cancel sets an event. The pipeline notices between samples, then marks the run `cancelled`.
- If a run is paused or cancelled while an LLM call is already in progress, the call finishes first.

Resume:

- `POST /runs/{run_id}/resume` only accepts paused runs.
- It creates fresh events and starts the same execution method again.
- Resumability comes from processed spec ids in `samples.jsonl`.

Append:

- `POST /runs/{run_id}/append` only accepts completed, paused, or cancelled runs.
- It increments `target_count`.
- It immediately starts the pipeline again.
- Since specs are deterministic by target count and seed, old specs are skipped and only new spec ids are processed.

One small cleanup issue: `TaskRegistry` has a cleanup method, but the runner does not call it after completion. `is_running()` still returns false for completed tasks because it checks `task.done()`, but old registry entries can remain in memory until process restart.

## Pipeline Execution

The pipeline is built in `backend/main.py` from three stages:

1. `GenerationStage`
2. `SchemaValidationStage`
3. `SemanticValidationStage`

These stages are run by `PipelineExecutor`. The full run is orchestrated by `PipelineRunner`.

Per sample flow:

1. `SpecGenerator` creates a deterministic list of specs for the entire target count.
2. `SampleStore.get_processed_spec_ids()` reads already-written samples so resume/append can skip them.
3. For each remaining spec, the runner creates a `StageContext`.
4. `GenerationStage` calls `TextGenerator.generate()`.
5. `TextGenerator` builds a prompt from the generation prompt template and calls the selected LLM service with task `generation`.
6. The generation response becomes `generated_text`, `raw_llm_output`, and `model_metadata`.
7. Empty text causes a retry result. The executor retries up to `config.generation.max_retries_on_empty`.
8. `SchemaValidationStage` checks the text and the spec deterministically.
9. `SemanticValidationStage` calls the LLM service with task `validation`, parses JSON extraction, and compares it against the original spec.
10. The runner builds a `Sample`.
11. If validation failed, the runner also builds a `Failure`.
12. The sample is appended to `samples.jsonl`; the failure is appended to `failures.jsonl` if present.
13. Run counters are updated in `metadata.json`.
14. A `sample_completed` event is appended to `events.jsonl`.
15. When all specs are processed, the run becomes `completed`.

The pipeline is intentionally sample-by-sample. It is easy to inspect and resume, but not optimized for high throughput yet.

## Spec Generation

`SpecGenerator` in `backend/app/pipeline/spec_generator.py` does not use an LLM. It creates ground truth deterministically from config.

Inputs:

- target count
- run seed
- configured measurement phrases
- configured value kinds
- configured allowed units

For each item, it randomly selects phrase, kind, and unit from config using `random.Random(seed)`. It then generates values based on value kind:

- `exact` and `approx`: `value_nominal`
- `range` and `min_max`: `value_min` and `value_max`
- `tolerance`: `value_nominal` and `value_tolerance`
- `min_only`: `value_min`
- `max_only`: `value_max`

Each spec id is a 16-character SHA-256 prefix built from phrase, kind, unit, seed, and values. This makes resume and append possible because the same seed and same target prefix produce the same first specs.

The LLM never invents the truth. The LLM only renders the truth into text and later re-extracts it during validation.

## Text Generation And LLM Routing

`TextGenerator` in `backend/app/pipeline/text_generator.py` uses config task routing for `generation`.

It looks up:

- `config.tasks["generation"].model_ref`
- `config.tasks["generation"].prompt_ref`
- `config.tasks["generation"].profile_ref`

It formats the selected prompt template with fields from the spec:

- `measurement_phrase`
- `value_kind`
- `value_nominal`
- `value_min`
- `value_max`
- `value_tolerance`
- `unit_norm`

Then it calls:

```text
llm_service.complete(prompt, system, task="generation", run_id, sample_id)
```

The returned metadata records model ref, provider, prompt ref, prompt version, task, latency, token counts, and estimated cost if available.

There are two LLM implementations:

- `MockLLMService`: deterministic local fake used for tests and no-credit development.
- `TokenRouterService`: OpenAI-compatible HTTP client that posts to `<TOKENROUTER_BASE_URL>/chat/completions`.

`TokenRouterService` resolves task routing, builds chat messages, sends model/profile settings, retries transient failures, extracts `choices[0].message.content`, reads usage token counts, and estimates cost from a small hardcoded table for the configured default models.

The TokenRouter cost table is rough and only covers:

- `google/gemini-flash`
- `openai/gpt-4.1`
- `anthropic/claude-sonnet`

If model names change, cost may become `null`.

## Validation

There are two layers of validation.

Schema validation is deterministic and lives in `backend/app/validation/schema_validator.py`.

It checks:

- generated text is non-empty
- generated text length is within configured min/max
- generated text does not look like JSON or metadata leakage
- the spec has the required numeric fields for its value kind
- range min is less than max
- tolerance is positive
- unit is in the configured allowed list

Semantic validation is model-assisted and lives in `backend/app/validation/semantic_validator.py`.

It:

1. Builds a validation prompt using the configured validation prompt.
2. Calls the LLM service with task `validation`.
3. Attempts to parse JSON from the response.
4. Compares extracted measurement phrase, unit, and numeric values against the original spec.

Numeric comparison allows a 5 percent relative tolerance. That tolerance is currently a module constant, not a YAML setting.

Failure categories include:

- `schema_invalid`
- `semantic_mismatch`
- `wrong_value`
- `wrong_unit`
- `wrong_measurement_phrase`
- `missing_unit`
- `missing_value`
- `extra_measurement`
- `invalid_json`
- `rejected`
- `llm_error`
- `text_too_short`
- `text_too_long`
- `empty_output`

The frontend has a slightly different failure vocabulary. The API maps backend categories into frontend categories in `backend/app/api/samples.py`.

Example mappings:

- backend `wrong_unit` becomes frontend `missing_unit`
- backend `extra_measurement` becomes frontend `extra_measurement_added`
- backend `missing_value` becomes frontend `wrong_value`
- text length errors become frontend `schema_invalid`

This category translation matters when troubleshooting why a frontend label does not exactly match a stored failure record.

## Metrics And Benchmarks

Metrics are computed from stored files, not continuously held in memory.

`MetricsTracker.compute_run_metrics()` reads `samples.jsonl` and `failures.jsonl` for a run and calculates:

- attempted samples
- valid samples
- failed samples
- schema valid rate
- semantic match rate
- overall valid rate
- failure breakdown
- total cost
- cost per valid sample
- average latency
- model usage
- prompt usage
- total input/output tokens

`GET /runs/{run_id}/metrics` returns run metrics.

`GET /metrics/summary` aggregates across all runs or selected run ids.

`GET /metrics/live` picks the most relevant run, preferring running first, then paused, completed, failed, created, and cancelled. It returns the frontend `MetricsSnapshot` shape.

Current live metrics limitations:

- `stage` is always `text_generation`.
- `throughputPerMin` is always `0`.
- Recent failures are collected by scanning samples and choosing invalid ones, not by reading events.
- The active model is the validation model if present, otherwise the generation model.

`GET /benchmarks` groups existing runs by generation model ref and generation prompt ref. It aggregates counts, rates, cost, and latency into frontend benchmark rows. It does not run new benchmark jobs.

## Exports

Exports are created by `Exporter` in `backend/app/export/exporter.py`.

`POST /exports` receives:

- run ids
- format: `jsonl` or `csv`
- valid-only flag
- export-flagged-only flag
- optional filters for measurement phrase, value kind, model ref, prompt ref

The exporter streams matching samples from each run, writes a file in `backend/data/exports`, then writes a manifest.

JSONL records contain:

- sample id
- run id
- generated text
- truth object
- model ref
- prompt ref
- status
- created timestamp

CSV exports use equivalent flattened fields.

The backend only supports JSONL and CSV. The frontend UI offers Parquet and HuggingFace folder options, but those are not implemented by the backend.

Download is available through:

```text
GET /exports/{export_id}/download
```

## Frontend App Structure

The frontend is a React 18, Vite, TypeScript, shadcn/Radix-style app.

The app root is `frontend/src/App.tsx`.

It creates:

- a React Query client with 5 second stale time
- tooltip/toast providers
- a browser router
- a shared `AppShell`
- routes for each main screen

Routes:

- `/` redirects to `/runs`
- `/runs`
- `/monitor`
- `/samples`
- `/failures`
- `/config`
- `/benchmarks`
- `/exports`
- `/settings`
- `/api-status`
- `/help`

`frontend/src/components/layout/AppShell.tsx` renders the sidebar, sticky header, backend status, and current active run chip.

`frontend/src/components/layout/AppSidebar.tsx` defines navigation. It currently has hardcoded footer text saying `backend - localhost:8000` and `connected - mock mode`, even though the API client has `USE_MOCKS=false` and the base URL can be changed through local storage.

## Frontend API Client

All current frontend/backend calls go through `frontend/src/api/client.ts`.

Important constants:

```text
USE_MOCKS = false
API_BASE = localStorage["foundry.apiBase"] or "http://localhost:8000"
```

Because `API_BASE` is computed at module import time, changing the base URL in Settings does not immediately reconfigure already-imported API functions. Reloading the frontend after saving the setting is the safest path.

Current implemented client methods:

- `listRuns()` -> `GET /runs`
- `getRun(id)` -> `GET /runs/{id}`
- `listSamples()` -> `GET /samples`
- `listFailures()` -> `GET /failures`
- `getMetrics()` -> `GET /metrics/live`
- `listModels()` -> `GET /config/models`
- `listPrompts()` -> `GET /config/prompts`
- `listProfiles()` -> `GET /config/profiles`
- `listBenchmarks()` -> `GET /benchmarks`
- `listExports()` -> `GET /exports`
- `ping()` -> `GET /health`

There are no frontend API methods yet for:

- creating a run
- starting a run
- pausing a run
- resuming a run
- cancelling a run
- appending samples
- updating review tags/notes/export flags
- creating exports
- downloading exports
- editing config
- activating or duplicating prompts
- changing models or task routing

The backend has many of those endpoints already, but the frontend write actions are mostly visual placeholders.

## Frontend Types And API Contract

Frontend types live in `frontend/src/types/index.ts`.

These types define the exact JSON shapes the UI expects:

- `Run`
- `Sample`
- `FailureBucket`
- `MetricsSnapshot`
- `ModelDef`
- `PromptDef`
- `TaskProfile`
- `BenchmarkRow`
- `ExportRecord`

The backend has been partially adapted to match these types. When adding new API methods, keep using these frontend types or update both sides at the same time.

Important frontend expectations:

- Run id is `id`, not `run_id`.
- Sample run id is `runId`.
- Generated text is `generatedText`.
- Expected truth is nested under `expectedTruth`.
- Failure buckets are aggregated, not raw failure rows.
- Metrics use rate values from 0 to 1, not percentages from 0 to 100.
- Benchmark percentages are 0 to 100 integer-ish values.
- Export format is uppercase in the UI.

## Frontend Screens

### Runs

`frontend/src/pages/Runs.tsx` fetches `api.listRuns()`.

It displays:

- header summary counts
- run cards
- active run moving border
- run stats
- generation model, validation model, prompts, cost, and config snapshot

Current limitation: the Create New Run dialog only closes locally. It does not call `POST /runs`. Dropdown actions for Resume, Pause, Append, Compare, and Export are present visually but do not call the backend.

### Live Monitor

`frontend/src/pages/Monitor.tsx` fetches:

- `api.getMetrics()` every 2 seconds
- `api.listRuns()`

It displays:

- current run
- current stage
- active model
- throughput
- pipeline stepper
- metric cards
- recent failures

Current backend limitation: live stage is always `text_generation`, and throughput is always zero.

### Samples

`frontend/src/pages/Samples.tsx` fetches:

- `api.listSamples()`
- `api.listRuns()`

Filtering is client-side over the fetched sample array. The backend supports some per-run filters, but the global `/samples` client method currently fetches a broad list and filters in React.

The page shows:

- sample table
- selected sample inspector
- expected truth
- generated text
- validator output
- raw model output
- metadata
- review buttons and notes textarea

Current limitation: review buttons, include/exclude actions, and notes do not call `PATCH /runs/{run_id}/samples/{sample_id}` yet.

### Failure Review

`frontend/src/pages/Failures.tsx` fetches:

- `api.listFailures()`
- `api.listRuns()`

The backend global `/failures` endpoint returns aggregated failure buckets, not raw failure rows. It includes counts, affected models, affected prompts, example sample ids, and hints.

Current limitation: the run/model filters on the page are local UI state but are not applied to API calls or filtering logic yet.

### Config Studio

`frontend/src/pages/ConfigStudio.tsx` fetches:

- `api.listModels()`
- `api.listPrompts()`
- `api.listProfiles()`

It uses backend data for model cards, prompt cards, and profiles. However, task routing and validation rules still come from mock fixtures.

Current limitation: toggles, switches, duplicate, edit, archive, domain setting switches, and validation rule switches do not save to the backend. Model selection state is also initialized from mock fixture models, not from the fetched backend model list.

### Benchmarks

`frontend/src/pages/Benchmarks.tsx` fetches `api.listBenchmarks()`.

Sorting and pinning are client-side. Export CSV downloads the visible benchmark rows from the browser, not through the backend.

### Exports

`frontend/src/pages/Exports.tsx` fetches:

- runs
- samples
- export history

It builds a client-side preview count. The Trigger Export button does not call `POST /exports` yet. Download buttons do not call `/exports/{id}/download` yet.

The frontend format picker includes JSONL, CSV, Parquet, and HuggingFace folder layout. The backend currently supports only JSONL and CSV.

### Settings

`frontend/src/pages/Settings.tsx` saves `foundry.apiBase` into local storage.

Current limitation: because `API_BASE` is read once at import time, the user should reload after saving. The helper text says mock mode is on until disabled in code, but `USE_MOCKS` is currently false.

### API Status

`frontend/src/pages/ApiStatus.tsx` pings `/health` every 5 seconds.

It shows a static endpoint checklist. The checklist does not test each listed endpoint; it marks all as ok when ping succeeds.

## Current Frontend-Backend Connection Map

These are the connections that are actually wired:

```text
Frontend AppShell header
  -> api.ping()
  -> GET /health

Frontend AppShell active run chip
  -> api.listRuns()
  -> GET /runs

Runs page
  -> api.listRuns()
  -> GET /runs

Monitor page
  -> api.getMetrics()
  -> GET /metrics/live
  -> api.listRuns()
  -> GET /runs

Samples page
  -> api.listSamples()
  -> GET /samples
  -> api.listRuns()
  -> GET /runs

Failure Review page
  -> api.listFailures()
  -> GET /failures
  -> api.listRuns()
  -> GET /runs

Config Studio page
  -> api.listModels()
  -> GET /config/models
  -> api.listPrompts()
  -> GET /config/prompts
  -> api.listProfiles()
  -> GET /config/profiles

Benchmarks page
  -> api.listBenchmarks()
  -> GET /benchmarks

Exports page
  -> api.listExports()
  -> GET /exports
  -> api.listRuns()
  -> GET /runs
  -> api.listSamples()
  -> GET /samples

API Status page
  -> api.ping()
  -> GET /health
```

Backend endpoints implemented but not currently wired from frontend:

```text
POST /runs
POST /runs/{run_id}/start
POST /runs/{run_id}/pause
POST /runs/{run_id}/resume
POST /runs/{run_id}/cancel
POST /runs/{run_id}/append
GET  /runs/{run_id}
GET  /runs/{run_id}/metrics
GET  /runs/{run_id}/events
GET  /runs/{run_id}/samples
GET  /runs/{run_id}/samples/{sample_id}
PATCH /runs/{run_id}/samples/{sample_id}
GET  /runs/{run_id}/failures
GET  /runs/{run_id}/failures/{failure_id}
GET  /config/raw
PUT  /config
POST /config/validate
PATCH /config/models/{ref}
POST /config/prompts/{ref}/activate
POST /config/prompts/{ref}/deactivate
POST /config/prompts/{ref}/duplicate
PATCH /config/prompts/{ref}
GET  /config/task-routing
PATCH /config/task-routing/{task}
POST /exports
GET  /exports/{export_id}
GET  /exports/{export_id}/download
GET  /metrics/summary
GET  /metrics/benchmark
```

## First Run Walkthrough For A Copilot

This is the practical first-run mental model.

1. Decide whether to use real TokenRouter or mock LLM.
   - For safe local smoke tests, use `MOCK_LLM=true`.
   - For real generation, set `MOCK_LLM=false` and provide `TOKENROUTER_API_KEY`.
2. Start the backend from `backend/`.
   - Use `.\dev.ps1` on Windows PowerShell.
   - Watch the printed host/port.
3. Check backend health in a browser:
   - `http://localhost:<port>/health`
   - `http://localhost:<port>/docs`
4. Start the frontend from `frontend/`.
   - Use `npm.cmd run dev` in PowerShell if `npm` is blocked by execution policy.
   - Open the Vite URL, likely `http://localhost:8080`.
5. In frontend Settings, set the API base to the backend URL.
6. Reload the frontend.
7. Confirm API Status says the backend is reachable.
8. Because the frontend Create Run button is not wired, create and start a run through API docs or a REST client for now.
9. After the run starts, the frontend Runs, Monitor, Samples, Failures, Benchmarks, and Exports pages can read the stored backend state.

Example backend flow through API docs:

1. `POST /runs` with a small target count, such as 3 or 5.
2. Copy the returned `id` from the response. If using old tests or raw internal expectations, be aware the current API returns frontend-shaped `id`, not `run_id`.
3. `POST /runs/{id}/start`.
4. Poll `GET /runs/{id}` until status becomes `completed`, `failed`, or `paused`.
5. Inspect `GET /runs/{id}/samples`.
6. Inspect `GET /runs/{id}/metrics`.
7. Create an export with `POST /exports`.

## Known Mismatches And Troubleshooting Notes

The codebase is newly created and has some expected rough edges. These are the important ones.

### Port mismatch

The frontend defaults to `http://localhost:8000`, but the backend example env uses `8003` and code default uses `8001`. Align these before debugging CORS or fetch errors.

### Frontend write actions are mostly not wired

The UI looks like it can create, start, pause, append, review, and export, but those buttons currently do not call mutation endpoints. Use FastAPI docs or direct HTTP calls for write operations until the API client is extended.

### API tests appear stale

The tests in `tests/test_api.py` expect older snake_case backend responses such as `run_id`, `target_count`, and `samples_attempted`. The current API returns UI-shaped fields like `id`, `targetCount`, and `attempted` from several endpoints.

That means tests may fail even if the current frontend-oriented API is working as implemented. Either update tests to match UI-shaped responses, or add raw internal endpoints and keep tests against those.

### Test tooling was not runnable in this environment

During inspection:

- `python` was not found on PATH.
- `py` was not found on PATH.
- The bundled Python existed but did not have `pytest` installed.
- `npm` was blocked by PowerShell script execution policy.
- `npm.cmd test -- --run` launched but failed with `spawn EPERM` from esbuild while loading Vitest config.

So no reliable test pass/fail result was obtained from this environment.

### Config edits may not affect live pipeline until restart

This is the highest-impact backend behavior. Config API endpoints can save new YAML, and run creation can snapshot it, but the pipeline services were constructed with the startup config. Restart the backend after changing models, prompts, profiles, units, value kinds, validation lengths, or generation settings if you want pipeline behavior to definitely match the new config.

### Mock mode text is inconsistent

The frontend says mock mode in some UI text, but `USE_MOCKS=false` in `client.ts`. The backend can also independently run in mock or real TokenRouter mode. Treat frontend mock mode and backend mock LLM mode as separate concepts.

### Backend global samples endpoint has limited filtering

The frontend global Samples page fetches `/samples`, which returns samples across runs with optional run/status support. Most filtering is done client-side. For larger datasets, prefer per-run endpoints and server-side filters.

### Live monitor stage is not truly live yet

The backend does not emit current stage state into metrics. `/metrics/live` always returns `text_generation`. Events are stored, but the live endpoint does not derive stage from them.

### Export UI offers formats the backend cannot create

Backend supports JSONL and CSV only. Parquet and HuggingFace layout are frontend placeholders.

### Current local storage is append-oriented

Samples and failures are JSONL append files. This is transparent and reliable for v0, but there is no locking or database transaction layer. Avoid running multiple backend processes against the same `backend/data` folder.

### TokenRouter model names may need verification

The YAML model names came from project assumptions. If real TokenRouter calls fail with client errors, verify current TokenRouter model identifiers and update `dataset_config.yaml`.

## Good Mental Model For Debugging

When troubleshooting, follow the path of one sample:

```text
Run metadata
  -> deterministic spec
  -> generation prompt
  -> generation LLM call
  -> generated text
  -> schema validation
  -> validation prompt
  -> validation LLM call
  -> parsed extraction
  -> comparison against original spec
  -> sample or failure JSONL row
  -> metrics computed from stored rows
  -> frontend API adapter
  -> React page display
```

If a value looks wrong in the UI, ask these questions in order:

1. Is the backend using the config you think it is using, or does it need a restart?
2. Does the run's `metadata.json` have the expected model/prompt/profile refs?
3. Does the run's `config_snapshot.yaml` contain the expected settings?
4. Does `samples.jsonl` contain the raw generated text and model metadata?
5. Does `failures.jsonl` contain a more precise backend failure category?
6. Is the API adapter translating or simplifying the field/category?
7. Is the frontend doing additional client-side filtering or display transformation?

## Important Files By Responsibility

Backend startup and settings:

- `backend/main.py`
- `backend/dev.ps1`
- `backend/app/core/settings.py`
- `backend/app/core/exceptions.py`
- `backend/app/core/logging_config.py`

Backend API:

- `backend/app/api/health.py`
- `backend/app/api/config.py`
- `backend/app/api/runs.py`
- `backend/app/api/samples.py`
- `backend/app/api/metrics.py`
- `backend/app/api/benchmarks.py`
- `backend/app/api/exports.py`

Backend models:

- `backend/app/models/config.py`
- `backend/app/models/run.py`
- `backend/app/models/spec.py`
- `backend/app/models/sample.py`
- `backend/app/models/failure.py`
- `backend/app/models/metrics.py`
- `backend/app/models/export.py`
- `backend/app/models/llm.py`

Backend pipeline:

- `backend/app/pipeline/spec_generator.py`
- `backend/app/pipeline/text_generator.py`
- `backend/app/pipeline/stages.py`
- `backend/app/pipeline/executor.py`
- `backend/app/pipeline/runner.py`
- `backend/app/pipeline/task_registry.py`

Backend LLM and validation:

- `backend/app/services/base.py`
- `backend/app/services/mock_llm.py`
- `backend/app/services/tokenrouter.py`
- `backend/app/validation/schema_validator.py`
- `backend/app/validation/semantic_validator.py`

Backend storage, metrics, exports:

- `backend/app/storage/paths.py`
- `backend/app/storage/config_store.py`
- `backend/app/storage/run_store.py`
- `backend/app/storage/sample_store.py`
- `backend/app/storage/export_store.py`
- `backend/app/metrics/tracker.py`
- `backend/app/export/exporter.py`

Frontend API, types, and app shell:

- `frontend/src/api/client.ts`
- `frontend/src/types/index.ts`
- `frontend/src/App.tsx`
- `frontend/src/components/layout/AppShell.tsx`
- `frontend/src/components/layout/AppSidebar.tsx`

Frontend pages:

- `frontend/src/pages/Runs.tsx`
- `frontend/src/pages/Monitor.tsx`
- `frontend/src/pages/Samples.tsx`
- `frontend/src/pages/Failures.tsx`
- `frontend/src/pages/ConfigStudio.tsx`
- `frontend/src/pages/Benchmarks.tsx`
- `frontend/src/pages/Exports.tsx`
- `frontend/src/pages/Settings.tsx`
- `frontend/src/pages/ApiStatus.tsx`

Config and fixtures:

- `backend/data/configs/dataset_config.yaml`
- `backend/tests/fixtures/test_config.yaml`
- `frontend/src/api/mocks/fixtures.ts`

## Suggested Next Implementation Steps

The most useful next development pass would be integration-focused rather than adding new screens.

1. Pick a single default backend port and update backend env example, frontend API default, CORS, sidebar text, and docs.
2. Add frontend API client methods for run creation, start, pause, resume, append, sample update, export creation, and export download.
3. Wire Runs page actions to React Query mutations.
4. Wire Samples review actions to `PATCH /runs/{run_id}/samples/{sample_id}`.
5. Wire Exports Trigger Export and Download buttons.
6. Make Settings update the API client without requiring a reload, or explicitly force a reload after save.
7. Fix Config Studio to use real task routing and validation rules instead of fixtures.
8. Decide how backend should handle config changes: rebuild services after save, or require restart and expose that requirement in health/config responses.
9. Update tests to match current API responses.
10. Add a small "first run" smoke script or documented API-docs workflow using `MOCK_LLM=true`.

