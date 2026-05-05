# Frontend PRD — Measurement Dataset Foundry UI v0

## 1. Product Overview

Build a local-first frontend application for the Measurement Dataset Foundry.

This frontend is the visual control center for a synthetic dataset generation backend. It allows the user to create, run, resume, inspect, validate, compare, and export synthetic text datasets.

This is not a landing page, chatbot, generic SaaS dashboard, or decorative AI demo.

It is an interactive operations console for a local FastAPI backend.

The first use case is measurement extraction dataset generation, but the UI should be designed so the system can later support other structured dataset generation workflows.

---

## 2. Product Goal

The frontend should let the user operate the dataset pipeline without relying on CLI workflows.

The user should be able to:

- create dataset generation runs
- resume interrupted runs
- append additional samples to existing runs
- monitor live progress
- inspect generated samples
- review validation failures
- switch prompts and models visually
- compare model/prompt performance
- export valid datasets

The frontend is primarily about control, observability, and iteration.

---

## 3. Core Product Philosophy

### 3.1 UI as Dataset Control Center

Think of the UI as a control room for a synthetic dataset factory.

It should show what the system is doing, what it produced, what failed, why it failed, and what knobs the user can adjust next.

### 3.2 No CLI Dependency for Normal Use

The user does not like CLI-heavy workflows.

The frontend should expose the major backend capabilities visually:

- run creation
- run start/pause/resume
- config review
- prompt selection
- model selection
- sample inspection
- failure review
- export

CLI commands can exist for debugging, but the normal workflow should be UI-first.

### 3.3 Experiment-Oriented Design

The UI should treat prompts, models, profiles, and runs as experiment assets.

The user should be able to duplicate and tweak a prompt, test another model, compare results, then revert or continue.

The UI should avoid destructive editing where possible.

### 3.4 Dense but Readable

This is an engineering tool. It can be information-dense, but it must remain readable and calm.

Avoid huge empty dashboard cards. Avoid vague placeholder widgets. Every panel should correspond to real concepts in the backend.

---

## 4. Visual Direction

Target aesthetic:

- technical
- functional
- slightly industrial
- dark-mode friendly
- data-dense but clean
- calm motion, not flashy motion

Good references:

- GitHub Actions
- Vercel dashboard
- Postman collections
- VSCode settings
- observability dashboards
- lightweight manufacturing control panels

Avoid:

- marketing landing page feel
- chatbot layout
- generic SaaS dashboard templates
- excessive neon/glow
- animated node canvases
- decorative AI illustrations

---

## 5. Aceternity UI Requirement

Use Aceternity UI components selectively to give the interface a premium, modern feel without compromising usability.

Specifically include:

- Background Beams
- Moving Border

Aceternity should be used as an enhancement layer, not as the entire design language.

### 5.1 Background Beams Usage

Use Background Beams in a limited way:

- app shell background
- dashboard hero/header area
- login-free local landing/control home area
- empty state for no runs yet

Do not place heavy animated backgrounds behind every table or every dense data screen.

Do not reduce text readability.

Do not make the interface feel like a crypto landing page.

Background Beams should be subtle, low-contrast, and mostly decorative behind high-level dashboard areas.

### 5.2 Moving Border Usage

Use Moving Border for important, interactive cards or buttons:

- active run card
- primary “Start Run” button
- selected prompt card
- selected model card
- currently running pipeline stage
- high-value warning or status panels

Moving Border should communicate selection, activity, or importance.

Do not use moving borders on every card. If everything glows, nothing matters.

### 5.3 Performance Guardrails

Animated components should not interfere with data-heavy screens.

Requirements:

- animations should remain subtle
- avoid placing animation behind large scrolling tables
- avoid excessive simultaneous animated borders
- prefer static fallbacks if performance drops
- support reduced-motion preference if practical
- prioritize responsiveness over visual effects

---

## 6. App Navigation

Use a persistent sidebar navigation.

Primary sections:

- Runs
- Monitor
- Samples
- Failures
- Config Studio
- Benchmarks
- Exports

Optional secondary sections:

- Settings
- API Status
- Help / Notes

The UI should feel like one cohesive application, not separate pages stitched together.

---

## 7. Main Screens

## 7.1 Runs Screen

### Purpose

The Runs screen is the main control panel for dataset generation.

### User Goals

The user should be able to:

- create a new run
- resume a paused/interrupted run
- append more samples to an existing run
- cancel a run
- inspect run history
- compare recent runs at a glance

### Required UI Elements

- “Create New Run” button
- run list
- run cards
- status badges
- sample count summary
- valid/invalid split
- estimated cost
- active prompt/model summary
- last updated timestamp

### Run Card Fields

Each run card should show:

- run ID
- status
- created time
- updated time
- batch size or target count
- attempted samples
- valid samples
- failed samples
- active generation model
- active validation model
- active prompt references
- estimated cost
- config snapshot indicator

### Interactions

User can:

- open run details
- resume run
- pause run
- append batch
- export run
- compare run

### Visual Notes

Use Moving Border on the currently active/running run card only.

---

## 7.2 Live Monitor Screen

### Purpose

The Live Monitor shows pipeline execution in real time.

### User Goals

The user wants to see:

- whether the backend is working
- what stage it is in
- what model is being called
- how many samples are valid
- what failures are happening
- how much money is being spent

### Required Metrics

Display:

- current run ID
- current stage
- active model
- samples attempted
- valid sample count
- invalid sample count
- schema valid rate
- semantic match rate
- failure rate
- throughput
- estimated cost
- cost per valid sample
- recent failures
- last backend update time

### Pipeline Stage Display

Stages may include:

- Spec Generation
- Text Generation
- Schema Validation
- Semantic Validation
- Mutation
- Revalidation
- Storage
- Export

### Visual Notes

Use a clear stage timeline or stepper.

Moving Border can highlight the active pipeline stage.

Background Beams may appear subtly in the top header area, but not behind dense metric tables.

---

## 7.3 Sample Explorer Screen

### Purpose

The Sample Explorer lets the user inspect generated samples and understand whether the pipeline is producing useful data.

### Layout

Use a split layout:

Left side:

- sample table
- filters

Right side:

- selected sample detail inspector

### Required Table Columns

- status
- generated text preview
- measurement phrase
- value kind
- unit
- model
- prompt version
- run ID
- timestamp

### Filters

Support filters for:

- run
- valid/invalid
- failure type
- model
- prompt version
- measurement phrase
- value kind
- unit
- reviewed/unreviewed
- tagged edge case

### Detail Inspector

The selected sample should show side-by-side panels:

- Expected Truth
- Generated Text
- Validator Output
- Diff / Status

Also show:

- raw model output
- validation result
- failure category
- metadata
- notes
- review tags

### Review Actions

User can mark a sample as:

- good
- bad
- interesting
- high-value edge case
- exclude from export
- include in export

User can add notes.

### Visual Notes

Use strong visual contrast between expected truth and validator output.

Failures should be obvious without being visually chaotic.

---

## 7.4 Failure Review Screen

### Purpose

The Failure Review screen summarizes what is going wrong and helps guide the next config/prompt/model adjustment.

### Required Elements

- failure category breakdown
- failure trend over time
- representative failed samples
- filters by model, prompt, run, phrase, value kind
- top recurring issues
- affected prompts/models

### Initial Failure Categories

- schema_invalid
- semantic_mismatch
- missing_unit
- wrong_value
- wrong_measurement_phrase
- extra_measurement_added
- duplicate_value
- invalid_json
- rejected
- llm_error
- timeout
- unknown

### User Goal

The user should be able to look at this screen and understand what to change next.

Examples:

- validation model is too weak
- generation prompt is allowing extra measurements
- model is dropping units
- tolerance phrases are failing
- one model is much more expensive with little quality gain

### Visual Notes

Use charts sparingly.

A failure category table with representative examples is more useful than decorative graphs.

---

## 7.5 Config Studio Screen

### Purpose

Config Studio is the control center for prompts, models, task profiles, and routing.

This is one of the most important screens.

The user should not need to directly edit YAML for common tasks.

The UI should work as a visual editor for YAML-backed configuration.

### Sections

Config Studio should include:

- Model Registry
- Prompt Library
- Task Routing
- Task Profiles
- Measurement Domain Settings
- Validation Rules

---

### 7.5.1 Model Registry

Show models as cards grouped by task.

Task groups:

- Generation
- Validation
- Mutation
- Summarization

Each model card should show:

- display name
- model ID
- provider
- notes
- enabled/disabled state
- compatible tasks
- estimated cost tier if known
- last used timestamp if available

### Model Selection Interaction

Use checkbox-style selection.

Example:

Generation Models:

- selected: Gemini Flash
- unselected: Claude Sonnet
- unselected: GPT-4.1
- unselected: Qwen 32B

Validation Models:

- selected: GPT-4.1
- unselected: Claude Sonnet
- unselected: Gemini Flash

The user should not need to type model names manually in normal use.

### Visual Notes

Use Moving Border on selected/active model cards.

---

### 7.5.2 Prompt Library

Prompts should be managed as cards.

Each prompt card should show:

- prompt title
- prompt ref
- version
- task type
- active/inactive state
- notes
- last used
- rough performance summary if available

### Prompt Actions

User can:

- activate/deactivate
- duplicate
- rename
- edit
- archive
- add notes
- compare

Default workflow should be duplicate-and-tweak, not overwrite.

### Prompt Editing

Prompt editing should happen in a structured editor panel or modal.

The editor should allow text editing, but make it clear that edits are versioned.

### Visual Notes

Use Moving Border on active prompt cards.

---

### 7.5.3 Task Routing

Show which prompt, model, and task profile are assigned to each task.

Tasks:

- generation
- validation
- mutation
- summarization
- export formatting

Each row should show:

- task name
- selected model
- selected prompt
- selected profile
- active status

The user should be able to change selections using dropdowns or card selectors.

---

### 7.5.4 Task Profiles

Task profiles define runtime behavior.

Fields:

- temperature
- max tokens
- retry count
- timeout
- strictness level
- diversity level
- notes

Show profiles as editable cards.

Example profiles:

- cheap_bulk
- strict_validator
- adversarial
- summarizer

---

### 7.5.5 Measurement Domain Settings

Allow visual review/editing of:

- measurement phrases
- units
- value kinds
- generation ranges
- allowed labels

Initial phrases:

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

---

### 7.5.6 Validation Rules

Show validation rules clearly.

Rules should include:

- required fields by value kind
- allowed units
- maximum text length
- no metadata leakage
- no extra measurements unless configured
- value preservation requirement
- unit preservation requirement

---

## 7.6 Benchmark Screen

### Purpose

Compare models, prompts, and runs.

### Required Metrics

- schema valid rate
- semantic match rate
- failure rate
- cost per valid sample
- total estimated cost
- throughput
- average latency
- duplicate rate if available
- reviewed-good rate if available

### Comparison Views

Support comparison by:

- run
- model
- prompt
- task profile
- value kind
- measurement phrase

### Recommended Layout

Use tables and compact chart cards.

Benchmark table fields:

- model
- prompt
- run count
- valid percentage
- semantic match percentage
- failure percentage
- cost per valid sample
- notes

### User Goal

The user should be able to answer:

- Is the expensive model actually better?
- Which prompt creates fewer failures?
- Which model is fast but sloppy?
- Which prompt creates more useful diversity?

---

## 7.7 Export Center

### Purpose

Export clean datasets.

### Required Features

User can export by:

- run
- valid only
- reviewed only
- model
- prompt
- measurement phrase
- value kind
- unit
- include/exclude edge cases

Initial formats:

- JSONL
- CSV

### Export Preview

Before export, show:

- estimated sample count
- filters applied
- output format
- included fields

### Export History

Show previous exports:

- filename
- format
- sample count
- created time
- filters
- download action

---

## 8. API Integration Expectations

The frontend should communicate with a local FastAPI backend.

Backend API groups:

- health
- config
- runs
- samples
- failures
- metrics
- exports
- benchmarks

The frontend should use an environment variable for the API base URL.

No auth is required for v0.

The frontend should be able to run against mock data before the backend is complete.

---

## 9. Mock Data Requirements

Use realistic mock data.

Mock data should include:

- multiple runs
- running, paused, completed, and failed statuses
- valid samples
- invalid samples
- different failure categories
- multiple prompts
- multiple models
- cost estimates
- task profiles
- export history

Do not use generic placeholder data like “Item 1” or “Lorem ipsum.”

---

## 10. Component Requirements

Recommended component categories:

- AppShell
- Sidebar
- TopStatusBar
- MetricCard
- RunCard
- PipelineStageStepper
- SampleTable
- SampleDetailPanel
- FailureBreakdown
- PromptCard
- ModelCard
- TaskRoutingTable
- ProfileCard
- BenchmarkTable
- ExportPanel
- ConfigEditorPanel

Components should be cleanly organized and reusable.

---

## 11. Interaction Requirements

The UI should support:

- toggling active models
- toggling active prompts
- duplicating prompts
- editing prompt notes
- selecting task profiles
- starting/resuming/pausing runs
- filtering sample lists
- selecting a sample for inspection
- marking samples reviewed
- adding notes
- creating exports

For v0, actions can update mock state if backend endpoints are not ready.

---

## 12. Error and Empty States

Important empty states:

- no runs yet
- no samples yet
- backend disconnected
- config invalid
- no failures
- no exports

Error states should be clear and useful.

Examples:

- backend unavailable
- TokenRouter not configured
- config validation failed
- run failed
- export failed

Avoid vague errors.

---

## 13. Local Development

Frontend should:

- run locally
- connect to local FastAPI backend
- allow API URL configuration
- support mock mode
- require no authentication in v0

---

## 14. Accessibility and Usability

Requirements:

- readable contrast
- keyboard-friendly controls where practical
- clear status indicators
- avoid motion overload
- support reduced motion if practical
- avoid hiding critical information behind hover-only interactions

---

## 15. Future Compatibility

The UI should be designed so future versions can add:

- audio synthesis status
- audio sample explorer
- waveform preview
- noise augmentation settings
- Edge Impulse export
- Postgres-backed datasets
- stronger benchmark analytics
- automated prompt suggestions
- dataset versioning

Do not implement these in v0 unless simple placeholder hooks are useful.

---

## 16. Success Criteria

The frontend is successful if:

- user can operate the dataset system without CLI reliance
- user can create/resume/inspect runs
- user can see live progress and metrics
- user can inspect individual samples clearly
- user can understand failures
- user can switch prompts/models visually
- user can compare runs
- user can export datasets
- UI feels like an operations console, not a demo

---

## 17. Notes for Lovable

When generating this frontend:

- build the full app shell first
- use realistic mock data
- implement all main navigation sections
- prioritize control and inspection
- make Config Studio especially strong
- use Aceternity Background Beams and Moving Border selectively
- avoid a generic SaaS dashboard look
- avoid a chatbot UI
- avoid landing-page sections
- keep the UI dense, useful, and engineer-friendly

End of PRD.
