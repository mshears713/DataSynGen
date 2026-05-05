# Backend PRD — Measurement Dataset Foundry v0

## 1. Product Summary

Build the backend for a UI-driven synthetic dataset generation tool. The backend will power a local frontend dashboard that allows the user to create, run, resume, inspect, validate, benchmark, and export synthetic text datasets.

The first domain is measurement extraction. The backend should generate text samples from structured measurement truth specs, validate those samples, persist run artifacts, expose status/results through an API, and support human-guided iteration through YAML-backed configuration.

This is not a CLI-first tool. CLI utilities may exist for debugging, but the primary user workflow is through a frontend interface calling backend API endpoints.

This PRD covers the backend only.

---

## 2. Primary Objective

Create a FastAPI backend that can:

1. Load and manage YAML-backed dataset configuration.
2. Create resumable dataset generation runs.
3. Generate measurement specs.
4. Use TokenRouter for LLM calls.
5. Generate natural-language text samples.
6. Validate generated samples structurally and semantically.
7. Persist valid samples, failed samples, run metadata, metrics, and config snapshots.
8. Expose clean API endpoints for a Lovable-generated frontend.
9. Export clean datasets as JSONL and CSV.
10. Support future integration with Bespoke Curator, audio generation, and Edge Impulse without requiring a rewrite.

---

## 3. Key Design Principles

### 3.1 UI-First Backend

The backend must assume a frontend will drive most workflows.

Avoid requiring terminal commands for normal use cases such as:

- creating a run
- starting generation
- pausing or resuming
- inspecting samples
- viewing failures
- editing config
- exporting datasets

### 3.2 Modular Pipeline

The backend should separate concerns clearly:

- API layer
- configuration layer
- run management
- storage
- LLM service
- generation pipeline
- validation pipeline
- metrics
- export

Each component should be replaceable without breaking the whole system.

### 3.3 Local-First v0

For v0, use local file storage rather than a database.

The system should still be structured in a way that allows Postgres or another database later.

### 3.4 YAML as Human-Control Layer

YAML should remain the editable source of truth for:

- models
- prompts
- task profiles
- measurement phrases
- validation rules
- generation behavior
- export settings

The backend should expose safe endpoints for reading and updating config.

### 3.5 TokenRouter First

All LLM calls should go through a TokenRouter service abstraction.

Do not hardcode provider-specific calls throughout the codebase.

### 3.6 Traceability

Every sample must be traceable to:

- run ID
- config snapshot
- prompt reference
- model reference
- task profile
- LLM response metadata
- validation result
- timestamp

### 3.7 Human-Guided Feedback

The backend should surface failure patterns and metrics, but it should not autonomously rewrite prompts, schemas, or system instructions in v0.

---

## 4. Important Implementation Note: Research Bespoke Curator First

Before implementing the pipeline from scratch, Claude Code should research the current Bespoke Curator repository and documentation.

The implementation should determine whether Curator can be used directly or partially for:

- structured LLM generation
- batch processing
- caching
- automatic recovery
- resumable generation
- dataset viewers or inspection utilities
- prompt/result traceability
- JSON/structured outputs
- Hugging Face dataset support
- request metadata tracking

The backend should not force Curator if integration creates too much complexity for v0.

Recommended approach:

1. Research Curator’s current API and best practices.
2. Identify which features are stable and useful.
3. Use Curator where it clearly reduces custom implementation.
4. Wrap Curator behind internal service interfaces so it can be replaced later.
5. Do not let Curator-specific concepts leak heavily into frontend API contracts.

If Curator integration is uncertain, implement a simple internal pipeline first while keeping the architecture compatible with Curator later.

---

## 5. User Workflow

The expected user workflow is:

1. Open frontend dashboard.
2. Review or edit YAML-backed config through UI.
3. Select active model/prompt/task profile cards.
4. Create a new run or resume an existing run.
5. Start a small generation batch.
6. Watch run progress and metrics.
7. Inspect generated samples and failures.
8. Adjust prompt/model/config if needed.
9. Run another batch.
10. Compare runs.
11. Export valid samples.

The backend should support this workflow end-to-end.

---

## 6. Core Backend Modules

### 6.1 API Module

Responsible for HTTP endpoints consumed by the frontend.

Should expose endpoints for:

- health checks
- config read/update
- run creation
- run start/pause/resume
- run details
- sample listing
- failure listing
- metrics retrieval
- prompt/model selections
- export generation
- benchmark results

### 6.2 Config Module

Responsible for loading, validating, snapshotting, and updating YAML config.

Requirements:

- load active config from local file
- validate structure before use
- expose config to frontend
- support saving edits from frontend
- preserve backups or version history when config changes
- snapshot config into each run folder at run creation
- never allow a running run to mutate its own config snapshot unexpectedly

### 6.3 Run Manager

Responsible for run lifecycle.

Run states should include at least:

- created
- running
- paused
- completed
- failed
- cancelled

The run manager should support:

- create run
- start run
- pause run
- resume run
- append additional batch to previous run
- inspect run status
- recover from partial/incomplete runs

### 6.4 Storage Module

Responsible for local persistence.

Storage should be append-friendly and restart-safe.

Recommended storage artifacts per run:

- run metadata
- config snapshot
- samples
- failures
- metrics
- events or logs
- export manifests

For v0, JSON and JSONL files are acceptable.

Design for future database migration by centralizing all persistence operations.

### 6.5 TokenRouter LLM Service

Responsible for all model calls.

Requirements:

- read model references from config
- resolve task-specific model/profile/prompt
- call TokenRouter API
- handle retries and errors
- normalize responses into internal format
- track model, provider, latency, token estimates, and cost estimates when available
- never expose API keys to frontend

Environment variables should be used for secrets.

### 6.6 Spec Generator

Responsible for creating structured truth specs.

This may be deterministic or partially randomized based on config.

The spec generator should produce measurement extraction truth objects such as:

- measurement phrase
- value kind
- nominal value
- min value
- max value
- tolerance
- normalized unit
- tags
- seed
- spec ID

The LLM should not invent truth. Truth should be generated by deterministic code or explicit configured rules.

### 6.7 Text Generator

Responsible for rendering structured truth specs into natural-language utterances.

Requirements:

- use configured generator prompt
- use configured generation model
- produce one or more candidate utterances
- preserve truth exactly
- avoid inventing additional measurements
- store raw model response
- store cleaned/generated text separately if cleanup is performed

### 6.8 Schema Validator

Responsible for deterministic validation.

Checks should include:

- required fields exist
- value kind is allowed
- numeric fields match value kind rules
- unit is allowed
- generated text is non-empty
- generated text does not contain obvious metadata leakage
- generated text does not exceed configured length limits, if configured

### 6.9 Semantic Validator

Responsible for model-based validation.

The validator model should re-extract structured meaning from the generated text and compare it against the original truth spec.

It should identify failure categories such as:

- wrong value
- wrong unit
- wrong measurement phrase
- missing unit
- missing value
- extra measurement
- invalid extraction
- ambiguous output
- validator failure

### 6.10 Metrics Module

Responsible for summarizing run quality.

Track:

- samples attempted
- valid samples
- failed samples
- schema valid rate
- semantic match rate
- failure breakdown
- cost estimate
- cost per valid sample
- model usage
- prompt usage
- latency
- throughput

### 6.11 Export Module

Responsible for producing clean dataset artifacts.

Initial exports:

- JSONL
- CSV

Export filters should include:

- run ID
- valid only
- reviewed only
- prompt version
- model
- value kind
- measurement phrase
- unit

---

## 7. Data Concepts

### 7.1 Measurement Definition

Represents an opaque measurement phrase.

Examples:

- outer diameter
- inner diameter
- overall length
- thickness
- depth

Do not merge aliases automatically in v0.

### 7.2 Generation Spec

Represents the structured truth to be expressed by a generated sample.

The generation spec is authoritative.

### 7.3 Sample

Represents one generated text utterance and all associated metadata.

A sample should include:

- sample ID
- run ID
- generation spec ID
- generated text
- raw model output
- status
- validation results
- model metadata
- prompt metadata
- timestamps
- review tags or notes

### 7.4 Failure

A failed sample should be stored, not discarded.

A failure should include:

- failure ID
- sample ID if available
- run ID
- failure category
- failure details
- original truth
- generated text if available
- validator output if available
- raw error if relevant
- timestamp

### 7.5 Run

A run is a first-class object.

A run should include:

- run ID
- status
- created timestamp
- updated timestamp
- config snapshot path
- sample target or batch size
- current counts
- selected prompt/model/task profile references
- cost metrics
- notes

---

## 8. YAML Configuration Requirements

The backend should support a primary YAML config file.

The config should include these major sections:

- project metadata
- measurement phrases
- units
- value kinds
- prompts
- models
- task profiles
- task routing
- validation rules
- generation settings
- export settings

### 8.1 Models

Model entries should include:

- internal model ref
- provider
- model name
- notes
- enabled flag
- task compatibility if useful

The YAML may contain commented candidate models for future experimentation.

### 8.2 Prompts

Prompt entries should include:

- prompt ref
- task type
- title
- description
- active flag
- version
- prompt text
- notes

Prompt versions should be duplicated rather than overwritten casually.

### 8.3 Task Routing

Task routing should define which model, prompt, and profile each task uses.

Tasks should include at least:

- generation
- validation
- mutation
- summarization

Mutation and summarization may be implemented later but should be represented cleanly.

### 8.4 Task Profiles

Task profiles should include:

- temperature
- max tokens
- retry count
- timeout
- optional strictness/diversity hints

### 8.5 Config Safety

When the frontend edits config:

- validate before saving
- create backup or versioned copy
- return useful error messages
- do not corrupt current config
- do not mutate active run snapshots

---

## 9. API Requirements

Exact endpoint names may change, but the backend must expose capabilities in the following groups.

### 9.1 Health

The frontend should be able to check whether the backend is running and whether required configuration/secrets are available.

Health output should include:

- backend status
- config loaded status
- TokenRouter configured status
- storage writable status

Do not expose secret values.

### 9.2 Config Endpoints

Capabilities:

- get active config
- update active config
- validate proposed config
- list prompt cards
- update prompt active state
- duplicate prompt
- archive prompt
- list model cards
- update active model selection
- list task profiles
- update task routing

### 9.3 Run Endpoints

Capabilities:

- create run
- start run
- pause run
- resume run
- cancel run
- append batch to existing run
- list runs
- get run details
- get run metrics
- get run events

### 9.4 Sample Endpoints

Capabilities:

- list samples
- filter samples
- get sample detail
- update review status
- add note
- include/exclude from export
- list failures
- get failure detail

### 9.5 Benchmark Endpoints

Capabilities:

- list benchmark summaries
- compare model/prompt runs
- compare costs and quality metrics

This can be minimal in v0 but should be planned cleanly.

### 9.6 Export Endpoints

Capabilities:

- create export
- list exports
- download export
- filter export by selected criteria

---

## 10. Run Execution Behavior

### 10.1 Initial Execution Model

For v0, simple background execution is acceptable.

Options include:

- FastAPI background tasks
- a lightweight local worker
- process/thread-based worker

Do not overbuild with Celery or distributed queues unless necessary.

### 10.2 Pausing

Pause behavior may be cooperative.

The backend should finish the current in-flight sample or batch, then mark the run paused.

### 10.3 Resuming

Resume should continue from the last persisted state.

The system should not duplicate valid samples silently.

### 10.4 Appending

The user should be able to add more samples to a previous run or create a new run based on a previous run’s config.

Both workflows are useful.

### 10.5 Failure Handling

Failures must be persisted with useful reason codes.

The run should not crash entirely because one sample fails validation.

LLM API failures should be retried according to task profile settings, then recorded if still failing.

---

## 11. Feedback Loop Requirements

The backend should produce actionable feedback.

Actionable feedback means:

- clear failure categories
- representative examples
- counts by failure type
- affected prompt/model
- affected measurement phrase/value kind
- suggested area to inspect

The backend should not automatically edit prompts in v0.

However, it should produce summaries that are easy for the user to paste into ChatGPT or another agent for guidance.

Recommended feedback outputs:

- failure summary
- top recurring mismatch patterns
- sample examples per category
- model/prompt quality comparison
- cost-quality tradeoff summary

---

## 12. Benchmarking Requirements

Benchmarking should be possible without complex setup.

Minimum v0 support:

- compare runs by model
- compare runs by prompt
- compare valid rate
- compare semantic match rate
- compare failure breakdown
- compare estimated cost
- compare throughput

The backend should store enough metadata to make benchmarking possible later, even if the first UI view is simple.

Avoid hidden auto-routing in early phases because it makes benchmark results harder to interpret.

---

## 13. TokenRouter Requirements

Claude Code must research TokenRouter API usage before implementing.

The backend should support:

- API key from environment variable
- model name from YAML
- request timeout
- retry handling
- structured response handling where supported
- cost/token metadata if returned
- clear error reporting

The TokenRouter service should be isolated so it can be replaced with another provider abstraction later.

No frontend endpoint should ever expose the TokenRouter key.

---

## 14. Validation Rules for Measurement Domain

Initial value kinds:

- exact
- approx
- range
- tolerance
- min_only
- max_only
- min_max

Rules:

- exact and approx require nominal value
- range requires min and max
- tolerance requires nominal and tolerance
- min_only requires min
- max_only requires max
- min_max requires min and max

Initial units:

- mm
- cm
- in

Initial measurement phrases:

- outer diameter
- inner diameter
- overall length
- width
- height
- thickness
- depth
- hole diameter
- slot width
- flange thickness
- radius
- wall thickness

These should be configurable and not hardcoded deeply.

---

## 15. Frontend Integration Expectations

The frontend will likely be generated in Lovable and may live in a separate repo.

The backend should therefore provide:

- CORS support for local frontend development
- predictable JSON responses
- clear error messages
- endpoint documentation through FastAPI OpenAPI docs
- stable API contracts
- simple local startup process

The frontend should not need to know storage internals.

---

## 16. Error Handling

Errors should be structured and useful.

Error responses should include:

- error type
- user-readable message
- technical detail when safe
- suggested next action when possible

Avoid vague errors such as “failed” without context.

Log details server-side.

---

## 17. Security and Secrets

Secrets must be loaded from environment variables.

Required:

- TokenRouter API key

Optional later:

- provider-specific keys
- database URL
- object storage credentials

Do not store secrets in YAML config or run snapshots.

Do not return secrets through API endpoints.

---

## 18. Testing Requirements

Claude Code should implement phase-level testing.

Recommended tests:

### Config Tests

- valid config loads
- invalid config is rejected
- config backup/versioning works
- task routing references valid model/prompt/profile refs

### Storage Tests

- run folder is created
- metadata is persisted
- samples append correctly
- failures append correctly
- metrics update correctly
- interrupted run can be resumed

### Validation Tests

- value_kind rules enforced
- invalid units rejected
- wrong numeric fields rejected
- semantic comparison catches mismatches

### API Tests

- health endpoint works
- config endpoints work
- run lifecycle endpoints work
- sample listing/filtering works
- export creation works

### TokenRouter Service Tests

- mock calls succeed
- failed calls retry
- metadata is captured
- no secrets leak in responses

### End-to-End Smoke Test

A small run should be able to:

1. create a run
2. generate a few specs
3. generate samples using mocked LLM responses
4. validate samples
5. store results
6. return metrics
7. export valid samples

Use mocked LLM responses for tests by default so tests do not burn credits.

---

## 19. Development Phases

### Phase 1 — Backend Skeleton and Config

Deliverables:

- FastAPI app
- health endpoint
- YAML config loader
- config validation
- local storage structure
- basic run metadata creation

Exit criteria:

- backend starts locally
- config loads successfully
- frontend can call health/config endpoints

### Phase 2 — Run Lifecycle and Storage

Deliverables:

- create run
- list runs
- get run details
- local run folders
- config snapshots
- sample/failure storage interfaces

Exit criteria:

- runs can be created and inspected
- storage artifacts persist correctly

### Phase 3 — TokenRouter Service and Generation

Deliverables:

- TokenRouter service abstraction
- task routing
- prompt/model/profile resolution
- basic text generation
- metadata logging

Exit criteria:

- backend can generate sample text through TokenRouter or mocked provider
- no model names are hardcoded in pipeline logic

### Phase 4 — Validation and Feedback

Deliverables:

- schema validation
- semantic validation
- failure categories
- metrics summaries
- failure review endpoints

Exit criteria:

- valid and invalid samples are separated
- failure summaries are available to frontend

### Phase 5 — Resumability, Export, and Benchmarking

Deliverables:

- pause/resume support
- append batch support
- JSONL/CSV export
- basic run comparison metrics

Exit criteria:

- interrupted runs can resume
- valid samples can be exported
- runs can be compared by model/prompt metadata

---

## 20. Acceptance Criteria

The backend is successful when:

- It can be started locally.
- It exposes API docs.
- It can load YAML config.
- It can create and resume runs.
- It can call TokenRouter through a centralized service.
- It can generate text samples from structured specs.
- It can validate samples and store failures.
- It logs model/prompt/run metadata.
- It returns useful metrics to a frontend.
- It exports valid samples.
- It supports mocked LLM responses for testing.
- It does not require CLI interaction for normal workflows.

---

## 21. Notes for Claude Code

Use the README as the product vision and this PRD as the backend implementation guide.

Important implementation guidance:

- Do not build the frontend in this backend PRD.
- Do not add audio features yet.
- Do not implement Edge Impulse integration yet.
- Do not build an overcomplicated agent system.
- Do not make the project CLI-first.
- Keep config human-readable and UI-editable.
- Keep TokenRouter calls isolated.
- Make storage boring and reliable.
- Use mocks so tests do not spend LLM credits.
- Make every run inspectable.
- Make failures visible, not hidden.
- Prefer clear modules over clever abstractions.
- Research Bespoke Curator and TokenRouter before implementation.
- If a library integration is unstable or unclear, wrap it or defer it rather than blocking the core v0 pipeline.

The core v0 loop is:

Create run → generate specs → generate text → validate → store → summarize → inspect → export.

Everything else should support that loop.
