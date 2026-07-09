---
name: test
description: Run 阅天府's local test suites (api + engine pytest, and optionally web e2e). Use when asked to run tests, verify Python changes, or before pushing — CI does not run pytest, so this is the only gate for Python code.
---

Run this project's test suites locally. **CI only runs the Playwright smoke test — never pytest** — so the Python suites below are the only thing that catches Python breaks before deploy.

## Python (run both, from the repo root)

```
PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q
PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q
```

- The two suites need different `PYTHONPATH` values (api needs both dirs; the engine needs only its own). Don't merge them into one command.
- Render/rasterization tests `skipif`-skip when `rsvg-convert` (`librsvg2-bin`) is absent — report skips as "not run," not as passes.
- Single test / file: append a path or `-k`, e.g. `PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests/test_eval_harness.py -q` or `... -k test_name`.

## Web e2e (optional — this is what CI runs)

```
cd apps/web && yarn e2e
```

Playwright runs on offset ports (web 3100 / api 8010) against an `.e2e-sandbox/` copy of the data — it never touches live `data/projects`.

## Report

Summarize pass/fail counts per suite and list any **non-skip** failures with the failing test id. If a byte-exact snapshot test fails right after an intentional geometry/render change, flag it for the human (baseline re-freeze is a manual review step) rather than editing the test.
