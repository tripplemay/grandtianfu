import { test, expect, type Page } from '@playwright/test';

// CP5v2/v3 贴合并房与合并组: 多候选点选目标 / Esc 取消 / 打通方向 / 分隔还原 /
// 组单房间视图 / 方案几何页版本管理只读。沙箱 API 数据 (start-api.sh), 全程不点
// 户型确认, 不落盘活数据。几何编辑走「草稿版本」上下文 (方案上下文几何已只读)。
// D 户型 r_garden(入户花园, space=garden) 恰有两个相邻候选 (r_vest 玄关 / r_foyer)。

// 从当前已确认版本创建草稿 (每测试独立, 版本号动态取返回值)。
async function createDraft(page: Page): Promise<string> {
  const res = await page.request.post('/api/projects/D/baselines', {
    data: {},
  });
  expect(res.status()).toBe(201);
  return ((await res.json()) as { id: string }).id;
}

async function openDraftEditor(page: Page): Promise<string> {
  const vid = await createDraft(page);
  await page.goto(
    `/studio/projects/D/editor?baseline=${encodeURIComponent(vid)}`,
  );
  await expect(page.getByTestId('stage-svg').first()).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.locator('rect[data-room-id="r_garden"]')).toBeVisible({
    timeout: 15_000,
  });
  return vid;
}

// 走完「选 r_garden -> 贴合并房 -> 点选 r_vest」的并入流。
async function mergeGardenIntoVest(page: Page) {
  await page.locator('rect[data-room-id="r_garden"]').click();
  await page.getByRole('button', { name: '贴合并房' }).click();
  const layer = page.getByTestId('merge-pick-layer');
  await expect(layer).toBeVisible();
  await expect(layer.locator('rect')).toHaveCount(2);
  await page.locator('rect[data-room-id="r_vest"]').click();
  await expect(page.getByTestId('merge-pick-layer')).toHaveCount(0);
}

test('贴合并房: 点选目标并入, 侧栏呈现单房间组视图', async ({ page }) => {
  await openDraftEditor(page);
  await mergeGardenIntoVest(page);
  await expect(page.getByText(/已并入 玄关/).first()).toBeVisible();
  // 单房间视图 (CP5v3): 组级面板 (组名=目标房名, space 归目标), 成员细节折叠。
  await expect(page.getByText('合并组 · 2 成员')).toBeVisible();
  await expect(page.getByTestId('group-space')).toContainText('entry');
  // 成员身份收进「高级」折叠, 不再平铺原始 id 面板。
  await expect(page.getByText('高级: 2 个矩形成员')).toBeVisible();
});

test('贴合并房: Esc 取消点选模式', async ({ page }) => {
  await openDraftEditor(page);
  await page.locator('rect[data-room-id="r_garden"]').click();
  await page.getByRole('button', { name: '贴合并房' }).click();
  await expect(page.getByTestId('merge-pick-layer')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('merge-pick-layer')).toHaveCount(0);
});

test('打通: 选中房并入 Shift+点的目标房', async ({ page }) => {
  await openDraftEditor(page);
  await page.locator('rect[data-room-id="r_garden"]').click();
  await page
    .locator('rect[data-room-id="r_vest"]')
    .click({ modifiers: ['Shift'] });
  await page.getByRole('button', { name: '打通' }).click();
  await expect(
    page.getByText(/已打通: 入户花园 并入 玄关/).first(),
  ).toBeVisible();
});

test('分隔: 并房后按 prev_space 还原原名称与 space id', async ({ page }) => {
  await openDraftEditor(page);
  await mergeGardenIntoVest(page);
  // 并房后主选即被并房 r_garden -> 直接点「分隔」走 prev_space 还原回路
  await page.getByRole('button', { name: '分隔' }).click();
  await expect(
    page.getByText(/已分隔 → 还原为「入户花园」/).first(),
  ).toBeVisible();
  // 复用原 space id: garden (开洞 p01 引用它而未被清理); 拆出后回到单房面板
  await expect(page.getByLabel(/空间 space/)).toHaveValue('garden');
});

test('方案几何页: 版本管理项目下只读 + 家具可编辑', async ({ page }) => {
  await page.goto('/studio/projects/D/editor?scheme=default');
  await expect(page.getByTestId('stage-svg').first()).toBeVisible({
    timeout: 15_000,
  });
  // 几何页只读: 指引 banner 可见, 编辑工具 (贴合并房) 不渲染
  await expect(page.getByText(/户型已启用版本管理/).first()).toBeVisible();
  await expect(page.getByRole('button', { name: '贴合并房' })).toHaveCount(0);
  // 家具 Tab 正常可编辑 (投放区就绪)
  await page.getByRole('tab', { name: '家具' }).click();
  await expect(page.getByTestId('furn-canvas-dropzone')).toBeVisible({
    timeout: 15_000,
  });
});
