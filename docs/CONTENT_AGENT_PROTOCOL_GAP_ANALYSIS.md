# Content Agent Protocol Gap Analysis

Date: 2026-05-08

Scope: Compare current Phase-1 implementation / clean schema path against latest `MAGA_MVP_ARCHITECTURE.md`, `EXECUTOR_PROTOCOL.md`, and `AGENT_EXECUTION_LAYER_PLAN.md`.

## Current direction confirmed

Latest docs confirm the new paradigm:

- MAGA remains the marketing content workbench, asset center, control plane, source of truth.
- Hermes `maga-worker` is the early unified executor, not business source of truth; historical `xhs-writer` is only its `xhs.*` capability source.
- MVP front stage is simple: product/topic, optional audience, style, one-click generation, title/body output.
- Complexity is internal: intent normalization, strategy completion, generation, style optimization, publishability check.
- Protocol direction is now push stage orchestration: MAGA invokes executor capabilities; executor reports events/artifacts/completion callbacks.

## Important protocol changes vs current code

### 1. Pull claim vs push invoke

Current code has:

- `POST /content-agent/tasks/claim`
- `GET /content-agent/tasks/{task_id}/snapshot`
- Executor pulls task and then writes events/artifacts/complete/fail.

Latest protocol says:

- MAGA creates run and stage_call.
- MAGA calls executor `POST {executor_base}/invoke`.
- Executor returns sync result or async ack.
- Executor writes callbacks during stage.
- MAGA decides next stage after each capability.

Conclusion:

- Pull claim can remain only as local dev fallback / v0.0 compatibility.
- Real v0.1 implementation should add push invoke orchestrator and stage_call table.

### 2. StageCall is missing

Protocol makes Stage Call a first-class concept:

- `stage_call_id`
- `capability`
- `schema_version`
- `sequence_no`
- `invoke_mode`
- `status`
- `input_snapshot_json`
- `output_snapshot_json`
- `stats_json`
- `deadline_at`
- retry linkage

Current clean schema lacks `content_agent_stage_call`.

Conclusion:

- Add `ContentAgentStageCall` before building serious Hermes integration.
- `RunEvent` and `Artifact` should be grouped by `stage_call_id`.

### 3. Run token / state protection missing

Protocol requires:

- `run_token` on run.
- Executor callbacks include `X-Run-Token`.
- MAGA checks current `stage_call_id` and run token before accepting complete/fail/status transitions.

Current code has no `run_token`, no `current_stage_call_id`, no token validation.

Conclusion:

- Add run token fields and validation plumbing.

### 4. ExecutorRegistry fields are too v0.0

Current model has:

- `profile_name`
- `endpoint`
- `capabilities`
- `trigger_mode`

Protocol expects:

- `protocol_version`
- `invoke_url`
- `supported_capabilities_json`
- `auth_token_secret_ref`
- `hmac_secret_ref`
- `max_concurrency` likely useful

Conclusion:

- Rename/augment fields to protocol terms while preserving current tests.

### 5. Event / Artifact need protocol fields

Current event lacks:

- `stage_call_id`
- `occurred_at`
- `otel_attributes_json`
- `idempotency_key`

Current artifact lacks:

- `stage_call_id`
- `artifact_code`
- `idempotency_key`

Conclusion:

- Add these before implementing callback idempotency.

### 6. Human review table missing

Protocol and execution plan include:

- `content_agent_human_review`
- `/runs/{run_id}/human-review`
- needs_review gate

Current code only supports fail/complete.

Conclusion:

- Add after StageCall, before front-end review UI.

### 7. Capability list changes the orchestration unit

Protocol v0.1 capabilities:

1. `xhs.interpret_brief`
2. `xhs.run_ae_analysis`
3. `xhs.generate_draft`
4. `xhs.run_ae_review`
5. `xhs.rewrite_draft`

Current adapter writes one whole `brief.yaml` for xhs_runtime full flow.

Conclusion:

- For MVP local smoke, whole-flow adapter is fine.
- For protocol v0.1, Hermes `maga-worker` should expose `/invoke` and map each `xhs.*` capability to a bounded part of the historical xhs runtime.
- MAGA should orchestrate stage sequence and rewrite decision, not Hermes.

## Data model recommendation after reading docs

Clean schema Phase 1 should now be:

1. `executor_registry`
2. `content_brief`
3. `brief_snapshot`
4. `content_agent_task`
5. `content_agent_run`
6. `content_agent_stage_call`
7. `content_agent_event`
8. `content_agent_artifact`
9. `content_agent_human_review`

Then Phase 1.5 / Phase 2:

10. `content_version`
11. `generation_strategy`
12. `expert_definition`
13. `expert_rule_set`
14. `score_rubric`

Do not add Brand/Product/Corpus into the critical path until the three-field MVP generation works; include them as snapshots in `brief_snapshot.snapshot_json` first.

## API recommendation

Add protocol v0.1 endpoints under current prefix:

Executor callback endpoints:

- `POST /api/v1/content-agent/runs/{run_id}/events`
- `POST /api/v1/content-agent/runs/{run_id}/artifacts`
- `POST /api/v1/content-agent/runs/{run_id}/human-review`
- `POST /api/v1/content-agent/runs/{run_id}/stage-calls/{stage_call_id}/complete`
- `POST /api/v1/content-agent/runs/{run_id}/stage-calls/{stage_call_id}/fail`
- `POST /api/v1/content-agent/runs/{run_id}/heartbeat`

MAGA internal orchestration endpoints / service methods:

- create task from simple MVP input
- start run
- create next stage call
- invoke executor
- apply stage result and decide next stage

Keep v0.0 endpoints temporarily:

- `tasks/claim`
- `tasks/{task_id}/snapshot`

But mark as dev fallback.

## Immediate next implementation order

1. Add `ContentAgentStageCall` model + schema + tests.
2. Extend run/event/artifact models with protocol fields.
3. Add idempotency tests for event/artifact upload.
4. Add complete/fail stage-call endpoints with run_token + current_stage_call validation.
5. Add a small MAGA-side stage orchestrator for one capability at a time.
6. Adapt local Hermes `maga-worker` integration from pull/full-flow to push/invoke skeleton.

## Open decision

For quickest MVP, there are two viable paths:

A. Protocol-correct path:
- Implement push invoke + stage_call now.
- Slightly slower, but aligns with docs.

B. Local smoke path:
- Keep pull claim + full-flow xhs_runtime adapter for one end-to-end demo.
- Then refactor to protocol v0.1.

Given latest docs are explicit about push mode and StageCall, choose A unless there is a demo deadline requiring B.
