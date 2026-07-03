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

// ---- 合并组 / 异形空间 (P3 一期): 同 merge 房聚成一个逻辑 (L 形) 房间 ---- //
// 两房同组 iff 两者 merge 非空且相等 (与后端 geometry.merge_groups 一致)。单房/无 merge
// -> 视同独立 (所有下游对无 merge 数据保持原行为)。代表 = 最大面积, 平局最小 id。

// 组内成员 (含自身); 无 merge -> [room]。
export function roomsInGroup(g: Geometry, room: Room): Room[] {
  if (!room.merge) return [room];
  return g.rooms.filter((r) => r.merge && r.merge === room.merge);
}

// 组内成员矩形 (含自身), 按成员 id 稳定序 —— 供 nearestPartRect 的 id tie-break 退化为数组序。
export function groupMemberRects(g: Geometry, room: Room): Rect[] {
  return roomsInGroup(g, room)
    .slice()
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
    .map((r) => r.rect);
}

// 组代表 (最大面积, 平局取最小 id) —— 家具 room_id 锚点 / 单标签用稳定成员。
export function groupPrimary(g: Geometry, room: Room): Room {
  const members = roomsInGroup(g, room);
  if (members.length < 2) return room;
  return members.reduce((best, r) => {
    const area = r.rect[2] * r.rect[3];
    const bestArea = best.rect[2] * best.rect[3];
    if (area > bestArea) return r;
    if (area === bestArea && r.id < best.id) return r;
    return best;
  });
}

// 点 -> 最近成员矩形, tie-break 距离→面积(大优先)→id 序 (与引擎 nearest_part 一致;
// rects 无 id, id tie-break 退化为数组序, 故调用方须传 groupMemberRects 的稳定序)。
export function nearestPartRect(rects: Rect[], x: number, y: number): Rect {
  let best = rects[0];
  let bestDist = Infinity;
  let bestArea = -Infinity;
  for (const rect of rects) {
    const [rx, ry, rw, rh] = rect;
    const dx = Math.max(rx - x, 0, x - (rx + rw));
    const dy = Math.max(ry - y, 0, y - (ry + rh));
    const dist = dx * dx + dy * dy;
    const area = rw * rh;
    if (dist < bestDist || (dist === bestDist && area > bestArea)) {
      best = rect;
      bestDist = dist;
      bestArea = area;
    }
  }
  return best;
}

// 点是否落在组内任一成员矩形 (L 形凹口自然排除)。
export function pointInGroup(rects: Rect[], x: number, y: number): boolean {
  return rects.some(
    ([rx, ry, rw, rh]) => x >= rx && x <= rx + rw && y >= ry && y <= ry + rh,
  );
}

// 两矩形是否共一段共线边 (相接, 供「贴合建议并房」判定)。
function _shareEdge(a: Rect, b: Rect): boolean {
  const [ax, ay, aw, ah] = a;
  const [bx, by, bw, bh] = b;
  const yOverlap = Math.min(ay + ah, by + bh) - Math.max(ay, by) > 1e-6;
  const xOverlap = Math.min(ax + aw, bx + bw) - Math.max(ax, bx) > 1e-6;
  const vAbut =
    (Math.abs(ax + aw - bx) < SNAP || Math.abs(bx + bw - ax) < SNAP) &&
    yOverlap;
  const hAbut =
    (Math.abs(ay + ah - by) < SNAP || Math.abs(by + bh - ay) < SNAP) &&
    xOverlap;
  return vAbut || hAbut;
}

// 「贴合建议并房」候选: 与 room 相接一条边、且未与其同组的房。
export function adjacentMergeCandidates(g: Geometry, room: Room): Room[] {
  return g.rooms.filter(
    (r) =>
      r.id !== room.id &&
      !(r.merge && room.merge && r.merge === room.merge) &&
      _shareEdge(room.rect, r.rect),
  );
}

// L 形三点直画 (P3): p1/p2 定包围盒对角, p3 定缺口角 (离 p3 最近的 bbox 角挖掉)。
// 返回拼成 L 的两个正交矩形 (共一段边, 可直接同组); 缺口过小/过大或退化 -> null (仅直角)。
export function buildLShapeRects(
  p1: [number, number],
  p2: [number, number],
  p3: [number, number],
): [Rect, Rect] | null {
  const x0 = Math.min(p1[0], p2[0]);
  const x1 = Math.max(p1[0], p2[0]);
  const y0 = Math.min(p1[1], p2[1]);
  const y1 = Math.max(p1[1], p2[1]);
  if (x1 - x0 < GRID * 2 || y1 - y0 < GRID * 2) return null;
  const cx = Math.abs(p3[0] - x0) <= Math.abs(p3[0] - x1) ? x0 : x1;
  const cy = Math.abs(p3[1] - y0) <= Math.abs(p3[1] - y1) ? y0 : y1;
  const nx = Math.min(x1, Math.max(x0, p3[0]));
  const ny = Math.min(y1, Math.max(y0, p3[1]));
  const notchW = Math.abs(nx - cx);
  const notchH = Math.abs(ny - cy);
  if (notchW < GRID || notchH < GRID) return null;
  if (notchW >= x1 - x0 - GRID || notchH >= y1 - y0 - GRID) return null;
  const gx1 = Math.max(cx, nx);
  const gx0 = Math.min(cx, nx);
  const gy1 = Math.max(cy, ny);
  const gy0 = Math.min(cy, ny);
  let rectA: Rect;
  let rectB: Rect;
  if (cy === y0) {
    // 缺口在上排: 下部整宽 + 上部保留缺口列之外
    rectA = [x0, gy1, x1 - x0, y1 - gy1];
    rectB =
      cx === x0 ? [gx1, y0, x1 - gx1, gy1 - y0] : [x0, y0, gx0 - x0, gy1 - y0];
  } else {
    // 缺口在下排: 上部整宽 + 下部保留缺口列之外
    rectA = [x0, y0, x1 - x0, gy0 - y0];
    rectB =
      cx === x0
        ? [gx1, gy0, x1 - gx1, y1 - gy0]
        : [x0, gy0, gx0 - x0, y1 - gy0];
  }
  return [rectA, rectB];
}

// 1D 区间差: [lo,hi] 减去若干覆盖区间的并集 -> 剩余子区间。
function _subtract1D(
  lo: number,
  hi: number,
  covers: Array<[number, number]>,
): Array<[number, number]> {
  const merged = covers.slice().sort((a, b) => a[0] - b[0]);
  const out: Array<[number, number]> = [];
  let cur = lo;
  for (const [a, b] of merged) {
    if (a > cur + 1e-6) out.push([cur, Math.min(a, hi)]);
    cur = Math.max(cur, b);
    if (cur >= hi) break;
  }
  if (cur < hi - 1e-6) out.push([cur, hi]);
  return out;
}

// 一组成员矩形的【并集轮廓】线段 (共享/内部边挖掉 -> 只留外轮廓, 正确处理 L 形凹口与
// 重叠矩形)。返回几何坐标线段 [x1,y1,x2,y2]。供 RoomsLayer 画单一组外框 (共享边不描边)。
export function groupOutlineSegments(
  rects: Rect[],
): Array<[number, number, number, number]> {
  const EPS = 1e-6;
  const segs: Array<[number, number, number, number]> = [];
  for (let i = 0; i < rects.length; i++) {
    const [x, y, w, h] = rects[i];
    const xR = x + w;
    const yB = y + h;
    const others = rects.filter((_, j) => j !== i);
    // 水平边 (y=yEdge, x∈[x,xR]): 被"y 向跨过 yEdge 且 x 重叠"的兄弟覆盖处挖掉。
    const subH = (yEdge: number) => {
      const covers: Array<[number, number]> = [];
      for (const [ox, oy, ow, oh] of others) {
        if (oy - EPS <= yEdge && yEdge <= oy + oh + EPS) {
          const a = Math.max(x, ox);
          const b = Math.min(xR, ox + ow);
          if (b - a > EPS) covers.push([a, b]);
        }
      }
      return _subtract1D(x, xR, covers);
    };
    // 竖直边 (x=xEdge, y∈[y,yB]).
    const subV = (xEdge: number) => {
      const covers: Array<[number, number]> = [];
      for (const [ox, oy, ow, oh] of others) {
        if (ox - EPS <= xEdge && xEdge <= ox + ow + EPS) {
          const a = Math.max(y, oy);
          const b = Math.min(yB, oy + oh);
          if (b - a > EPS) covers.push([a, b]);
        }
      }
      return _subtract1D(y, yB, covers);
    };
    for (const [a, b] of subH(y)) segs.push([a, y, b, y]);
    for (const [a, b] of subH(yB)) segs.push([a, yB, b, yB]);
    for (const [a, b] of subV(x)) segs.push([x, a, x, b]);
    for (const [a, b] of subV(xR)) segs.push([xR, a, xR, b]);
  }
  return segs;
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

// ---- 吸附辅助线 (P1-4): 纯检测, 不改吸附结果 ---- //

// 一条对齐辅助线 (几何坐标)。axis='v' -> 竖线 x=pos, 纵跨 [from,to];
// axis='h' -> 横线 y=pos, 横跨 [from,to]。
export interface SnapGuide {
  axis: 'v' | 'h';
  pos: number;
  from: number;
  to: number;
}

const GUIDE_EPS = 0.6; // 吸附后边坐标已对齐到候选值, 仅需极小容差判定命中。

function dedupeGuides(guides: SnapGuide[]): SnapGuide[] {
  const map = new Map<string, SnapGuide>();
  for (const gd of guides) {
    const key = `${gd.axis}:${Math.round(gd.pos)}`;
    const ex = map.get(key);
    if (!ex) map.set(key, gd);
    else
      map.set(key, {
        ...ex,
        from: Math.min(ex.from, gd.from),
        to: Math.max(ex.to, gd.to),
      });
  }
  return [...map.values()];
}

// 拖动/缩放得到的最终 rect, 其 4 边若与其他房间边对齐 (吸附命中) 则产出辅助线。
// 与 computeMove/computeResize 解耦 (只读最终 rect), 不影响吸附数值结果。
export function rectSnapGuides(
  g: Geometry,
  room: Room,
  rect: Rect,
): SnapGuide[] {
  const out: SnapGuide[] = [];
  const rx0 = rect[0];
  const rx1 = rect[0] + rect[2];
  const ry0 = rect[1];
  const ry1 = rect[1] + rect[3];
  for (const r of g.rooms) {
    if (r.id === room.id) continue;
    const ax0 = r.rect[0];
    const ax1 = r.rect[0] + r.rect[2];
    const ay0 = r.rect[1];
    const ay1 = r.rect[1] + r.rect[3];
    for (const cand of [ax0, ax1]) {
      if (
        Math.abs(rx0 - cand) < GUIDE_EPS ||
        Math.abs(rx1 - cand) < GUIDE_EPS
      ) {
        out.push({
          axis: 'v',
          pos: cand,
          from: Math.min(ry0, ay0),
          to: Math.max(ry1, ay1),
        });
      }
    }
    for (const cand of [ay0, ay1]) {
      if (
        Math.abs(ry0 - cand) < GUIDE_EPS ||
        Math.abs(ry1 - cand) < GUIDE_EPS
      ) {
        out.push({
          axis: 'h',
          pos: cand,
          from: Math.min(rx0, ax0),
          to: Math.max(rx1, ax1),
        });
      }
    }
  }
  return dedupeGuides(out);
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

// 开洞最小宽 (轴线单位, 1=10mm): 端点拖宽不可小于此 (P2-8)。
export const OPENING_MIN = 30;

// 门窗端点拖宽 (P2-8): 拖某一端到 curCoord, 网格吸附 + 夹取寄主墙 hostExtent +
// 保最小宽 OPENING_MIN。另一端固定。返回新 span (lo<=hi)。纯函数, 不改入参。
export function computeOpeningResize(
  origSpan: [number, number],
  end: 'lo' | 'hi',
  curCoord: number,
  host: [number, number] | null,
): [number, number] {
  let lo = origSpan[0];
  let hi = origSpan[1];
  const snapped = Math.round(curCoord / GRID) * GRID;
  if (end === 'lo') {
    lo = snapped;
    if (host) lo = Math.max(host[0], lo);
    lo = Math.min(lo, hi - OPENING_MIN); // 保最小宽 (另一端固定)
  } else {
    hi = snapped;
    if (host) hi = Math.min(host[1], hi);
    hi = Math.max(hi, lo + OPENING_MIN);
  }
  return [lo, hi];
}

// 自由墙整体平移 (P2-9): 据 orig at/span + 几何位移 (dx,dy) 算新位置, 网格吸附。
// axis='h' (at=y): 垂直拖 dy 改 at, 水平拖 dx 沿轴移 span; axis='v' 反之。
// 墙天然轴对齐, 平移即"正交"。返回 {at, span}, 不改入参。
export function computeFreeWallMove(
  axis: 'h' | 'v',
  origAt: number,
  origSpan: [number, number],
  dx: number,
  dy: number,
): { at: number; span: [number, number] } {
  const len = origSpan[1] - origSpan[0];
  if (axis === 'h') {
    const at = Math.round((origAt + dy) / GRID) * GRID;
    const lo = Math.round((origSpan[0] + dx) / GRID) * GRID;
    return { at, span: [lo, lo + len] };
  }
  const at = Math.round((origAt + dx) / GRID) * GRID;
  const lo = Math.round((origSpan[0] + dy) / GRID) * GRID;
  return { at, span: [lo, lo + len] };
}

// 画两点 (矩形) -> 新房 rect (§ P1-7): 网格吸附 + 最小尺寸。过小返回 null。
// 类比 buildFreeWall 的两点落点; 调用方负责赋默认 space/type 并经重叠校验。
export function buildRoomRect(
  p1: [number, number],
  p2: [number, number],
): Rect | null {
  const x = Math.round(Math.min(p1[0], p2[0]) / GRID) * GRID;
  const y = Math.round(Math.min(p1[1], p2[1]) / GRID) * GRID;
  const w = Math.round(Math.abs(p2[0] - p1[0]) / GRID) * GRID;
  const h = Math.round(Math.abs(p2[1] - p1[1]) / GRID) * GRID;
  if (w < 10 || h < 10) return null;
  return [x, y, w, h];
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

// 直插窗 (P4 窗直插模式): 点墙落一扇默认窗 (类比 buildDefaultdoor, kind=window, 默认 wtype
// normal, 宽 120)。调用方在插窗模式下用。
export function buildDefaultWindow(
  g: Geometry,
  wall: WallRaw,
  coord: number,
): Opening {
  let lo = Math.max(wall.lo, Math.round((coord - 60) / GRID) * GRID);
  let hi = lo + 120;
  if (hi > wall.hi) {
    hi = wall.hi;
    lo = hi - 120;
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
    id: nextId('w'),
    kind: 'window',
    wtype: 'normal',
    wall: { axis: wall.axis, at: wall.at, span: [lo, hi] },
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

// ---- 多选: 框选 / 对齐 / 分布 (阶段 5a / P2-7) ---- //

// 两矩形相交判定 (用于 marquee 框选; 相接也算命中, 比 rectsOverlap 宽松)。
export function rectsIntersect(a: Rect, b: Rect): boolean {
  return (
    a[0] <= b[0] + b[2] &&
    a[0] + a[2] >= b[0] &&
    a[1] <= b[1] + b[3] &&
    a[1] + a[3] >= b[1]
  );
}

// 把两点 (几何坐标) 归一化为 marquee 矩形 [x,y,w,h]。
export function marqueeRect(
  x0: number,
  y0: number,
  x1: number,
  y1: number,
): Rect {
  return [
    Math.min(x0, x1),
    Math.min(y0, y1),
    Math.abs(x1 - x0),
    Math.abs(y1 - y0),
  ];
}

// 对齐 / 分布的通用包围盒 (id + 几何左上 + 宽高)。
export interface AlignBox {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export type AlignMode =
  | 'left'
  | 'right'
  | 'top'
  | 'bottom'
  | 'hcenter'
  | 'vcenter';
export type DistributeMode = 'h' | 'v';

// 对齐: 据 mode 计算各盒新左上 (x,y)。纯函数, 返回 id -> {x,y} (仅含会动的轴, 另一轴保持)。
// left/right/top/bottom 贴选区包围盒对应边; hcenter/vcenter 对齐到选区包围盒中心线。
// 单元素或空 -> 原值 (no-op)。可单测。
export function alignBoxes(
  boxes: AlignBox[],
  mode: AlignMode,
): Map<string, { x: number; y: number }> {
  const out = new Map<string, { x: number; y: number }>();
  if (boxes.length < 2) {
    boxes.forEach((b) => out.set(b.id, { x: b.x, y: b.y }));
    return out;
  }
  const minX = Math.min(...boxes.map((b) => b.x));
  const maxX = Math.max(...boxes.map((b) => b.x + b.w));
  const minY = Math.min(...boxes.map((b) => b.y));
  const maxY = Math.max(...boxes.map((b) => b.y + b.h));
  const cX = (minX + maxX) / 2;
  const cY = (minY + maxY) / 2;
  for (const b of boxes) {
    let { x, y } = b;
    switch (mode) {
      case 'left':
        x = minX;
        break;
      case 'right':
        x = maxX - b.w;
        break;
      case 'hcenter':
        x = cX - b.w / 2;
        break;
      case 'top':
        y = minY;
        break;
      case 'bottom':
        y = maxY - b.h;
        break;
      case 'vcenter':
        y = cY - b.h / 2;
        break;
    }
    out.set(b.id, { x: Math.round(x), y: Math.round(y) });
  }
  return out;
}

// 分布: 水平/垂直等距 (按中心)。首尾盒固定, 中间盒中心均匀分布。纯函数, 返回 id -> {x,y}。
// 少于 3 个 -> no-op (无中间盒可分布)。可单测。
export function distributeBoxes(
  boxes: AlignBox[],
  mode: DistributeMode,
): Map<string, { x: number; y: number }> {
  const out = new Map<string, { x: number; y: number }>();
  boxes.forEach((b) => out.set(b.id, { x: b.x, y: b.y }));
  if (boxes.length < 3) return out;
  const horiz = mode === 'h';
  const center = (b: AlignBox) => (horiz ? b.x + b.w / 2 : b.y + b.h / 2);
  const sorted = [...boxes].sort((a, b) => center(a) - center(b));
  const first = center(sorted[0]);
  const last = center(sorted[sorted.length - 1]);
  const step = (last - first) / (sorted.length - 1);
  sorted.forEach((b, i) => {
    if (i === 0 || i === sorted.length - 1) return;
    const target = first + step * i;
    const prev = out.get(b.id) ?? { x: b.x, y: b.y };
    if (horiz) out.set(b.id, { x: Math.round(target - b.w / 2), y: prev.y });
    else out.set(b.id, { x: prev.x, y: Math.round(target - b.h / 2) });
  });
  return out;
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
