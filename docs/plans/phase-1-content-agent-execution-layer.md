# Phase 1 Content Agent Execution Layer Implementation Plan

> **For Hermes:** Use subagent-driven-development or Codex for isolated implementation/review tasks, but keep MAGA as marketing content source of truth and Hermes/xhs-writer as execution worker.

**Goal:** Build the first local development slice of MAGA's content-agent execution layer so xhs-writer can claim generation tasks and write back trace/artifacts.

**Architecture:** Add MAGA-native content-agent tables, schemas, service logic, and FastAPI endpoints. Keep executor abstraction lightweight and content-specific; do not build a generic Agent platform. xhs-writer integration remains API/file-adapter based during local development and must not become a production filesystem boundary.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, MySQL JSON columns, Pydantic v2.

---

## Batch 1: Backend execution-layer skeleton

### Task 1: Add content-agent models

**Objective:** Represent executor registry, content tasks, runs, events, and artifacts in SQLAlchemy.

**Files:**
- Create: `platform-server/app/models/content_agent.py`
- Modify: `platform-server/app/models/__init__.py`

**Implementation notes:**
- Table names:
  - `executor_registry`
  - `content_agent_task`
  - `content_agent_run`
  - `content_agent_event`
  - `content_agent_artifact`
- Use existing SQLAlchemy 2 style from `app/models/prompt_optimizer.py`.
- JSON fields hold snapshots, metadata, config, token usage, capabilities.
- Status fields stay string-based for MVP.

**Verification:**
- `python -m compileall app/models/content_agent.py app/models/__init__.py`

### Task 2: Add Pydantic schemas

**Objective:** Define request/response payloads for claim, snapshot, event, artifact, complete, and fail.

**Files:**
- Create: `platform-server/app/schemas/content_agent.py`

**Key schemas:**
- `ContentAgentTaskCreate`
- `ContentAgentClaimRequest`
- `ContentAgentClaimResponse`
- `ContentAgentEventCreate`
- `ContentAgentArtifactCreate`
- `ContentAgentRunCompleteRequest`
- `ContentAgentRunFailRequest`

**Verification:**
- `python -m compileall app/schemas/content_agent.py`

### Task 3: Add service logic

**Objective:** Encapsulate task creation, claim, snapshot retrieval, event/artifact writeback, complete/fail state transitions.

**Files:**
- Create: `platform-server/app/services/content_agent_service.py`

**Behavior:**
- `create_task`: creates a pending content task.
- `claim_task`: finds one pending task matching executor/capabilities, creates a run, marks task running.
- `get_task_snapshot`: returns task input snapshot and asset refs.
- `create_event`: appends trace event.
- `create_artifact`: appends artifact.
- `complete_run`: marks run/task succeeded and writes output summary.
- `fail_run`: marks run/task failed and writes error message.

**Verification:**
- service-level async tests or a smoke script against SQLite where practical.

### Task 4: Add API endpoints

**Objective:** Expose the execution boundary required by xhs-writer.

**Files:**
- Create: `platform-server/app/api/v1/endpoints/content_agent.py`
- Modify: `platform-server/app/api/v1/router.py`

**Endpoints:**
- `POST /api/v1/content-agent/tasks`
- `POST /api/v1/content-agent/tasks/claim`
- `GET /api/v1/content-agent/tasks/{task_id}/snapshot`
- `POST /api/v1/content-agent/runs/{run_id}/events`
- `POST /api/v1/content-agent/runs/{run_id}/artifacts`
- `POST /api/v1/content-agent/runs/{run_id}/complete`
- `POST /api/v1/content-agent/runs/{run_id}/fail`

**Verification:**
- Import router successfully.
- OpenAPI generation does not fail.

### Task 5: Add Alembic migration

**Objective:** Create the five content-agent tables and indexes.

**Files:**
- Create: `platform-server/alembic/versions/028_add_content_agent_execution_layer.py`

**Verification:**
- `python -m compileall alembic/versions/028_add_content_agent_execution_layer.py`
- Later local DB: `alembic upgrade head`.

---

## Batch 2: First local xhs-writer adapter

### Task 6: Snapshot to xhs brief adapter

**Objective:** Convert ContentTask snapshot to xhs-writer brief YAML/dict.

**Files:**
- Create: `scripts/content_agent_snapshot_to_xhs_brief.py`

**MVP mapping:**
- `input.product_topic` or `input.product` -> brief product/topic
- `input.target_audience` -> brief target audience
- `input.style` -> brief style
- optional `painpoint`, `selling_points`, `brand_rules`, `required_aes`

**Verification:**
- Given a mock snapshot JSON, produce a brief YAML that xhs runtime can read.

---

## Batch 3: Local smoke workflow

### Task 7: Manual end-to-end dry run

**Objective:** Validate the MAGA API boundary with a mock task before connecting real xhs-writer runtime.

**Flow:**
1. Create pending task.
2. Claim as `hermes_xhs_writer`.
3. Write one status event.
4. Write one draft artifact.
5. Write one final_content artifact.
6. Complete the run.

**Acceptance:**
- Task status is `succeeded`.
- Run status is `succeeded`.
- Events/artifacts are queryable in DB.
- No Hermes direct DB production assumption is introduced.
