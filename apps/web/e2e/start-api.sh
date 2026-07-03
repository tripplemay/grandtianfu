#!/usr/bin/env bash
# e2e 用 FastAPI 启动器: 活数据拷入沙箱再起服 (红线: e2e 绝不写 data/projects)。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SANDBOX="$ROOT/.e2e-sandbox"
rm -rf "$SANDBOX"
mkdir -p "$SANDBOX"
cp -R "$ROOT/data/projects" "$SANDBOX/projects"
export DATA_DIR="$SANDBOX/projects"
export ARTIFACTS_DIR="$SANDBOX/artifacts"
export UPLOADS_DIR="$SANDBOX/uploads"
export PYTHONPATH="$ROOT/packages/floorplan_core"
cd "$ROOT/apps/api"
exec python3 -m uvicorn main:app --host 127.0.0.1 --port "${E2E_API_PORT:-8010}"
