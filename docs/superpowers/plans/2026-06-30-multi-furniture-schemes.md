# Multi Furniture Schemes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A project can hold multiple furniture schemes, and editor/gallery/render workflows can operate on a selected `scheme_id`.

**Architecture:** Keep `geometry.json` as the project-level source of truth. Add a backend scheme storage layer under `data/projects/{project}/schemes/{scheme_id}` and expose scheme-specific API routes while keeping legacy routes mapped to `default`. Thread `scheme` through the Studio UI using URL query parameters.

**Tech Stack:** FastAPI, pytest, Next.js 15 client components, React 18, TypeScript, existing `floorplan_core` render engine.

---

### Task 1: Backend Scheme Storage

**Files:**
- Create: `apps/api/schemes.py`
- Test: `apps/api/tests/test_schemes_storage.py`

- [ ] **Step 1: Write failing tests**

Cover virtual default listing, first-write migration, default root sync, non-default isolation, duplicate, metadata patch, and soft delete.

Run:

```bash
PYTHONPATH=packages/floorplan_core:apps/api .venv/bin/python -m pytest apps/api/tests/test_schemes_storage.py -q
```

Expected before implementation: import or attribute failures for the missing `schemes` module.

- [ ] **Step 2: Implement storage helpers**

Add safe id validation, `list_schemes`, `create_scheme`, `duplicate_scheme`, `get_scheme`, `patch_scheme`, `delete_scheme`, `read_furniture`, `write_furniture`, `list_renders`, and `append_render`.

- [ ] **Step 3: Verify storage tests pass**

Run the same pytest command. Expected: all tests in `test_schemes_storage.py` pass.

### Task 2: Backend Scheme API

**Files:**
- Modify: `apps/api/main.py`
- Test: `apps/api/tests/test_schemes_api.py`

- [ ] **Step 1: Write failing API tests**

Cover `GET/POST /schemes`, duplicate, patch, delete, scheme furniture read/save, scheme render, and legacy default compatibility.

Run:

```bash
PYTHONPATH=packages/floorplan_core:apps/api .venv/bin/python -m pytest apps/api/tests/test_schemes_api.py -q
```

Expected before implementation: 404 for new routes.

- [ ] **Step 2: Add route handlers**

Wire new routes to `schemes.py`; refactor legacy furniture/render routes to use `default` scheme storage.

- [ ] **Step 3: Verify API tests pass**

Run the same pytest command. Expected: all tests in `test_schemes_api.py` pass.

### Task 3: Scheme-Scoped AI Render History And Artifacts

**Files:**
- Modify: `apps/api/aigc/artifacts.py`
- Modify: `apps/api/main.py`
- Modify: `apps/api/tests/test_artifacts.py`
- Modify: `apps/api/tests/test_render_ai.py`

- [ ] **Step 1: Write failing tests**

Assert nested artifact paths such as `D/scheme_ai_001/ai-render/{uuid}.png`, scheme render histories, and legacy `/render-ai` mapping to `default`.

Run:

```bash
PYTHONPATH=packages/floorplan_core:apps/api .venv/bin/python -m pytest apps/api/tests/test_artifacts.py apps/api/tests/test_render_ai.py -q
```

Expected before implementation: nested artifact save is unsupported and scheme render history routes are missing.

- [ ] **Step 2: Implement nested artifact save and scheme render-ai helper**

Add `ArtifactStore.save_scoped()` and route both old and new render-ai endpoints through a shared helper.

- [ ] **Step 3: Verify render tests pass**

Run the same pytest command. Expected: artifact and render-ai tests pass.

### Task 4: Frontend Scheme Query Plumbing

**Files:**
- Modify: `apps/web/src/lib/studioApi.ts`
- Modify: `apps/web/src/components/studio/editor/FloorplanEditor.tsx`
- Modify: `apps/web/src/components/studio/editor/hooks/useProjectData.ts`
- Modify: `apps/web/src/components/studio/editor/hooks/useFurnitureEditor.ts`
- Modify: `apps/web/src/components/studio/editor/hooks/useDraftAutosave.ts`
- Modify: `apps/web/src/app/studio/projects/[id]/editor/page.tsx`
- Modify: `apps/web/src/app/studio/projects/[id]/gallery/page.tsx`
- Modify: `apps/web/src/app/studio/projects/[id]/render/page.tsx`

- [ ] **Step 1: Update API client**

Add `schemeId?: string` to furniture, render history, and render-ai calls; add scheme CRUD types and helpers.

- [ ] **Step 2: Thread scheme query through pages**

Read `scheme` from `useSearchParams()`, default to `default`, and route gallery/render/editor calls to scheme-aware API endpoints.

- [ ] **Step 3: Isolate editor draft keys**

Include `schemeId` in furniture draft persistence keys so candidate schemes do not overwrite each other's local drafts.

- [ ] **Step 4: Type-check/build**

Run:

```bash
cd apps/web && yarn build
```

Expected: Next build succeeds.

### Task 5: Scheme Page MVP

**Files:**
- Modify: `apps/web/src/app/studio/projects/[id]/scheme/page.tsx`
- Modify: `apps/web/src/lib/studioRoutes.tsx`

- [ ] **Step 1: Replace placeholder with candidate list UI**

Use `listSchemes`, `createScheme`, `duplicateScheme`, `patchScheme`, and `deleteScheme`. Provide actions to open editor/gallery/render with `?scheme={id}`.

- [ ] **Step 2: Enable navigation item**

Remove `comingSoon` from the project-scoped scheme route.

- [ ] **Step 3: Build**

Run:

```bash
cd apps/web && yarn build
```

Expected: Next build succeeds.

### Task 6: Full Verification

**Files:**
- Modify as required by previous tasks only.

- [ ] **Step 1: Run backend test suite**

```bash
PYTHONPATH=packages/floorplan_core:apps/api .venv/bin/python -m pytest apps/api/tests -q
```

Expected: existing API tests plus new scheme tests pass.

- [ ] **Step 2: Run focused engine tests**

```bash
PYTHONPATH=packages/floorplan_core .venv/bin/python -m pytest packages/floorplan_core/tests -q -k 'not render_string_matches_baseline_byte_for_byte'
```

Expected: focused engine tests pass; byte-for-byte golden tests remain excluded because `.phase0-baseline` is not tracked in this checkout.

- [ ] **Step 3: Review diff**

```bash
git status --short
git diff --check
```

Expected: no whitespace errors and only intended files changed.
