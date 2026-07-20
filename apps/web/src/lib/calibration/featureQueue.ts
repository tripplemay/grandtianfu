// calib-cure-b3 F004/F008：特征点轮候排序 + 异面点↔地面孪生定位。
//
// 为什么抽成纯模块：apps/web 没有单测 runner（只有 Playwright e2e，且 e2e 零覆盖标定），
// 这是唯一能被回归脚本直接执行的形态 —— 见 `scripts/check/feature-queue-order.ts`
// （`node --experimental-strip-types` 直跑，不引入任何新依赖）。
//
// 排序要同时满足四条约束（每条都是被实测打出来的）：
//   C1 置信度分级优先（F003）：结构角 < 门框开口 < 存疑窗点。
//   C2 **地面点必须先于它的异面孪生**（F004，verifying-1）：否则孪生联动提示恒不触发 =
//      死代码。原实装同 priority 落 id 字典序，而 `'ceilcorner:' < 'corner:'`，天花板角
//      恒排在孪生之前，实测首次触发位次 11~25 而 MIN_POINTS=4，预算内一次都碰不到。
//   C3 **大成员房的角先轮候**（F008，用户 L2）：原次级键是 planId 字典序，
//      `corner:r-itki-331:*` 字母序最靠前，而该成员是 600×2800mm 的窄条 —— 用户被引导先点
//      一个细条的四角，PnP 基线最差，实测解出 reproj 754px / 相机高 0.66m。改按后端下发的
//      member_rank（成员面积降序）排。
//   C4 **首 4 点必须非共面**（F008，用户 L2）：MIN_POINTS=4 一满就自动 dry-run，若前 4 位
//      全是地面角则 z 跨度=0、s3/s1=0，用户拿到的必然是共面输入。C2 的朴素实现（所有地面点
//      排在所有异面点之前）恰好保证了这一坏结果。故改为「先 3 个铺开的地面角，第 4 位直接给
//      第 1 个地面角的天花板孪生」—— 4 点即非共面，且孪生竖线提示正好在第 4 点首次触发。
//
// C2 与 C4 的相容性：地面 gi 的位次是 i<3 ? i : 2i-2；孪生 ci 的位次是 3+2i。
// 恒有 (i<3 ? i : 2i-2) < 3+2i，故「地面先于其孪生」在任意 i 下都成立。

export interface QueueFeature {
  id: string;
  priority: number;
  member_rank: number;
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

/** 组内基准序：大成员房优先（C3），再按孪生键与 id 稳定收敛。 */
const byMember = (a: QueueFeature, b: QueueFeature): number =>
  a.member_rank - b.member_rank ||
  planId(a.id).localeCompare(planId(b.id)) ||
  a.id.localeCompare(b.id);

/** 首 3 个地面点打头，其后地面/异面交替（C4），异面点始终跟在其地面孪生之后（C2）。 */
const GROUND_HEAD = 3;

function interleaveTier(tier: readonly QueueFeature[]): QueueFeature[] {
  const grounds = tier.filter((f) => !isElevated(f)).sort(byMember);
  const elevated = tier.filter(isElevated).sort(byMember);
  const twinOf = new Map<string, QueueFeature>();
  for (const e of elevated) {
    const k = planId(e.id);
    if (!twinOf.has(k)) twinOf.set(k, e);
  }

  const out: QueueFeature[] = [];
  const emittedElevated = new Set<string>();
  let gi = 0;
  let ci = 0;
  while (gi < grounds.length || ci < grounds.length) {
    // 前 GROUND_HEAD 个只放地面点，之后地面/异面交替
    if (gi < GROUND_HEAD && gi < grounds.length) {
      out.push(grounds[gi++]);
      continue;
    }
    if (ci < gi) {
      const twin = twinOf.get(planId(grounds[ci].id));
      ci++;
      if (twin) {
        out.push(twin);
        emittedElevated.add(twin.id);
        continue;
      }
      continue; // 该地面点没有异面孪生，跳过这一拍
    }
    if (gi < grounds.length) out.push(grounds[gi++]);
    else break;
  }
  // 无地面孪生的异面点（理论上不该有，构造保证成对）兜底附在末尾，不丢特征
  for (const e of elevated) if (!emittedElevated.has(e.id)) out.push(e);
  return out;
}

/** 按契约排出轮候队列（不修改入参，返回新数组）。 */
export function orderFeatureQueue<T extends QueueFeature>(
  features: readonly T[],
): T[] {
  const tiers = [...new Set(features.map((f) => f.priority))].sort(
    (a, b) => a - b,
  );
  const out: T[] = [];
  for (const p of tiers) {
    out.push(
      ...(interleaveTier(features.filter((f) => f.priority === p)) as T[]),
    );
  }
  return out;
}
