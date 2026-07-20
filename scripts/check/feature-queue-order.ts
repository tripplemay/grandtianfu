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
  compareFeatureQueue,
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

/** 造一组和 derive_features 同形的特征（墙角 + 天花板孪生 + 门框 + 门顶 + 窗）。 */
function fixture(): QueueFeature[] {
  const corners = ['西北', '东北', '东南', '西南'];
  const feats: QueueFeature[] = [];
  for (const c of corners) {
    feats.push({ id: `corner:r_a:${c}`, priority: 0, world: [100, 200, 0] });
    feats.push({ id: `ceilcorner:r_a:${c}`, priority: 0, world: [100, 200, CEIL] });
  }
  feats.push({ id: 'door:d1:a', priority: 1, world: [0, 500, 0] });
  feats.push({ id: 'doorhead:d1:a', priority: 1, world: [0, 500, 2050] });
  feats.push({ id: 'window:w1:a', priority: 2, world: [800, 0, 0] });
  feats.push({ id: 'winhead:w1:a', priority: 2, world: [800, 0, CEIL] });
  // 打乱，确保结论来自排序而非输入顺序
  return feats.sort((x, y) => x.id.length - y.id.length || (x.id < y.id ? 1 : -1));
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

// 断言 4：排序确定性（同输入不同初始顺序 -> 同结果），且比较器自反一致。
const again = orderFeatureQueue([...fixture()].reverse()).map((f) => f.id);
check(
  JSON.stringify(again) === JSON.stringify(queue.map((f) => f.id)),
  '排序不确定: 输入顺序影响结果',
);
check(compareFeatureQueue(queue[0], queue[0]) === 0, '比较器对自身不返回 0');

if (failures.length > 0) {
  console.error('FAIL feature-queue-order:');
  for (const f of failures) console.error('  - ' + f);
  process.exit(1);
}
console.log(`PASS feature-queue-order (${queue.length} 个特征, 4 条断言)`);
console.log('  轮候序: ' + queue.map((f) => f.id).join(' -> '));
