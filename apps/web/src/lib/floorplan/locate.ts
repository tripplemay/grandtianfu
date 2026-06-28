// 定位校验反馈 (阶段 5b / P2-12): 从校验/冲突/警告文案中提取首个可定位几何元素,
// 供侧栏点击 -> 选中并高亮/居中。纯函数, 可单测。

import type { Geometry } from './types';

export type LocateTarget =
  | { kind: 'room'; id: string }
  | { kind: 'opening'; id: string }
  | { kind: 'freewall'; id: string };

export interface GeoBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

// 文案 -> token 集合 (按非字母数字下划线切分)。几何 id 均为简单 token (如 living/d08)。
function tokenize(msg: string): Set<string> {
  return new Set(msg.split(/[^A-Za-z0-9_]+/).filter(Boolean));
}

// 提取首个匹配元素。优先级: opening (warn 文案明确含开洞 id) > freewall > room。
export function locateInMessage(g: Geometry, msg: string): LocateTarget | null {
  const set = tokenize(msg);
  for (const op of g.openings ?? []) {
    if (set.has(op.id)) return { kind: 'opening', id: op.id };
  }
  for (const fw of g.free_walls ?? []) {
    if (set.has(fw.id)) return { kind: 'freewall', id: fw.id };
  }
  for (const r of g.rooms) {
    if (set.has(r.id)) return { kind: 'room', id: r.id };
  }
  return null;
}

// 墙段 (opening/freewall) -> 几何包围盒, 含 pad。axis='v' 为竖墙 (x=at, span 沿 y)。
function segBox(
  axis: string,
  at: number,
  span: [number, number],
  pad: number,
): GeoBox {
  const [lo, hi] = span;
  if (axis === 'v') {
    return { x: at - pad, y: lo - pad, w: 2 * pad, h: hi - lo + 2 * pad };
  }
  return { x: lo - pad, y: at - pad, w: hi - lo + 2 * pad, h: 2 * pad };
}

// 目标元素 -> 几何包围盒 (未叠 origin), 供 zoomToSelection。找不到返回 null。
export function targetGeoBox(g: Geometry, t: LocateTarget): GeoBox | null {
  if (t.kind === 'room') {
    const r = g.rooms.find((rr) => rr.id === t.id);
    return r
      ? { x: r.rect[0], y: r.rect[1], w: r.rect[2], h: r.rect[3] }
      : null;
  }
  if (t.kind === 'opening') {
    const op = (g.openings ?? []).find((o) => o.id === t.id);
    return op ? segBox(op.wall.axis, op.wall.at, op.wall.span, 40) : null;
  }
  const fw = (g.free_walls ?? []).find((f) => f.id === t.id);
  return fw ? segBox(fw.axis, fw.at, fw.span, 40) : null;
}
