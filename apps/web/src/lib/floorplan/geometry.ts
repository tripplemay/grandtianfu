// 纯几何函数 — 从 轴测图POC/editor.html 精确移植 (§③④⑤⑥)。
// 无副作用: 接收数据, 返回新值; 调用方负责以不可变方式应用 (coding-style: 不 mutate)。

import type { Geometry, Room, Rect, Opening, FreeWall, WallRaw } from './types';
import { nextId } from './ids';

export const GRID = 5;
export const SNAP = 8;

// 与引擎一致 (geometry.py): 外墙角色 -> 加粗渲染。_walls_raw dict 不带 ext, 由 role 推导。
export const EXT_ROLES = new Set(['exterior', 'outdoor']);
export function wallIsExt(role: string): boolean {
  return EXT_ROLES.has(role);
}

export const ROOM_TYPES = [
  'living',
  'bedroom',
  'wet',
  'corridor',
  'public',
  'outdoor',
] as const;
export const FREEWALL_ROLES = [
  'interior',
  'exterior',
  'thin',
  'public',
  'outdoor',
  'demarcation',
] as const;

// 房间地面色块配色 (与 editor.html RCOL 一致)。
export const ROOM_COLORS: Record<string, string> = {
  living: '#efe6d2',
  bedroom: '#e8e0cf',
  wet: '#dbe6ec',
  corridor: '#ece7da',
  public: '#e6e6e6',
  outdoor: '#dceadd',
};

export function roomById(g: Geometry, id: string | null): Room | null {
  if (!id) return null;
  return g.rooms.find((r) => r.id === id) ?? null;
}

// 房间并集包围盒, 画布(内容)坐标 = 几何坐标 + origin。用于视口 Fit (阶段 1)。
// 无房间返回 null。
export function roomsContentBBox(
  g: Geometry,
  origin: [number, number],
): { x: number; y: number; w: number; h: number } | null {
  if (!g.rooms.length) return null;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const r of g.rooms) {
    const [x, y, w, h] = r.rect;
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x + w);
    maxY = Math.max(maxY, y + h);
  }
  return {
    x: minX + origin[0],
    y: minY + origin[1],
    w: maxX - minX,
    h: maxY - minY,
  };
}

// 几何坐标命中首个房间 (§②)。
export function roomAt(g: Geometry, px: number, py: number): Room | null {
  for (const r of g.rooms) {
    const [x, y, w, h] = r.rect;
    if (px >= x && px <= x + w && py >= y && py <= y + h) return r;
  }
  return null;
}

// [x,y,w,h] 严格相交 (相接=不重叠), §④。
export function rectsOverlap(a: Rect, b: Rect): boolean {
  return (
    a[0] < b[0] + b[2] - 1e-6 &&
    a[0] + a[2] > b[0] + 1e-6 &&
    a[1] < b[1] + b[3] - 1e-6 &&
    a[1] + a[3] > b[1] + 1e-6
  );
}

// 重叠冲突对: 两房净矩形重叠且未标记同一合并组。sameSpace 决定错误文案。
export interface OverlapError {
  a: string;
  b: string;
  sameSpace: boolean;
}

// 默认拦截 + 合并豁免 (与后端 geometry.validate 一致): 遍历房间对, 净矩形重叠
// 且二者 merge 非空且相等 -> 豁免; 否则记为 ERROR。merge 是元数据, 不影响 derive。
export function findOverlapErrors(rooms: Room[]): OverlapError[] {
  const out: OverlapError[] = [];
  for (let i = 0; i < rooms.length; i++) {
    for (let j = i + 1; j < rooms.length; j++) {
      const A = rooms[i];
      const B = rooms[j];
      if (!rectsOverlap(A.rect, B.rect)) continue;
      if (A.merge && B.merge && A.merge === B.merge) continue; // 同一合并组豁免
      out.push({ a: A.id, b: B.id, sameSpace: A.space === B.space });
    }
  }
  return out;
}

// 重叠冲突对 -> 面板可读文案 (与后端 validate 文案一致)。
export function overlapErrorMessage(e: OverlapError): string {
  return e.sameSpace
    ? `房间重叠未标记合并: ${e.a} x ${e.b}(用「打通」标记合并或拖开)`
    : `跨 space 重叠: ${e.a} x ${e.b}`;
}

// 跨 space 净矩形重叠 -> 禁止 (§④)。
export function crossSpaceOverlap(
  g: Geometry,
  room: Room,
  rect: Rect,
): boolean {
  return g.rooms.some(
    (r) =>
      r.id !== room.id && r.space !== room.space && rectsOverlap(rect, r.rect),
  );
}

// 竖向吸附候选 x: 其他房间左右边 + 外轮廓 (§③)。
export function vCands(g: Geometry, room: Room): number[] {
  const s = new Set<number>();
  g.rooms.forEach((r) => {
    if (r.id !== room.id) {
      s.add(r.rect[0]);
      s.add(r.rect[0] + r.rect[2]);
    }
  });
  const xs = g.rooms
    .map((r) => r.rect[0])
    .concat(g.rooms.map((r) => r.rect[0] + r.rect[2]));
  s.add(Math.min(...xs));
  s.add(Math.max(...xs));
  return [...s];
}

export function hCands(g: Geometry, room: Room): number[] {
  const s = new Set<number>();
  g.rooms.forEach((r) => {
    if (r.id !== room.id) {
      s.add(r.rect[1]);
      s.add(r.rect[1] + r.rect[3]);
    }
  });
  const ys = g.rooms
    .map((r) => r.rect[1])
    .concat(g.rooms.map((r) => r.rect[1] + r.rect[3]));
  s.add(Math.min(...ys));
  s.add(Math.max(...ys));
  return [...s];
}

// 单边吸附 (resize 用): 优先吸附候选边, 否则退回网格 (§③)。
export function snapEdge(v: number, cands: number[]): number {
  let bd = SNAP + 0.001;
  let best = 0;
  for (const c of cands) {
    const d = Math.abs(c - v);
    if (d < bd) {
      bd = d;
      best = c - v;
    }
  }
  if (bd <= SNAP) return best;
  return Math.round(v / GRID) * GRID - v; // 退回网格吸附
}

// 多边联合吸附 (move 用): 任一边吸到任一候选则整体平移 (§③)。
export function bestSnap(edges: number[], cands: number[]): number {
  let bd = SNAP + 0.001;
  let best: number | null = null;
  for (const ev of edges)
    for (const c of cands) {
      const d = Math.abs(c - ev);
      if (d < bd) {
        bd = d;
        best = c - ev;
      }
    }
  if (best !== null) return best;
  return Math.round(edges[0] / GRID) * GRID - edges[0];
}

// 由派生墙 (已扣本洞) 重建寄主墙连续区间, 取含本洞的那段 [lo,hi] (§⑤ D12 夹取防越界)。
// 找不到返回 null (不夹取, 交服务端 D12 报错)。
export function hostExtent(
  op: Opening,
  wallsRaw: WallRaw[] | undefined,
): [number, number] | null {
  if (!wallsRaw) return null;
  const ax = op.wall.axis;
  const at = op.wall.at;
  const [slo, shi] = op.wall.span;
  const EPS = 2;
  const segs: Array<[number, number]> = [[slo, shi]];
  wallsRaw.forEach((w) => {
    if (w.axis === ax && Math.abs(w.at - at) < 1e-6) segs.push([w.lo, w.hi]);
  });
  segs.sort((a, b) => a[0] - b[0]);
  const merged: Array<[number, number]> = [[segs[0][0], segs[0][1]]];
  for (let i = 1; i < segs.length; i++) {
    const s = segs[i];
    const last = merged[merged.length - 1];
    if (s[0] <= last[1] + EPS) last[1] = Math.max(last[1], s[1]);
    else merged.push([s[0], s[1]]);
  }
  for (const m of merged) {
    if (slo >= m[0] - EPS && shi <= m[1] + EPS) return [m[0], m[1]];
  }
  for (const m of merged) {
    if (shi > m[0] && slo < m[1]) return [m[0], m[1]]; // 退化: 与本洞重叠的段
  }
  return null;
}

// ---- 拖拽计算 (返回新 rect; 不修改入参) ---- //

export interface MoveResult {
  rect: Rect;
}

// 拖房间=移动 (§②③④): 吸附 + 取整 + 跨 space 重叠回弹。
export function computeMove(
  g: Geometry,
  room: Room,
  orig: Rect,
  dx: number,
  dy: number,
  alt: boolean,
): Rect {
  let rect: Rect = [orig[0] + dx, orig[1] + dy, orig[2], orig[3]];
  if (!alt) {
    const sdx = bestSnap([rect[0], rect[0] + rect[2]], vCands(g, room));
    const sdy = bestSnap([rect[1], rect[1] + rect[3]], hCands(g, room));
    rect = [rect[0] + sdx, rect[1] + sdy, rect[2], rect[3]];
  }
  rect = [Math.round(rect[0]), Math.round(rect[1]), orig[2], orig[3]];
  if (crossSpaceOverlap(g, room, rect)) return orig; // 越界回弹: 保持上一合法值
  return rect;
}

// 8 把手=缩放 (§②③④)。handle: nw/n/ne/e/se/s/sw/w。
export function computeResize(
  g: Geometry,
  room: Room,
  orig: Rect,
  handle: string,
  gx: number,
  gy: number,
  alt: boolean,
): Rect {
  let x0 = orig[0];
  let y0 = orig[1];
  let x1 = orig[0] + orig[2];
  let y1 = orig[1] + orig[3];
  if (handle.includes('w')) x0 = gx;
  if (handle.includes('e')) x1 = gx;
  if (handle.includes('n')) y0 = gy;
  if (handle.includes('s')) y1 = gy;
  if (!alt) {
    const vc = vCands(g, room);
    const hc = hCands(g, room);
    if (handle.includes('w')) x0 += snapEdge(x0, vc);
    if (handle.includes('e')) x1 += snapEdge(x1, vc);
    if (handle.includes('n')) y0 += snapEdge(y0, hc);
    if (handle.includes('s')) y1 += snapEdge(y1, hc);
  }
  x0 = Math.round(x0);
  y0 = Math.round(y0);
  x1 = Math.round(x1);
  y1 = Math.round(y1);
  const rect: Rect = [
    Math.min(x0, x1),
    Math.min(y0, y1),
    Math.abs(x1 - x0),
    Math.abs(y1 - y0),
  ];
  if (rect[2] < 10 || rect[3] < 10) return orig;
  if (crossSpaceOverlap(g, room, rect)) return orig;
  return rect;
}

// 门窗滑块拖动: 夹取到寄主墙区间 (§⑤ D12)。返回新 span。
export function computeOpeningSpan(
  op: Opening,
  origSpan: [number, number],
  startCoord: number,
  curCoord: number,
  host: [number, number] | null,
): [number, number] {
  const len = origSpan[1] - origSpan[0];
  let lo = Math.round((origSpan[0] + (curCoord - startCoord)) / GRID) * GRID;
  if (host && host[1] - host[0] >= len) {
    lo = Math.max(host[0], Math.min(host[1] - len, lo));
  }
  return [lo, lo + len];
}

// 点墙 (开门模式) 插入默认门 (§⑤): swing / w90 / cut。
export function buildDefaultDoor(
  g: Geometry,
  wall: WallRaw,
  coord: number,
): Opening {
  let lo = Math.max(wall.lo, Math.round((coord - 45) / GRID) * GRID);
  let hi = lo + 90;
  if (hi > wall.hi) {
    hi = wall.hi;
    lo = hi - 90;
  }
  let a: Room | null;
  let b: Room | null;
  if (wall.axis === 'v') {
    a = roomAt(g, wall.at - 1, (lo + hi) / 2);
    b = roomAt(g, wall.at + 1, (lo + hi) / 2);
  } else {
    a = roomAt(g, (lo + hi) / 2, wall.at - 1);
    b = roomAt(g, (lo + hi) / 2, wall.at + 1);
  }
  return {
    id: nextId('d'),
    kind: 'door',
    door_type: 'swing',
    wall: { axis: wall.axis, at: wall.at, span: [lo, hi] },
    hinge: 'lo',
    swing: '+',
    cut: true,
    between: [a ? a.space : '', b ? b.space : ''],
  };
}

// 自由墙: 画两点 (正交) -> free_wall (§⑥)。两点过近返回 null。
export function buildFreeWall(
  p1: [number, number],
  p2: [number, number],
): FreeWall | null {
  const dx = Math.abs(p2[0] - p1[0]);
  const dy = Math.abs(p2[1] - p1[1]);
  let fw: FreeWall;
  if (dx >= dy) {
    fw = {
      id: nextId('fw'),
      axis: 'h',
      at: p1[1],
      span: [Math.min(p1[0], p2[0]), Math.max(p1[0], p2[0])],
      role: 'interior',
    };
  } else {
    fw = {
      id: nextId('fw'),
      axis: 'v',
      at: p1[0],
      span: [Math.min(p1[1], p2[1]), Math.max(p1[1], p2[1])],
      role: 'interior',
    };
  }
  if (fw.span[1] - fw.span[0] < 10) return null;
  return fw;
}

// sweepFlag (门弧方向, § drawDoor)。
export function sweepFlag(
  h: [number, number],
  j: [number, number],
  t: [number, number],
): 0 | 1 {
  const cr = (j[0] - h[0]) * (t[1] - h[1]) - (j[1] - h[1]) * (t[0] - h[0]);
  return cr > 0 ? 1 : 0;
}
