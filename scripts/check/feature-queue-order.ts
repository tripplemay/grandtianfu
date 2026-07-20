// calib-cure-b3 F004 回归守门 —— 钉住 verifying-1 判 PARTIAL 的那个缺陷。
//
// 跑法（无需安装任何依赖，Node 22+）：
//   node --experimental-strip-types scripts/check/feature-queue-order.ts
//
// 为什么是脚本而不是单测：apps/web 无单测 runner（只有 Playwright e2e，且 e2e 零覆盖
// 标定）。本脚本直接 import 产品模块本体，不复制逻辑 —— 逻辑改坏了这里就会红。
//
// 修复前本脚本会在断言 1 失败：'ceilcorner:X' < 'corner:X' 使天花板角排在其地面孪生
// 之前，孪生联动提示（F004 旗舰交付）对天花板角永不触发 = 死代码。

import {
  isElevated,
  orderFeatureQueue,
  planId,
  type QueueFeature,
} from '../../apps/web/src/lib/calibration/featureQueue.ts';

const CEIL = 2700;
const failures: string[] = [];
const check = (ok: boolean, msg: string) => {
  if (!ok) failures.push(msg);
};

/** 造一组和 derive_features 同形的特征。含**两个成员房**以覆盖 member_rank（F008 C3）：
 *  r_big(rank 0) 与 r_small(rank 1)，且 r_small 的 id 字母序更靠前 —— 若排序退回字母序，
 *  小房间的角会抢到队首，正是用户 L2 实测踩到的坑。 */
function fixture(): QueueFeature[] {
  const corners = ['西北', '东北', '东南', '西南'];
  const feats: QueueFeature[] = [];
  const members: Array<[string, number]> = [
    ['r_big', 0],
    ['aaa_small', 1], // 字母序故意排在 r_big 之前
  ];
  for (const [mid, rank] of members) {
    // 真正的矩形四角（西北/东北/东南/西南），不可摆成一条线 —— 否则 fixture 自身退化，
    // 断言 6 会误报（本脚本第一版就踩了这个）。大房 4000×3000，小房 600×2800（窄条）。
    const [ox, oy, w, h] =
      rank === 0 ? [0, 0, 4000, 3000] : [9000, 0, 600, 2800];
    const rect: Array<[number, number]> = [
      [ox, oy],
      [ox + w, oy],
      [ox + w, oy + h],
      [ox, oy + h],
    ];
    corners.forEach((c, i) => {
      const xy: [number, number] = rect[i];
      feats.push({
        id: `corner:${mid}:${c}`,
        priority: 0,
        member_rank: rank,
        world: [...xy, 0],
      });
      feats.push({
        id: `ceilcorner:${mid}:${c}`,
        priority: 0,
        member_rank: rank,
        world: [...xy, CEIL],
      });
    });
  }
  feats.push({ id: 'door:d1:a', priority: 1, member_rank: 0, world: [0, 500, 0] });
  feats.push({ id: 'doorhead:d1:a', priority: 1, member_rank: 0, world: [0, 500, 2050] });
  feats.push({ id: 'window:w1:a', priority: 2, member_rank: 0, world: [800, 0, 0] });
  feats.push({ id: 'winhead:w1:a', priority: 2, member_rank: 0, world: [800, 0, CEIL] });
  // 打乱，确保结论来自排序而非输入顺序
  return feats.sort((x, y) => x.id.length - y.id.length || (x.id < y.id ? 1 : -1));
}

/** 4 点是否非共面（复刻后端 degeneracy 的 3D SVD 判据，纯 JS 实现，无依赖）。 */
function coplanarRatio(pts: Array<[number, number, number]>): number {
  const n = pts.length;
  const mean = [0, 1, 2].map((k) => pts.reduce((s, p) => s + p[k], 0) / n);
  const c = pts.map((p) => p.map((v, k) => v - mean[k]));
  // 3x3 协方差的最小特征值 / 最大特征值 ≈ (s3/s1)^2；用幂迭代求特征值谱
  const M = [0, 1, 2].map((i) =>
    [0, 1, 2].map((j) => c.reduce((s, p) => s + p[i] * p[j], 0) / n),
  );
  // 3x3 对称阵特征值：解特征多项式（闭式，避免引入线代库）
  const p1 = M[0][1] ** 2 + M[0][2] ** 2 + M[1][2] ** 2;
  const q = (M[0][0] + M[1][1] + M[2][2]) / 3;
  const p2 =
    (M[0][0] - q) ** 2 + (M[1][1] - q) ** 2 + (M[2][2] - q) ** 2 + 2 * p1;
  const p = Math.sqrt(p2 / 6) || 1e-30;
  const B = M.map((row, i) => row.map((v, j) => (v - (i === j ? q : 0)) / p));
  const detB =
    B[0][0] * (B[1][1] * B[2][2] - B[1][2] * B[2][1]) -
    B[0][1] * (B[1][0] * B[2][2] - B[1][2] * B[2][0]) +
    B[0][2] * (B[1][0] * B[2][1] - B[1][1] * B[2][0]);
  const phi = Math.acos(Math.max(-1, Math.min(1, detB / 2))) / 3;
  const e1 = q + 2 * p * Math.cos(phi);
  const e3 = q + 2 * p * Math.cos(phi + (2 * Math.PI) / 3);
  return e1 <= 0 ? 0 : Math.sqrt(Math.max(0, e3) / e1);
}

const queue = orderFeatureQueue(fixture());
const posOf = new Map(queue.map((f, i) => [f.id, i]));

// 断言 1（承重）：每个异面点的地面孪生必须排在它**之前** —— 否则孪生联动提示是死代码。
for (const f of queue) {
  if (!isElevated(f)) continue;
  const twin = planId(f.id);
  if (twin === f.id) continue;
  const tp = posOf.get(twin);
  check(
    tp !== undefined && tp < posOf.get(f.id)!,
    `孪生联动死代码: ${f.id} (位次 ${posOf.get(f.id)}) 排在其地面孪生 ${twin} (位次 ${tp}) 之前/缺失`,
  );
}

// 断言 2：F003 置信度分级仍是首要键（结构角 < 门框开口 < 存疑窗点），不得被本次修复打乱。
const prios = queue.map((f) => f.priority);
check(
  prios.every((p, i) => i === 0 || prios[i - 1] <= p),
  `priority 非单调递增: ${prios.join(',')}`,
);

// 断言 3：存疑窗点仍垫底（F003 的承重行为）。
check(
  queue[queue.length - 1].priority === 2,
  `队尾不是存疑窗点: ${queue[queue.length - 1].id}`,
);

// 断言 4：排序确定性（同输入不同初始顺序 -> 同结果）。
const again = orderFeatureQueue([...fixture()].reverse()).map((f) => f.id);
check(
  JSON.stringify(again) === JSON.stringify(queue.map((f) => f.id)),
  '排序不确定: 输入顺序影响结果',
);

// 断言 5（F008 C3，承重）：大成员房的角必须先于小成员房 —— 哪怕小房 id 字母序更靠前。
const firstSmall = queue.findIndex((f) => f.member_rank === 1);
const lastBig = queue.map((f) => f.member_rank).lastIndexOf(0);
check(
  firstSmall === -1 || lastBig === -1 || firstSmall > queue.findIndex((f) => f.member_rank === 0),
  'member_rank 未生效: 小成员房的角抢在大成员房之前(用户 L2 实测的窄条房坑)',
);
check(
  queue.slice(0, 4).every((f) => f.member_rank === 0),
  `首 4 点未全部取自最大成员房: ${queue.slice(0, 4).map((f) => f.id).join(',')}`,
);

// 断言 6（F008 C4，承重）：**首 4 点必须非共面** —— MIN_POINTS=4 一满就自动 dry-run，
// 共面输入会让用户拿到坏解算（实测 reproj 754px / 相机高 0.66m）。
const first4 = queue.slice(0, 4).map((f) => f.world);
const zSpread = Math.max(...first4.map((w) => w[2])) - Math.min(...first4.map((w) => w[2]));
check(zSpread > 1, `首 4 点 z 跨度=${zSpread}mm, 全同高 = 共面输入`);
const ratio = coplanarRatio(first4 as Array<[number, number, number]>);
check(ratio > 0.08, `首 4 点近共面 s3/s1=${ratio.toFixed(4)} (需 >0.08)`);

// 断言 7（F008 C4 副产物）：第 4 位应是某个已出现地面点的异面孪生 —— 孪生竖线提示
// 因此在 MIN_POINTS 预算内首次触发（F004 的功能第一次真正可达）。
const fourth = queue[3];
check(isElevated(fourth), `第 4 位不是异面点: ${fourth.id}`);
check(
  queue.slice(0, 3).some((f) => f.id === planId(fourth.id)),
  `第 4 位 ${fourth.id} 的地面孪生不在前 3 位内`,
);

if (failures.length > 0) {
  console.error('FAIL feature-queue-order:');
  for (const f of failures) console.error('  - ' + f);
  process.exit(1);
}
console.log(`PASS feature-queue-order (${queue.length} 个特征, 7 组断言)`);
console.log('  轮候序: ' + queue.map((f) => f.id).join(' -> '));
