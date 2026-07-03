import { test, expect } from '@playwright/test';

// P0 页面级冒烟 (升级计划安全网): 项目台 / 几何编辑器 / 家具编辑器 / 渲染链路。
// 只读操作为主; 沙箱 API (见 start-api.sh), 不触碰仓库活数据。

test('项目台加载并可进入项目 D', async ({ page }) => {
  await page.goto('/studio/projects');
  // 项目卡: 名称 + 「打开」按钮 (onClick 导航, 非 <a>)。
  await expect(page.getByText('id: D')).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: '打开' }).first().click();
  await expect(page).toHaveURL(/\/studio\/projects\/D\/overview/);
});

test('几何编辑器: 画布渲染房间且缩放控件就绪', async ({ page }) => {
  await page.goto('/studio/projects/D/editor?scheme=default');
  const svg = page.getByTestId('stage-svg').first();
  await expect(svg).toBeVisible({ timeout: 15_000 });
  // D 户型 20+ 房间: 画布上应有大量 rect (房间/网格)。
  await expect
    .poll(async () => svg.locator('rect').count(), { timeout: 15_000 })
    .toBeGreaterThan(5);
  await expect(page.getByText(/%$/).first()).toBeVisible(); // ZoomControls 百分比
});

test('家具编辑器: 家具库与画布投放区就绪', async ({ page }) => {
  await page.goto('/studio/projects/D/editor?scheme=default&tab=furniture');
  await expect(page.getByTestId('furniture-library')).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByTestId('furn-canvas-dropzone')).toBeVisible();
});

test('渲染链路: plan2d SVG 经同源代理可达', async ({ page }) => {
  const res = await page.request.get('/api/projects/D/render?mode=plan2d');
  expect(res.status()).toBe(200);
  expect(res.headers()['content-type']).toContain('svg');
  const body = await res.text();
  expect(body).toContain('<svg');
});
