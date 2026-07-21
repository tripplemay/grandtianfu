/**
 * calib-route-a1 F001 — mark.html 的真实浏览器布局自检。
 *
 * 跑法（在仓库任意位置）：
 *     node scripts/check/mark-tool-layout.mjs
 *
 * playwright 装在 apps/web 里；node 按**脚本所在位置**解析模块而非 cwd，
 * 故此处显式从 apps/web/node_modules 解析，不依赖调用者的 cwd。
 *
 * 为什么需要它：mark.html 是纯前端工具，pytest 覆盖不到。实际踩过的坑 ——
 * 侧栏新增平面图画布后，原本给照片画布写的通用 `canvas { position: absolute }`
 * 把它也绝对定位到页面左上角，**整块盖住两个文件选择框**，表现为「点 choose
 * file 没反应」。肉眼看页面完全正常（画布是透明的），只有 elementFromPoint
 * 能查出来。
 *
 * 同类前科：calib-cure-b3 F002 —— 新增 ShootingGuideDiagram 用了调色板外的
 * 颜色，类不生成 CSS，最承重的高亮线 stroke:none 不可见。都是「新加的可视元素
 * 没在真实浏览器里验过」。
 */
import { fileURLToPath, pathToFileURL } from 'url';
import { createRequire } from 'module';
import path from 'path';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE = 'file://' + path.resolve(HERE, '../calib_truth/mark.html');

let chromium;
try {
  const req = createRequire(path.resolve(HERE, '../../apps/web/package.json'));
  const mod = await import(pathToFileURL(req.resolve('playwright')).href);
  // playwright 是 CJS，具名导出不会被提升，chromium 挂在 default 上
  chromium = mod.chromium ?? mod.default?.chromium;
  if (!chromium) throw new Error('模块里找不到 chromium');
} catch (e) {
  console.error(`✗ 加载 playwright 失败：${e.message}`);
  console.error('  先在 apps/web 装依赖：cd apps/web && yarn install');
  process.exit(2);
}

// 必须能被真实点到的交互元素
const INTERACTIVE = ['photo', 'pts', 'exp', 'clr'];

const browser = await chromium.launch();
const fails = [];

for (const viewport of [{ width: 1400, height: 900 }, { width: 1024, height: 700 }]) {
  const page = await browser.newPage({ viewport });
  const jsErrors = [];
  page.on('pageerror', (e) => jsErrors.push(String(e)));
  page.on('console', (m) => m.type() === 'error' && jsErrors.push(m.text()));
  await page.goto(PAGE);
  await page.waitForTimeout(200);

  const tag = `${viewport.width}x${viewport.height}`;
  const results = await page.evaluate((ids) => {
    return ids.map((id) => {
      const el = document.getElementById(id);
      if (!el) return { id, missing: true };
      const r = el.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const top = document.elementFromPoint(cx, cy);
      return {
        id,
        visible: r.width > 0 && r.height > 0,
        inViewport: r.top >= 0 && r.left >= 0,
        blockedBy: el.contains(top) || top === el
          ? null
          : `<${top ? top.tagName.toLowerCase() : 'null'}${top && top.id ? '#' + top.id : ''}>`,
      };
    });
  }, INTERACTIVE);

  for (const r of results) {
    if (r.missing) { fails.push(`[${tag}] #${r.id} 不存在`); continue; }
    if (!r.visible) { fails.push(`[${tag}] #${r.id} 不可见`); continue; }
    if (r.blockedBy) fails.push(`[${tag}] #${r.id} 被 ${r.blockedBy} 遮挡`);
  }

  // 平面图画布不得脱离文档流（脱流即会盖住侧栏其余内容）
  const plan = await page.evaluate(() => {
    const c = document.getElementById('plan');
    const s = getComputedStyle(c);
    const r = c.getBoundingClientRect();
    return { position: s.position, w: r.width, h: r.height, right: r.right };
  });
  if (plan.position !== 'static') {
    fails.push(`[${tag}] #plan position=${plan.position}（须 static，否则会盖住侧栏）`);
  }
  if (plan.right > 340) {
    fails.push(`[${tag}] #plan 溢出侧栏（right=${plan.right|0} > 340）`);
  }
  if (jsErrors.length) fails.push(`[${tag}] JS 错误: ${jsErrors.join(' | ')}`);

  console.log(`[${tag}] 交互元素 ${INTERACTIVE.length} 个已查；#plan position=${plan.position} ${plan.w|0}x${plan.h|0}`);
  await page.close();
}

await browser.close();

if (fails.length) {
  console.error('\n✗ mark.html 布局自检失败:');
  for (const f of fails) console.error('  - ' + f);
  process.exit(1);
}
console.log('\n✓ mark.html 布局自检通过');
