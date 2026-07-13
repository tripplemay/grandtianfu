#!/usr/bin/env bash
# bootstrap.sh — 把 Triad Workflow 模板文件从源位置铺到项目运行位置
#
# 使用场景：
#   1. 从 harness-template repo degit 后运行（flat 布局，源文件在 CWD）
#   2. 手工测试：在 aigcgateway 里的 framework/ 目录运行（nested 布局）
#
# 运行方式（从项目根目录）：
#   bash bootstrap.sh

set -euo pipefail

TARGET_DIR="$(pwd)"

# 自动识别源布局：flat（degit）vs nested（从 aigcgateway 的 framework/ 运行）
if [ -d "$TARGET_DIR/harness" ] && [ -d "$TARGET_DIR/memory" ] && [ -d "$TARGET_DIR/templates" ]; then
  SRC_PREFIX="."
  LAYOUT="flat"
elif [ -d "$TARGET_DIR/framework/harness" ]; then
  SRC_PREFIX="framework"
  LAYOUT="nested"
else
  echo "✗ 找不到 framework 源文件。"
  echo "  预期：CWD 下有 harness/ memory/ templates/（flat 布局）"
  echo "  或：CWD 下有 framework/harness/ 等（nested 布局）"
  exit 1
fi

# 安全检查：避免覆盖已有项目
if [ -f "$TARGET_DIR/harness-rules.md" ]; then
  echo "✗ harness-rules.md 已存在，bootstrap.sh 可能已执行过。"
  echo "  如需重新初始化，请先清理现有 harness 文件或在干净目录运行。"
  exit 1
fi

echo "→ Bootstrapping Triad Workflow（布局：${LAYOUT}）"

# 1. Harness 角色文件到根目录
cp "$SRC_PREFIX/harness/harness-rules.md"           "$TARGET_DIR/harness-rules.md"
cp "$SRC_PREFIX/harness/planner.md"                 "$TARGET_DIR/planner.md"
cp "$SRC_PREFIX/harness/generator.md"               "$TARGET_DIR/generator.md"
cp "$SRC_PREFIX/harness/evaluator.md"               "$TARGET_DIR/evaluator.md"
cp "$SRC_PREFIX/harness/orchestration-patterns.md"  "$TARGET_DIR/orchestration-patterns.md"
cp "$SRC_PREFIX/harness/progress.init.json"         "$TARGET_DIR/progress.json"

# 1.5. Claude Code 机制化守门（.claude/：hooks + evaluator subagent + 角色技能）
mkdir -p "$TARGET_DIR/.claude"
cp -r "$SRC_PREFIX/templates/claude/." "$TARGET_DIR/.claude/"
chmod +x "$TARGET_DIR/.claude/hooks/"*.sh
chmod +x "$TARGET_DIR/.claude/autonomous/"*.sh   # 自主模式校验 hook（机件 #1/#3）

# 2. 状态机初始数据
cat > "$TARGET_DIR/features.json" <<'JSON'
{
  "sprint": null,
  "features": []
}
JSON
echo "[]" > "$TARGET_DIR/backlog.json"

# 3. 共享记忆目录
mkdir -p "$TARGET_DIR/.auto-memory/role-context"
cp "$SRC_PREFIX/memory/MEMORY.md"             "$TARGET_DIR/.auto-memory/"
cp "$SRC_PREFIX/memory/project-status.md"     "$TARGET_DIR/.auto-memory/"
cp "$SRC_PREFIX/memory/environment.md"        "$TARGET_DIR/.auto-memory/"
cp "$SRC_PREFIX/memory/user-role.md"          "$TARGET_DIR/.auto-memory/"
cp "$SRC_PREFIX/memory/reference-docs.md"     "$TARGET_DIR/.auto-memory/"
cp "$SRC_PREFIX/memory/role-context/"*.md     "$TARGET_DIR/.auto-memory/role-context/"

# 4. 项目指令（占位符版本，待 Claude 通过 INIT.md 填充）
cp "$SRC_PREFIX/templates/CLAUDE.md"          "$TARGET_DIR/CLAUDE.md"
cp "$SRC_PREFIX/templates/AGENTS.md"          "$TARGET_DIR/AGENTS.md"

# 5. docs 目录骨架
mkdir -p "$TARGET_DIR/docs/specs"
mkdir -p "$TARGET_DIR/docs/test-cases"
mkdir -p "$TARGET_DIR/docs/test-reports/user_report"
mkdir -p "$TARGET_DIR/docs/dev"
touch "$TARGET_DIR/docs/specs/.gitkeep"
touch "$TARGET_DIR/docs/test-cases/.gitkeep"
touch "$TARGET_DIR/docs/test-reports/user_report/.gitkeep"
touch "$TARGET_DIR/docs/dev/.gitkeep"

# 6. .gitignore
if [ ! -f "$TARGET_DIR/.gitignore" ]; then
  cat > "$TARGET_DIR/.gitignore" <<'GITIGNORE'
# Harness agent local identity（本机身份，不入 git）
.agent-id

# OS / editor
.DS_Store
*.swp
*.swo
GITIGNORE
else
  grep -qxF '.agent-id' "$TARGET_DIR/.gitignore" || echo ".agent-id" >> "$TARGET_DIR/.gitignore"
fi

# 7. 如果是 flat 布局（degit 的 template repo），把源文件规整到 framework/ 下
if [ "$LAYOUT" = "flat" ]; then
  echo "→ 规整 template 源文件到 framework/ 子目录（供后续沉淀回流）"
  mkdir -p "$TARGET_DIR/framework"
  mv "$TARGET_DIR/harness"       "$TARGET_DIR/framework/"
  mv "$TARGET_DIR/memory"        "$TARGET_DIR/framework/"
  mv "$TARGET_DIR/templates"     "$TARGET_DIR/framework/"
  [ -d "$TARGET_DIR/patterns" ] && mv "$TARGET_DIR/patterns" "$TARGET_DIR/framework/"
  [ -d "$TARGET_DIR/archive" ] && mv "$TARGET_DIR/archive" "$TARGET_DIR/framework/"
  # framework 自身文档（docs/0*.md）随源归整，避免与项目 docs/ 混淆
  if ls "$TARGET_DIR"/docs/0*.md >/dev/null 2>&1; then
    mkdir -p "$TARGET_DIR/framework/docs"
    mv "$TARGET_DIR"/docs/0*.md "$TARGET_DIR/framework/docs/"
  fi
  [ -f "$TARGET_DIR/cowork-constraint-design.md" ] && mv "$TARGET_DIR/cowork-constraint-design.md" "$TARGET_DIR/framework/"
  [ -f "$TARGET_DIR/proposed-learnings.md" ] && mv "$TARGET_DIR/proposed-learnings.md" "$TARGET_DIR/framework/"
  [ -f "$TARGET_DIR/CHANGELOG.md" ] && mv "$TARGET_DIR/CHANGELOG.md" "$TARGET_DIR/framework/CHANGELOG.md"
  # 根目录 README.md 原是 template landing（=framework/README.md），移走留出干净根目录
  [ -f "$TARGET_DIR/README.md" ] && mv "$TARGET_DIR/README.md" "$TARGET_DIR/framework/README.md"
fi

# 8. 把 INIT.md 移到根目录，方便 Claude CLI 直接找到
if [ -f "$TARGET_DIR/framework/INIT.md" ]; then
  mv "$TARGET_DIR/framework/INIT.md" "$TARGET_DIR/INIT.md"
fi

# 9. bootstrap.sh 自身移走（flat 布局时它在根目录，完成后用处不大）
if [ "$LAYOUT" = "flat" ] && [ -f "$TARGET_DIR/bootstrap.sh" ]; then
  mv "$TARGET_DIR/bootstrap.sh" "$TARGET_DIR/framework/bootstrap.sh"
fi

cat <<EOF

✓ Bootstrap 完成！

项目结构：
  ├── CLAUDE.md / AGENTS.md              （占位符版本，待 Claude 填充）
  ├── harness-rules.md / planner.md / generator.md / evaluator.md
  ├── orchestration-patterns.md          （同会话编排 / 并行 / fan-out 验收）
  ├── .claude/                           （hooks 守门 + evaluator subagent + /plan /build /verify 技能）
  ├── progress.json / features.json / backlog.json
  ├── .auto-memory/                      （T0/T1/T2 分层记忆）
  ├── docs/specs/ / test-cases/ / test-reports/
  └── framework/                         （源模板 + patterns/ 技术域经验库，供沉淀回流）

下一步：
  1. 在本目录打开 Claude CLI
  2. 说：「按 INIT.md 初始化项目」
  3. Claude 会问 6 个问题，自动填好所有占位符

INIT.md 执行完后，记得运行：
  rm INIT.md
  git remote add origin git@github.com:USERNAME/REPO.git
  git push -u origin main

EOF
