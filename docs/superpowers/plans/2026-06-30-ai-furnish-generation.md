# AI Furnish Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and ship AI furniture generation so `/scheme` can request 1..N candidate FurnitureSchemes from a style prompt, using LLM selection plus deterministic placement.

**Architecture:** The LLM only selects controlled furniture types/counts from `room_brief` options and never emits coordinates. A deterministic `floorplan_core.layout` module converts validated selections into room-relative placements, then `catalog.expand()` fills renderable appearance fields. FastAPI exposes `POST /api/projects/{house}/furnish` as an async job that writes new `FurnitureScheme` records; the web scheme page starts the job and polls completion.

**Tech Stack:** Python 3.9, FastAPI, pytest, httpx, `floorplan_core`, existing in-process `JobManager`, Next.js 15/React 18/Tailwind.

---

### Task 1: Deterministic Layout Engine

**Files:**
- Create: `packages/floorplan_core/floorplan_core/layout.py`
- Create: `packages/floorplan_core/tests/test_layout.py`

- [ ] **Step 1: Write failing tests**

Cover deterministic output, catalog-compatible item shapes, room-relative anchors, bounds for rect/round furniture centers, and graceful truncation when a room is too small.

Run:

```bash
PYTHONPATH=packages/floorplan_core .venv/bin/python -m pytest packages/floorplan_core/tests/test_layout.py -q
```

Expected before implementation: import failure for `floorplan_core.layout`.

- [ ] **Step 2: Implement layout planner**

Create `layout.plan(G, selections)` accepting validated selections shaped as:

```python
[
    {"room_id": "r_live", "items": [{"t": "sofa", "count": 1}, {"t": "plant", "count": 2}]}
]
```

The function returns placement-only furniture items with `room_id` and `dx/dy` or `dcx/dcy`, using catalog dimensions to keep centers inside target room rectangles.

- [ ] **Step 3: Verify layout tests pass**

Run the same pytest command. Expected: all layout tests pass.

### Task 2: Chat JSON Client

**Files:**
- Modify: `apps/api/aigc/providers.py`
- Modify: `apps/api/tests/test_providers.py`

- [ ] **Step 1: Write failing provider tests**

Cover `/chat/completions` URL, `response_format={"type":"json_object"}`, model override, JSON object parsing from `choices[0].message.content`, non-200 mapping to `ProviderError`, and malformed JSON mapping to `ProviderError`.

Run:

```bash
PYTHONPATH=packages/floorplan_core:apps/api .venv/bin/python -m pytest apps/api/tests/test_providers.py -q
```

Expected before implementation: `OpenAIImageProvider` has no `chat_json` method.

- [ ] **Step 2: Implement `chat_json`**

Extend provider protocol and OpenAI-compatible provider with `chat_json(messages, model=None, temperature=0.2) -> dict`.

- [ ] **Step 3: Verify provider tests pass**

Run the same pytest command. Expected: provider tests pass.

### Task 3: Furnish Planner Service

**Files:**
- Create: `apps/api/furnish.py`
- Create: `apps/api/tests/test_furnish.py`

- [ ] **Step 1: Write failing planner tests**

Cover prompt construction from room briefs, validation rejecting unknown room/type and reducing over-large counts, deterministic fallback variant naming, `catalog.expand()` use, and creation of multiple independent scheme payloads.

Run:

```bash
PYTHONPATH=packages/floorplan_core:apps/api .venv/bin/python -m pytest apps/api/tests/test_furnish.py -q
```

Expected before implementation: import failure for `furnish`.

- [ ] **Step 2: Implement planner**

Add:

```python
build_messages(style_prompt, briefs, count)
validate_selection(raw, briefs)
generate_candidates(G, provider, style_prompt, count, base_scheme_id)
```

Use `room_brief.build_briefs(G)`, `provider.chat_json()`, `layout.plan()`, and `catalog.expand()`.

- [ ] **Step 3: Verify planner tests pass**

Run the same pytest command. Expected: all planner tests pass.

### Task 4: `/furnish` API Job

**Files:**
- Modify: `apps/api/main.py`
- Modify: `apps/api/tests/test_schemes_api.py`
- Create or modify: `apps/api/tests/test_furnish_api.py`

- [ ] **Step 1: Write failing API tests**

Cover AI disabled returns 503, invalid count returns 400, unknown base scheme returns 404, successful mocked generation returns job id, job completion writes `source=ai` schemes, and root `furniture.json` is not overwritten.

Run:

```bash
PYTHONPATH=packages/floorplan_core:apps/api .venv/bin/python -m pytest apps/api/tests/test_furnish_api.py -q
```

Expected before implementation: 404 for `/api/projects/D/furnish`.

- [ ] **Step 2: Implement endpoint**

Add `POST /api/projects/{house}/furnish` that validates request, checks AI enabled, submits an async job, calls `furnish.generate_candidates()`, creates `FurnitureScheme` records, and returns summaries plus warnings in job result.

- [ ] **Step 3: Verify API tests pass**

Run the same pytest command. Expected: furnish API tests pass.

### Task 5: Frontend Generation Controls

**Files:**
- Modify: `apps/web/src/lib/studioApi.ts`
- Modify: `apps/web/src/app/studio/projects/[id]/scheme/page.tsx`

- [ ] **Step 1: Add API client helpers**

Add `startFurnish(projectId, {style_prompt,count,base_scheme_id})` and reuse `pollJob`.

- [ ] **Step 2: Add UI controls**

Add style prompt textarea, count selector, base scheme selector, generate button, in-progress state, warnings display, and automatic reload when job completes. Keep candidate cards as the primary work surface.

- [ ] **Step 3: Build**

Run:

```bash
cd apps/web && yarn build
```

Expected: Next build succeeds.

### Task 6: Verification And Deployment

**Files:**
- Modify docs only if progress notes need updating.

- [ ] **Step 1: Run backend tests**

```bash
PYTHONPATH=packages/floorplan_core:apps/api .venv/bin/python -m pytest apps/api/tests -q
```

- [ ] **Step 2: Run engine tests**

```bash
PYTHONPATH=packages/floorplan_core .venv/bin/python -m pytest packages/floorplan_core/tests -q -k 'not render_string_matches_baseline_byte_for_byte'
```

- [ ] **Step 3: Run web build**

```bash
cd apps/web && yarn build
```

- [ ] **Step 4: Push branch and merge/deploy**

Push `feat/ai-furnish`; merge to `main` only after tests/build are green. Because production deploy triggers from `main`, verify GitHub Actions or run the existing deploy path, then check production health and `/api/ai/status`.
