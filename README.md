# Measurement Dataset Foundry

A modular, UI-driven synthetic dataset generation tool for structured measurement extraction.

This project is designed to generate, validate, inspect, mutate, benchmark, and export synthetic text datasets for narrow extraction tasks. The first target domain is spoken-style measurement extraction for an embedded measurement device, but the tool should be modular enough to reuse for other structured dataset generation workflows later.

The first version is text-only. Audio generation, audio augmentation, Edge Impulse integration, and embedded deployment are intentionally deferred.

---

## 1. Project Purpose

The immediate goal is to build a working dataset generation system that can take structured measurement specs and produce high-quality natural-language examples with strict ground-truth labels.

Example target behavior:

```text
Input truth:
outer diameter = 65 mm

Generated utterance:
"Outer diameter is sixty five millimeters."

Expected structured output:
{
  "measurement_phrase": "outer diameter",
  "value_kind": "exact",
  "value_nominal": 65,
  "unit_norm": "mm"
}
```

The tool should not merely generate data. It should help operate the dataset generation process:

- start and resume generation runs
- inspect generated samples
- compare expected vs generated vs validated outputs
- identify failure patterns
- test different prompts and models
- track cost and quality
- export clean datasets

Think of this as a **synthetic dataset control center**, not a CLI script.

---

## 2. Current Scope

### In Scope for v0

- Text-only synthetic dataset generation
- Structured measurement specs
- YAML-backed configuration
- TokenRouter-based LLM calls
- Per-task model selection
- Prompt template management
- Feedback and validation loop
- Resumable runs
- Incremental dataset expansion
- Run metrics and cost tracking
- UI dashboard for control and inspection
- Export to JSONL / CSV

### Out of Scope for v0

- Audio synthesis
- Audio augmentation
- Edge Impulse integration
- ESP32 firmware
- On-device inference
- Model fine-tuning
- Autonomous prompt rewriting
- Full production database architecture

---

## 3. System Architecture

The project should be split into two main parts:

```text
Frontend UI
  ↓
FastAPI Backend
  ↓
Dataset Pipeline
  ↓
TokenRouter / LLM Providers
  ↓
Local Storage / Dataset Artifacts
```

Recommended repo layout:

```text
measurement-dataset-foundry/
  backend/
    app/
      api/
      core/
      pipeline/
      models/
      storage/
      services/
    data/
      runs/
      exports/
      configs/
    main.py
    requirements.txt

  frontend/
    lovable-export-or-react-app/

  docs/
    README.md
    PRD.md
```

The backend and frontend may live in separate repos during early development, especially if Lovable is used to generate the frontend. The API contract should be kept clean so they can be connected later without drama.

---

## 4. Backend Responsibilities

The backend should handle the actual dataset work.

Core responsibilities:

- load YAML configuration
- manage run lifecycle
- generate structured specs
- call LLMs through TokenRouter
- validate generated samples
- store outputs and failures
- expose run status to frontend
- track model usage and cost metadata
- export datasets

The backend should expose a FastAPI interface so the frontend never needs to directly touch files or LLM APIs.

Example backend capabilities:

```text
POST /runs/create
POST /runs/{run_id}/start
POST /runs/{run_id}/pause
POST /runs/{run_id}/resume
GET  /runs
GET  /runs/{run_id}
GET  /runs/{run_id}/samples
GET  /runs/{run_id}/failures
GET  /configs
PUT  /configs/{config_name}
GET  /exports
POST /exports/create
```

Exact endpoint names can change during implementation, but the backend should be designed around these concepts.

---

## 5. Frontend Responsibilities

The frontend should be a visual control and observability layer for the dataset pipeline.

This should not feel like a chatbot or a generic admin panel. It should feel like a lightweight industrial AI operations dashboard.

Useful mental models:

- GitHub Actions dashboard
- Vercel deployment dashboard
- Postman collections
- VSCode settings
- small manufacturing control panel

The frontend should let the user avoid CLI work wherever possible.

---

## 6. Core UI Areas

### 6.1 Run Control Panel

The run control panel is where the user starts, resumes, or extends generation runs.

It should support:

- create a new run
- resume an interrupted run
- add more samples to an existing run
- select run template
- choose dataset profile
- choose generation count or small batch size
- select active prompt/model configuration
- set validation strictness
- view current run status

The system should treat runs as first-class objects.

Each run should have:

- run ID
- status
- created timestamp
- config snapshot
- active prompt versions
- active model selections
- sample counts
- failure counts
- cost metadata

---

### 6.2 Live Pipeline Monitor

The live monitor should show what the pipeline is doing right now.

It should display:

- current stage
- current active model
- samples attempted
- valid samples
- invalid samples
- schema mismatch rate
- semantic mismatch rate
- estimated cost
- cost per valid sample
- throughput
- recent failures
- run progress

Pipeline stages may include:

```text
Spec Generation
Text Generation
Schema Validation
Semantic Validation
Mutation
Revalidation
Export
```

The goal is to make the pipeline understandable at a glance.

---

### 6.3 Sample Explorer

The sample explorer is for inspecting generated data.

Each sample should show:

- generated text
- expected truth
- validator extraction
- diff between truth and validation
- sample status
- model used
- prompt version
- task type
- timestamp
- run ID
- notes or tags

Useful filters:

- valid only
- failures only
- failure type
- measurement phrase
- value kind
- model
- prompt version
- run ID

This view is critical because failures should be understandable without digging through logs.

Recommended layout:

```text
Expected Truth | Generated Text | Validator Output | Diff / Status
```

---

### 6.4 Failure Review

The failure review screen should summarize what is going wrong.

It should show:

- top failure categories
- representative failed samples
- model/prompt responsible
- failure trend over time
- possible human notes

Initial failure categories:

- schema_invalid
- semantic_mismatch
- missing_unit
- wrong_value
- wrong_measurement_phrase
- extra_measurement_added
- duplicate_value
- invalid_json
- rejected

The goal is not to auto-fix everything immediately. The goal is to make the next human-guided prompt/config change obvious.

---

### 6.5 Config / Prompt Studio

The Config / Prompt Studio should be the control panel for models, prompts, task profiles, and generation behavior.

The underlying source of truth should be YAML, but the UI should make common edits visual and low-friction.

The user should not need to type raw model names or edit large files for every small experiment.

#### Prompt Cards

Prompts should be managed as selectable versioned assets.

Example:

```text
[✓] Generator Prompt v1 — Clean Semantic
[ ] Generator Prompt v2 — More Diverse
[ ] Generator Prompt v3 — Aggressive Edge Cases
```

Prompt card actions:

- activate
- deactivate
- duplicate
- rename
- edit
- archive
- add notes
- compare against another prompt

Prompts should not be overwritten casually. Duplicating and tweaking should be the default workflow.

#### Model Cards

Models should also be selectable through cards or checkboxes.

Example:

```text
Generation Models
[✓] Gemini Flash
[ ] Claude Sonnet
[ ] Qwen 32B
[ ] GPT-4.1

Validation Models
[ ] Gemini Flash
[✓] GPT-4.1
[ ] Claude Sonnet

Mutation Models
[✓] Claude Sonnet
[ ] Gemini Flash
```

The UI should support swapping models by selection, not by editing code.

#### Task Profiles

The UI should expose task profiles such as:

```yaml
profiles:
  cheap_bulk:
    temperature: 0.7
    max_tokens: 120

  strict_validator:
    temperature: 0.1
    max_tokens: 300

  adversarial:
    temperature: 1.0
    max_tokens: 250
```

Tasks should reference profiles rather than duplicating settings everywhere.

---

### 6.6 Benchmark / Comparison Screen

The benchmark screen should compare prompts and models.

Useful metrics:

- schema valid rate
- semantic match rate
- failure rate
- diversity score or duplicate rate
- throughput
- estimated cost
- cost per valid sample
- cost per accepted sample

Example comparison:

```text
Model / Prompt       Valid %   Semantic Match %   Cost / Valid   Notes
Gemini Flash + P1     94%          89%              low            fast, some unit misses
GPT-4.1 + P1          99%          97%              high           accurate, expensive
Claude + P2           96%          94%              medium         better phrasing diversity
```

This should support real engineering decisions instead of vibes-based prompt tuning.

---

### 6.7 Export Center

The export screen should allow the user to export:

- all valid samples
- only reviewed samples
- by run
- by prompt version
- by model
- by measurement phrase
- by value kind

Initial formats:

- JSONL
- CSV

Future formats may include Edge Impulse-compatible exports.

---

## 7. YAML Configuration

The system should use YAML as the human-readable control layer.

The YAML should define:

- measurement phrases
- value kinds
- prompt templates
- model registry
- task routing
- task profiles
- validation rules
- generation profiles
- export settings

The UI should read/write this YAML or communicate with backend endpoints that update it safely.

Example structure:

```yaml
project:
  name: measurement_dataset_foundry
  domain: measurement_extraction

models:
  cheap_fast:
    provider: tokenrouter
    model: google/gemini-flash
    notes: "Fast bulk generation candidate"

  validator_strict:
    provider: tokenrouter
    model: openai/gpt-4.1
    notes: "Higher accuracy validation candidate"

  creative_mutator:
    provider: tokenrouter
    model: anthropic/claude-sonnet
    notes: "Useful for adversarial phrasing"

# candidate_models:
#   - anthropic/claude-sonnet
#   - openai/gpt-4.1
#   - google/gemini-flash
#   - qwen/qwen2.5-32b
#   - deepseek/deepseek-chat

tasks:
  generation:
    model_ref: cheap_fast
    prompt_ref: generator_clean_v1
    profile_ref: cheap_bulk

  validation:
    model_ref: validator_strict
    prompt_ref: validator_strict_v1
    profile_ref: strict_validator

  mutation:
    model_ref: creative_mutator
    prompt_ref: mutator_edge_cases_v1
    profile_ref: adversarial
```

The exact model names should be verified during implementation based on TokenRouter’s current supported model list.

---

## 8. TokenRouter Integration

TokenRouter should be the main LLM provider layer.

The backend should centralize all LLM calls through one service abstraction.

Goals:

- avoid hardcoded model calls
- support per-task model selection
- support future provider swaps
- support model benchmarking
- log all usage metadata

Every LLM call should log:

- provider
- model
- task type
- prompt version
- input token estimate
- output token estimate
- cost estimate if available
- latency if available
- run ID
- sample ID or batch ID

Initial routing should be explicit and reproducible.

Avoid fully hidden automatic model selection in v0. Auto-routing may be explored later, but early work should prioritize understanding which model did what.

---

## 9. Dataset Generation Flow

Initial v0 flow:

```text
1. Load YAML config
2. Create or resume run
3. Generate measurement specs
4. Generate text utterances from specs
5. Run schema validation
6. Run semantic validation
7. Store valid samples
8. Store failed samples with reason codes
9. Summarize run metrics
10. Export accepted dataset
```

Optional early feedback loop:

```text
Generate
→ Validate
→ Summarize failure patterns
→ Human updates prompt/config
→ Resume or start new run
```

Later feedback loop:

```text
Generate
→ Validate
→ Mutate hard cases
→ Revalidate
→ Benchmark
→ Export
```

---

## 10. Validation Philosophy

The system should validate at multiple levels.

### Schema Validation

Checks that generated or extracted data matches required structure.

Example:

- required fields exist
- value_kind is valid
- numeric fields match value_kind
- unit_norm is allowed
- JSON is parseable

### Semantic Validation

Uses a validator model to re-extract meaning from generated text and compare against the original truth.

Example:

Truth:

```json
{
  "measurement_phrase": "outer diameter",
  "value_kind": "exact",
  "value_nominal": 65,
  "unit_norm": "mm"
}
```

Generated:

```text
"Outer diameter is 56 millimeters."
```

Validator result:

```json
{
  "measurement_phrase": "outer diameter",
  "value_kind": "exact",
  "value_nominal": 56,
  "unit_norm": "mm"
}
```

Result:

```text
semantic_mismatch: wrong_value
```

Failures should be stored, not silently discarded.

---

## 11. Resumability and Incremental Generation

The system must support interrupted and incremental work.

Required behavior:

- runs have persistent IDs
- outputs are written incrementally
- interrupted runs can resume
- additional batches can be appended later
- duplicate valid samples are avoided
- failures remain available for review
- configs are snapshotted per run

Example use cases:

```text
Run 100 samples today.
Inspect failures.
Update prompt.
Run another 100 samples tomorrow.
Compare both runs.
Export only valid samples.
```

This is central to the project. Dataset generation should be iterative, not a one-shot terminal command.

---

## 12. Storage

For v0, local file storage is acceptable.

Recommended early storage:

```text
data/
  configs/
    dataset_config.yaml
  runs/
    run_2026_05_04_001/
      run_metadata.json
      config_snapshot.yaml
      samples.jsonl
      failures.jsonl
      metrics.json
  exports/
    measurement_dataset_valid.jsonl
    measurement_dataset_valid.csv
```

A database can be added later if needed. The first priority is making the pipeline understandable, inspectable, and restart-safe.

---

## 13. Measurement Domain Defaults

The first target domain is measurement extraction.

Initial measurement phrases may include:

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

Initial value kinds:

- exact
- approx
- range
- tolerance
- min_only
- max_only
- min_max

Initial units:

- mm
- cm
- in

The system should treat measurement phrases as opaque labels. It should not automatically merge “outer diameter” and “outside diameter” unless explicitly configured later.

---

## 14. Human Review Features

The UI should support lightweight human review.

Useful review actions:

- mark sample good
- mark sample bad
- mark sample interesting
- mark sample high-value edge case
- add note
- archive sample
- include/exclude from export

This review data may become valuable later for model training and benchmark analysis.

---

## 15. Design Principles

### Modular, Not Overbuilt

The project should be domain-configurable, but not so abstract that v0 becomes a framework science fair project.

Build for the measurement dataset first, but keep domain-specific rules in YAML.

### UI-First Operation

The user should not need to rely on CLI usage for core workflows.

CLI commands can exist for debugging, but the primary workflow should be:

```text
Open UI
→ select config
→ start/resume run
→ inspect results
→ adjust prompts/models
→ export dataset
```

### Human-Guided Feedback

The system should identify problems and make them easy to understand.

It should not initially rewrite its own prompts, change schemas, or autonomously mutate its instructions.

### Trace Everything

Every generated sample should be traceable to:

- run
- config snapshot
- prompt version
- model
- task profile
- validation result
- timestamp

### Prefer Boring Reliability

Avoid complex agent frameworks, hidden auto-routing, or abstract orchestration until the simple loop works.

---

## 16. Suggested Implementation Order

1. Create FastAPI backend skeleton
2. Add YAML config loading
3. Add run creation and local run storage
4. Add TokenRouter LLM service abstraction
5. Add simple text generation task
6. Add schema validation
7. Add semantic validation
8. Add sample/failure storage
9. Add run metrics
10. Add frontend mock dashboard in Lovable
11. Connect frontend to backend endpoints
12. Add prompt/model selection UI
13. Add export screen
14. Add benchmarking view

---

## 17. Frontend Prompt Direction for Lovable

When generating the frontend, emphasize:

- industrial AI operations dashboard
- dataset control center
- dense but readable metrics
- run control
- sample explorer
- failure review
- prompt/model config cards
- benchmark comparison
- local backend API integration

Avoid:

- landing page feel
- chatbot-first design
- generic SaaS dashboard
- decorative AI visuals
- overly abstract node canvases

The UI should feel practical, inspectable, and controllable.

---

## 18. Next Steps

The next immediate step is to create a backend PRD that Claude Code can implement.

That PRD should focus on:

- FastAPI backend
- TokenRouter integration
- YAML-backed configuration
- run lifecycle
- local file storage
- validation logic
- API endpoints for frontend connection

After that, a Lovable prompt can be created for the frontend dashboard, using this README as the design foundation.
