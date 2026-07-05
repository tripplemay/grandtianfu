import { test, expect, type Page } from '@playwright/test';

// CP5v2 贴合并房点选目标: 多候选高亮 -> 点击指定并入目标; Esc 取消; 打通方向 =
// 并入 Shift+点的目标房; 分隔按 prev_space 还原。沙箱 API 数据 (start-api.sh),
// 全程不点保存, 不落盘。D 户型 r_garden(入户花园, space=garden) 恰有两个相邻
// 候选 (r_vest 玄关 space=entry / r_foyer), 稳定进点选模式。

const EDITOR = '/studio/projects/D/editor?scheme=default';

async function openEditor(page: Page) {
  await page.goto(EDITOR);
  await expect(page.getByTestId('stage-svg').first()).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.locator('rect[data-room-id="r_garden"]')).toBeVisible({
    timeout: 15_000,
  });
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

test('贴合并房: 多候选高亮后点选目标并入, space 归目标房', async ({
  page,
}) => {
  await openEditor(page);
  await mergeGardenIntoVest(page);
  // toast 明示归属 + 合并边界洞提醒 (p01 在 garden/vest... 视数据而定, 只断言归属)
  await expect(page.getByText(/已并入 玄关/).first()).toBeVisible();
  // 状态断言: 并房后主选被并房 r_garden, 侧栏 space 已归目标房 (entry)
  await expect(page.getByText('房间 r_garden')).toBeVisible();
  await expect(page.getByLabel(/空间 space/)).toHaveValue('entry');
});

test('贴合并房: Esc 取消点选模式', async ({ page }) => {
  await openEditor(page);
  await page.locator('rect[data-room-id="r_garden"]').click();
  await page.getByRole('button', { name: '贴合并房' }).click();
  await expect(page.getByTestId('merge-pick-layer')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('merge-pick-layer')).toHaveCount(0);
});

test('打通: 选中房并入 Shift+点的目标房', async ({ page }) => {
  await openEditor(page);
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
  await openEditor(page);
  await mergeGardenIntoVest(page);
  // 并房后主选即被并房 r_garden -> 直接点「分隔」走 prev_space 还原回路
  await expect(page.getByText('房间 r_garden')).toBeVisible();
  await page.getByRole('button', { name: '分隔' }).click();
  await expect(
    page.getByText(/已分隔 → 还原为「入户花园」/).first(),
  ).toBeVisible();
  // 复用原 space id: garden (开洞 p01 引用它而未被清理)
  await expect(page.getByLabel(/空间 space/)).toHaveValue('garden');
});
