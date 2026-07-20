// calib-cure-b3 F007 守门：拦截 tailwind 调色板之外的颜色类。
//
// 跑法（无需装依赖，Node 22+）：
//   node --experimental-strip-types scripts/check/tailwind-palette.ts
//
// 为什么需要它：apps/web/tailwind.config.js 的 `theme.colors` 是**整表覆盖**（不是
// `theme.extend.colors`），默认调色板里的 emerald / sky / fuchsia / rose 等**根本不存在**。
// 写 `bg-emerald-500` 不会报错、tsc 不管、eslint 不管、构建不失败 —— 它只是**一条 CSS 都
// 不生成**，元素静默退回默认色。
//
// 这类缺陷本批实际造成过：
//   - NOTICE_TONE.info 整条用 sky → 所有 tone="info" 提示条无边框/无背景/无文字色；
//   - CalibrationPreview 线框 text-fuchsia-* + stroke=currentColor → 线框不是紫红色；
//   - 特征点序号徽章 bg-emerald-500 + text-white → 浅色主题下白底白字；
//   - ShootingGuideDiagram 的「两面墙」高亮线 stroke: none → 整张示意图最承重的元素不可见。
//
// 教训（写给未来的自己）：**合规检查必须看构建产物，不能只看写法。** 上一轮验收看了写法、
// 判「复用设计系统 + 成对 dark: + 无 bg-*-50」全部合规，而实效是假的。本脚本把这条从
// 「靠人自觉」变成「工具强制」。

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const ROOT = new URL('../..', import.meta.url).pathname;
const WEB = join(ROOT, 'apps/web');
const SRC = join(WEB, 'src');

/** 从 tailwind.config.js 的 theme.colors 提取顶层色名（花括号配对扫描，避开 extend）。 */
function paletteNames(): Set<string> {
  const cfg = readFileSync(join(WEB, 'tailwind.config.js'), 'utf8');
  const m = /colors:\s*\{/.exec(cfg);
  if (!m) throw new Error('tailwind.config.js 中找不到 theme.colors');
  let depth = 1;
  let j = m.index + m[0].length;
  const start = j;
  while (depth > 0 && j < cfg.length) {
    if (cfg[j] === '{') depth++;
    else if (cfg[j] === '}') depth--;
    j++;
  }
  const block = cfg.slice(start, j - 1);
  const names = new Set<string>();
  for (const mm of block.matchAll(/^\s{0,8}([A-Za-z][A-Za-z0-9]*)\s*:/gm)) names.add(mm[1]);
  if (names.size === 0) throw new Error('theme.colors 解析出 0 个色名');
  return names;
}

const UTIL =
  '(?:bg|text|border|ring|fill|stroke|from|via|to|decoration|outline|divide|accent|caret|shadow|placeholder)';
const CLASS_RE = new RegExp(`\\b(?:[a-z-]+:)*(${UTIL})-([a-z]+)-(\\d{2,3})(?:\\/\\d+)?\\b`, 'g');

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(tsx?|css)$/.test(name)) out.push(p);
  }
  return out;
}

const palette = paletteNames();
// 非颜色的同形 utility（如 border-2 已被 \d 排除；这里挡住语义关键字）
const NOT_COLORS = new Set(['none', 'full', 'auto', 'current', 'inherit', 'transparent']);

const violations: string[] = [];
for (const file of walk(SRC)) {
  const lines = readFileSync(file, 'utf8').split('\n');
  lines.forEach((line, i) => {
    for (const m of line.matchAll(CLASS_RE)) {
      const [, util, color, shade] = m;
      if (NOT_COLORS.has(color) || palette.has(color)) continue;
      violations.push(`${relative(ROOT, file)}:${i + 1}  ${util}-${color}-${shade}`);
    }
  });
}

if (violations.length > 0) {
  console.error(`FAIL tailwind-palette: ${violations.length} 处使用了调色板外的颜色`);
  console.error('这些类不会生成任何 CSS —— 元素会静默退回默认色，不会报错也不会构建失败。');
  console.error(`可用色名: ${[...palette].sort().join(' ')}`);
  for (const v of violations) console.error('  - ' + v);
  process.exit(1);
}
console.log(`PASS tailwind-palette (扫描 ${walk(SRC).length} 个文件, 调色板 ${palette.size} 色)`);
