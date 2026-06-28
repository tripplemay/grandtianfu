// 统一 id 生成器 (阶段 0 地基)。替代分散的 `Date.now()%100000`(撞号风险)与
// 家具的数组下标身份。计数器单调递增 + base36 随机后缀, 单会话内绝不撞号,
// 跨会话也几乎不可能 (随机后缀)。纯前端运行时 id, 不要求与盘上数据格式耦合。

let counter = 0;

// 生成带前缀的稳定 id, 如 nextId('f') -> 'f-l3k2-7'。
export function nextId(prefix: string): string {
  counter += 1;
  const rand = Math.random().toString(36).slice(2, 6);
  return `${prefix}-${rand}-${counter}`;
}
