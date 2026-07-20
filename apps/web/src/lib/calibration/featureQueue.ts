// calib-cure-b3 F004 修复（verifying-1 判 PARTIAL）：特征点轮候排序 + 异面点↔地面孪生定位。
//
// 为什么抽成纯模块：apps/web 没有单测 runner（只有 Playwright e2e，且 e2e 零覆盖标定），
// 这是唯一能被回归脚本直接执行的形态 —— 见 `scripts/check/feature-queue-order.ts`
// （`node --experimental-strip-types` 直跑，不引入任何新依赖）。
//
// verifying-1 实证的缺陷：原实现同 priority 下直接落到 id 字典序，而 `'ceilcorner:' <
// 'corner:'`，于是**天花板角恒排在它的地面孪生之前** → `twinPlaced` 对天花板角永远为
// null → F004 的孪生联动提示在它唯一针对的场景（b2 L2 病灶「天花板角被点到窗户半高」）
// 里是死代码。实测首次触发位次 11~25，而 MIN_POINTS=4，预算内一次都碰不到。

export interface QueueFeature {
  id: string;
  priority: number;
  world: [number, number, number];
}

/** 异面点（Z>0）：天花板转角 / 门窗框顶 —— 须点画面里「高处」，不是地面。 */
export const isElevated = (f: QueueFeature): boolean => f.world[2] > 1;

/** 异面点 -> 其地面孪生 id（同 (x,y) 只差高度，F002 构造保证）。地面点返回自身。 */
export const planId = (id: string): string =>
  id
    .replace(/^ceilcorner:/, 'corner:')
    .replace(/^doorhead:/, 'door:')
    .replace(/^winhead:/, 'window:');

/**
 * 轮候排序契约：priority（F003 置信度分级）→ **地面点先于异面点** → planId → id。
 *
 * 「地面先于异面」是本次修复的承重项：它保证任何异面点被轮候到时，其地面孪生**必定
 * 已在队列更前位置**出现过，孪生联动提示因此可达。同时不改变几何风险 —— 修复前首 4
 * 点是 4 个天花板角（同高 z=2700），修复后是 4 个地面角（同高 z=0），二者同属
 * degeneracy_reason 的「全同高」分支，共面性未变差。
 */
export function compareFeatureQueue(a: QueueFeature, b: QueueFeature): number {
  return (
    a.priority - b.priority ||
    Number(isElevated(a)) - Number(isElevated(b)) ||
    planId(a.id).localeCompare(planId(b.id)) ||
    a.id.localeCompare(b.id)
  );
}

/** 按契约排出轮候队列（不修改入参，返回新数组）。 */
export function orderFeatureQueue<T extends QueueFeature>(
  features: readonly T[],
): T[] {
  return [...features].sort(compareFeatureQueue);
}
