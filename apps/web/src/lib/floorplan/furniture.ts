// 家具领域类型 + 工具 — 从 轴测图POC/editor.html【家具】Tab 精确移植。
// B1 后家具用相对键 {room_id, dx, dy}(矩形)/ {room_id, dcx, dcy}(圆形);
// 绝对坐标 = 房间矩形原点 (rect[0],rect[1]) + delta。画布坐标再叠加 origin。

import type { Geometry, Room, Rect } from './types';
import {
  roomById,
  rectsIntersect,
  alignBoxes,
  distributeBoxes,
  type SnapGuide,
  type AlignBox,
  type AlignMode,
  type DistributeMode,
} from './geometry';
import { nextId } from './ids';

export type Orient = 'N' | 'S' | 'W' | 'E';

// 家具件: 同时容纳相对键 (room_id+dx/dy 或 dcx/dcy) 与旧绝对键 (x/y 或 cx/cy)。
// 圆形件以 cx/cy/r 表达 (相对键 dcx/dcy); 矩形件以 x/y/w/h 表达 (相对键 dx/dy)。
export interface Furniture {
  t: string;
  // 稳定运行时 id (阶段 0): 选中/渲染 key/删除均以此为身份, 不再用数组下标。
  // 仅运行时存在; 载入时为无 id 的旧件补齐 (ensureFurnitureIds), 保存时剥离以保
  // 证盘上数据格式 byte 不破 (stripRuntimeFields)。
  id?: string;
  // 相对键 (B1 唯一真源)
  room_id?: string;
  dx?: number;
  dy?: number;
  dcx?: number;
  dcy?: number;
  // 旧绝对键 (向后兼容)
  x?: number;
  y?: number;
  cx?: number;
  cy?: number;
  // 形状尺寸
  w?: number;
  h?: number;
  r?: number;
  // 渲染元数据
  orient?: Orient;
  // 自由旋转角度 (度, P2-2)。orient 决定模型朝向基准, rot 是其上的额外旋转; 缺省/0 = 不旋转
  // (引擎渲染完全 no-op, 保 build byte 不变)。
  rot?: number;
  // z = 引擎家具【挤出高度】(mm)。axon.py m_cab/m_tall/m_washer 等据此出柜体高度
  // (700/850/1050/1550/1780/2000…)。**仅作高度, 不参与叠放排序** (历史曾误复用为叠放键 ->
  // 置底产负值/置顶把矮柜拔到 2010mm, 喂回引擎渲染失真; 现已解耦)。
  z?: number;
  // zorder = 专用【叠放次序键】(P2-13, 与挤出高度 z 解耦)。升序 -> 高 zorder 后画在上层。
  // 缺省按 0 处理; 当前盘上数据无此键 -> 排序为稳定 no-op (保 build byte 不变)。可持久化:
  // 落盘后 render_plan_2d 据同键排序, 使画廊 2D 平面叠放与编辑器一致。
  zorder?: number;
  color?: string;
  label?: string;
  [k: string]: unknown;
}

// 叠放排序键 (P2-13): 读专用 zorder, 升序 -> 高 zorder 后画在上层。无 zorder 视为 0。
// 不读引擎挤出高度 z (二者解耦)。
export function furnZOrder(it: Furniture): number {
  return typeof it.zorder === 'number' ? it.zorder : 0;
}

// 稳定按 zorder 升序排序 (P2-13): Array.prototype.sort 自 ES2019 起稳定, 故 zorder 相等/缺省的件
// 保持原相对次序 -> 对当前 (无 zorder) 数据渲染稳定。返回新数组, 不改入参。
export function sortByZ(items: Furniture[]): Furniture[] {
  return [...items].sort((a, b) => furnZOrder(a) - furnZOrder(b));
}

// 颜色映射 (与 editor.html COL 一致)。rug='none' -> 极淡填充。
export const FURN_COLORS: Record<string, string> = {
  bed: '#e3c9a6',
  sofa: '#d8c19c',
  chaise: '#cdd9e0',
  chair: '#cfe0d4',
  swivel_chair: '#3d5440',
  coffee_table: '#e7d9bb',
  island: '#e7d9bb',
  round_table: '#e7d9bb',
  nightstand: '#ece0c8',
  cabinet: '#ece0c8',
  tall_cabinet: '#ece0c8',
  wardrobe: '#cdb18f',
  bookshelf: '#ece0c8',
  desk: '#ece0c8',
  bench: '#ece0c8',
  dining_table: '#cdb18f',
  kitchen: '#ece0c8',
  fridge: '#cdb18f',
  media: '#cdb18f',
  washer_dryer: '#ececed',
  vanity: '#dde7ec',
  toilet: '#dde7ec',
  tub: '#dde7ec',
  shower: '#cdd9e0',
  plant: '#cfe0cf',
  entry_door: '#433d37',
  partition: '#cccccc',
  rug: 'none',
};

// 类型清单 (下拉)。Object.keys 顺序与 editor.html TYPES 一致。
export const FURN_TYPES = Object.keys(FURN_COLORS);

// 中文名 (2D 标签 / 列表显示, 与 editor.html zh() 一致)。
export const FURN_ZH: Record<string, string> = {
  bed: '床',
  sofa: '沙发',
  chaise: '贵妃',
  chair: '椅',
  swivel_chair: '旋椅',
  coffee_table: '茶几',
  island: '中岛',
  round_table: '圆几',
  nightstand: '床头',
  cabinet: '柜',
  tall_cabinet: '高柜',
  wardrobe: '衣柜',
  bookshelf: '书柜',
  desk: '书桌',
  bench: '凳',
  dining_table: '餐桌',
  kitchen: '橱柜',
  fridge: '冰箱',
  media: '影视',
  washer_dryer: '洗烘',
  vanity: '台盆',
  toilet: '马桶',
  tub: '浴缸',
  shower: '淋浴',
  plant: '绿植',
  entry_door: '入户门',
  partition: '隔墙',
  rug: '地毯',
};

export function furnZh(t: string): string {
  return FURN_ZH[t] ?? t;
}

// 圆形件判定: 有相对圆心键或旧绝对圆心键。
export function isCircle(it: Furniture): boolean {
  return (
    it.dcx !== undefined ||
    it.dcy !== undefined ||
    it.cx !== undefined ||
    it.cy !== undefined
  );
}

// 圆形件默认类型 (添加时落圆形)。与 editor.html addItem 一致。
export const CIRCLE_TYPES = new Set(['plant', 'round_table']);

// 解析后的绝对几何坐标 (尚未叠加 origin)。矩形/圆形字段都给出, 便于统一渲染/命中。
export interface FurnAbs {
  circle: boolean;
  x: number; // 矩形左上 / 圆形包围盒左上
  y: number;
  w: number;
  h: number;
  cx: number; // 中心 (矩形=几何中心, 圆形=圆心)
  cy: number;
  r: number; // 圆形半径 (矩形=0)
}

function roomRectOf(g: Geometry, roomId?: string): Rect | null {
  if (!roomId) return null;
  const r = roomById(g, roomId);
  return r ? r.rect : null;
}

// 家具件 -> 绝对几何坐标 (room.rect 原点 + dx/dy)。旧绝对件 (无 room_id) 原样用 x/y/cx/cy。
// 画布坐标 = 返回值 + origin (由渲染组件叠加, 与 RoomRect 一致)。
export function furnAbs(it: Furniture, g: Geometry): FurnAbs {
  const rect = roomRectOf(g, it.room_id);
  const baseX = rect ? rect[0] : 0;
  const baseY = rect ? rect[1] : 0;
  if (isCircle(it)) {
    const cx = it.dcx !== undefined ? baseX + it.dcx : it.cx ?? 0;
    const cy = it.dcy !== undefined ? baseY + it.dcy : it.cy ?? 0;
    const r = it.r ?? 20;
    return {
      circle: true,
      cx,
      cy,
      r,
      x: cx - r,
      y: cy - r,
      w: 2 * r,
      h: 2 * r,
    };
  }
  const x = it.dx !== undefined ? baseX + it.dx : it.x ?? 0;
  const y = it.dy !== undefined ? baseY + it.dy : it.y ?? 0;
  const w = it.w ?? 0;
  const h = it.h ?? 0;
  return { circle: false, x, y, w, h, cx: x + w / 2, cy: y + h / 2, r: 0 };
}

// 几何坐标命中房间 (point-in-rect, 首个命中)。用于拖动落点反推 room_id。
export function roomAtGeo(g: Geometry, gx: number, gy: number): Room | null {
  for (const r of g.rooms) {
    const [x, y, w, h] = r.rect;
    if (gx >= x && gx <= x + w && gy >= y && gy <= y + h) return r;
  }
  return null;
}

// 拖动落点 -> 新的相对键。anchor 为参考点几何坐标 (矩形=新左上, 圆形=新圆心)。
// center 为命中房间用的中心几何坐标。命中房间则改 room_id; 未命中保留旧 room_id。
// 返回仅含改动键的补丁 (不可变合并由调用方完成)。
export function reanchor(
  it: Furniture,
  g: Geometry,
  anchorX: number,
  anchorY: number,
  centerX: number,
  centerY: number,
): Partial<Furniture> {
  const hit = roomAtGeo(g, centerX, centerY);
  const room = hit ?? roomById(g, it.room_id ?? null);
  const baseX = room ? room.rect[0] : 0;
  const baseY = room ? room.rect[1] : 0;
  const patch: Partial<Furniture> = { room_id: room?.id ?? it.room_id };
  if (isCircle(it)) {
    patch.dcx = Math.round(anchorX - baseX);
    patch.dcy = Math.round(anchorY - baseY);
  } else {
    patch.dx = Math.round(anchorX - baseX);
    patch.dy = Math.round(anchorY - baseY);
  }
  return patch;
}

// 家具拖动对齐辅助线 (P1-4): 纯可视, 不改家具落点。家具件包围盒的左/中/右、上/中/下
// 与所属房间的左/中/右、上/中/下对齐 (容差内) 时产出辅助线, 跨房间整宽/整高。
export function furnSnapGuides(
  it: Furniture,
  g: Geometry,
  a: FurnAbs,
): SnapGuide[] {
  const r = roomById(g, it.room_id ?? null);
  if (!r) return [];
  const EPS = 4;
  const out: SnapGuide[] = [];
  const [rx, ry, rw, rh] = r.rect;
  const rcx = rx + rw / 2;
  const rcy = ry + rh / 2;
  const fx0 = a.x;
  const fx1 = a.x + a.w;
  const fy0 = a.y;
  const fy1 = a.y + a.h;
  for (const t of [rx, rcx, rx + rw]) {
    if (
      Math.abs(fx0 - t) < EPS ||
      Math.abs(a.cx - t) < EPS ||
      Math.abs(fx1 - t) < EPS
    ) {
      out.push({ axis: 'v', pos: t, from: ry, to: ry + rh });
    }
  }
  for (const t of [ry, rcy, ry + rh]) {
    if (
      Math.abs(fy0 - t) < EPS ||
      Math.abs(a.cy - t) < EPS ||
      Math.abs(fy1 - t) < EPS
    ) {
      out.push({ axis: 'h', pos: t, from: rx, to: rx + rw });
    }
  }
  // 去重 (同轴同位置)。
  const seen = new Set<string>();
  return out.filter((gd) => {
    const k = `${gd.axis}:${Math.round(gd.pos)}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

// 在指定房间内创建默认家具件 (添加按钮)。落在房间中心附近, 与 editor.html 默认尺寸一致。
export function buildDefaultFurniture(t: string, room: Room): Furniture {
  const [, , w, h] = room.rect;
  if (CIRCLE_TYPES.has(t)) {
    return {
      t,
      id: nextId('f'),
      room_id: room.id,
      dcx: Math.round(w / 2),
      dcy: Math.round(h / 2),
      r: 22,
    };
  }
  return {
    t,
    id: nextId('f'),
    room_id: room.id,
    dx: Math.max(0, Math.round(w / 2 - 60)),
    dy: Math.max(0, Math.round(h / 2 - 30)),
    w: 120,
    h: 60,
    orient: 'N',
  };
}

// 载入时为无 id 的旧件补齐稳定 id (运行时迁移)。已有 id 的保持不变。不可变返回。
export function ensureFurnitureIds(items: Furniture[]): Furniture[] {
  return items.map((it) => (it.id ? it : { ...it, id: nextId('f') }));
}

// 复制副本 (P2-4): 深拷贝选中件 + 偏移 + 新稳定 id。相对键 (dx/dy 或 dcx/dcy) 优先,
// 退回旧绝对键 (x/y 或 cx/cy)。同房偏移即可 (room_id 不变), 与 editor.html 直觉一致。
export function duplicateFurniture(
  it: Furniture,
  dx: number,
  dy: number,
): Furniture {
  const copy: Furniture = { ...it, id: nextId('f') };
  if (isCircle(it)) {
    if (copy.dcx !== undefined) copy.dcx += dx;
    else if (copy.cx !== undefined) copy.cx += dx;
    if (copy.dcy !== undefined) copy.dcy += dy;
    else if (copy.cy !== undefined) copy.cy += dy;
  } else {
    if (copy.dx !== undefined) copy.dx += dx;
    else if (copy.x !== undefined) copy.x += dx;
    if (copy.dy !== undefined) copy.dy += dy;
    else if (copy.y !== undefined) copy.y += dy;
  }
  return copy;
}

// ---- 缩放手柄 (P2-3): 在件本地 (未旋转) 坐标系内按手柄改 w/h (圆形改 r) ---- //

// 缩放结果: 新尺寸 + 新锚点/中心绝对几何坐标 (供 reanchor 反推 room_id+dx/dy)。
export interface FurnResize {
  w?: number;
  h?: number;
  r?: number;
  anchorX: number; // 矩形=新左上 / 圆形=圆心 (绝对几何坐标)
  anchorY: number;
  centerX: number; // 新中心 (命中房间用)
  centerY: number;
}

const MIN_FURN = 10; // 矩形最小边 (与几何 computeResize 一致)
const MIN_R = 5; // 圆形最小半径

// 把手缩放 (复用 geometry ResizeHandles 8 把手模式)。a=当前绝对几何; circle=是否圆形;
// handle=nw/n/ne/e/se/s/sw/w; (gx,gy)=指针绝对几何坐标; rotDeg=件当前旋转角。
// 计算在件本地 (绕中心反旋 rot) 坐标系内进行: 固定对边, 求新尺寸与中心位移, 再旋回世界。
// rot=0 时退化为轴对齐缩放 (固定对边)。纯函数, 可单测。
export function computeFurnResize(
  a: FurnAbs,
  circle: boolean,
  handle: string,
  gx: number,
  gy: number,
  rotDeg: number,
): FurnResize {
  const rad = (rotDeg * Math.PI) / 180;
  const cosr = Math.cos(rad);
  const sinr = Math.sin(rad);
  // 指针相对中心, 反旋 rad -> 本地坐标。
  const px = gx - a.cx;
  const py = gy - a.cy;
  const lx = px * cosr + py * sinr;
  const ly = -px * sinr + py * cosr;

  if (circle) {
    const nr = Math.max(MIN_R, Math.round(Math.hypot(lx, ly)));
    return {
      r: nr,
      anchorX: a.cx,
      anchorY: a.cy,
      centerX: a.cx,
      centerY: a.cy,
    };
  }

  // 本地矩形以中心为原点: 边在 ±w/2, ±h/2。按手柄改动对应边, 固定对边。
  let L = -a.w / 2;
  let R = a.w / 2;
  let T = -a.h / 2;
  let B = a.h / 2;
  if (handle.includes('w')) L = lx;
  if (handle.includes('e')) R = lx;
  if (handle.includes('n')) T = ly;
  if (handle.includes('s')) B = ly;
  const x0 = Math.min(L, R);
  const x1 = Math.max(L, R);
  const y0 = Math.min(T, B);
  const y1 = Math.max(T, B);
  const nW = Math.max(MIN_FURN, Math.round(x1 - x0));
  const nH = Math.max(MIN_FURN, Math.round(y1 - y0));
  // 新本地中心 (相对旧中心) -> 旋回世界 -> 新世界中心。
  const lcx = (x0 + x1) / 2;
  const lcy = (y0 + y1) / 2;
  const wcx = lcx * cosr - lcy * sinr;
  const wcy = lcx * sinr + lcy * cosr;
  const centerX = a.cx + wcx;
  const centerY = a.cy + wcy;
  return {
    w: nW,
    h: nH,
    anchorX: centerX - nW / 2,
    anchorY: centerY - nH / 2,
    centerX,
    centerY,
  };
}

// ---- 旋转 (P2-2): 指针角 -> rot, 15° 吸附 (Shift 自由) ---- //

// 旋转柄在件"上方" (本地 -Y); 指针绕中心的角度 + 90° = 件应转到的角。free=true 关吸附。
// 归一化到 [0,360)。纯函数, 可单测。
export function computeRotation(
  cx: number,
  cy: number,
  gx: number,
  gy: number,
  free: boolean,
): number {
  let deg = (Math.atan2(gy - cy, gx - cx) * 180) / Math.PI + 90;
  if (!free) deg = Math.round(deg / 15) * 15; // 15° 吸附 (含 45/90 等)
  deg = ((deg % 360) + 360) % 360;
  return deg;
}

// ---- 贴墙吸附 + 越界约束 (P2-5) ---- //

// 把锚点夹取到房间内 (矩形件: 整包围盒留在房内; 圆形件: 圆心留 r 内缩)。clamped=是否触发夹取。
// 房间小于件时退化为贴左上 (clamp 到房左上)。纯函数, 可单测。
export function clampToRoom(
  rect: Rect,
  anchorX: number,
  anchorY: number,
  w: number,
  h: number,
  circle: boolean,
  r: number,
): { anchorX: number; anchorY: number; clamped: boolean } {
  const [rx, ry, rw, rh] = rect;
  let ax = anchorX;
  let ay = anchorY;
  if (circle) {
    const loX = rx + r;
    const hiX = rx + rw - r;
    const loY = ry + r;
    const hiY = ry + rh - r;
    ax = hiX >= loX ? Math.min(hiX, Math.max(loX, anchorX)) : rx + rw / 2;
    ay = hiY >= loY ? Math.min(hiY, Math.max(loY, anchorY)) : ry + rh / 2;
  } else {
    const hiX = rx + rw - w;
    const hiY = ry + rh - h;
    ax = hiX >= rx ? Math.min(hiX, Math.max(rx, anchorX)) : rx;
    ay = hiY >= ry ? Math.min(hiY, Math.max(ry, anchorY)) : ry;
  }
  return {
    anchorX: ax,
    anchorY: ay,
    clamped: ax !== anchorX || ay !== anchorY,
  };
}

const WALL_SNAP = 8; // 贴墙吸附阈值 (与几何 SNAP 一致)

// 近墙阈值内把件吸附贴墙 (矩形件按四边; 圆形件按圆心到墙距)。不改 orient, 仅平移锚点。
// 纯函数, 可单测。
export function snapToWall(
  rect: Rect,
  anchorX: number,
  anchorY: number,
  w: number,
  h: number,
  circle: boolean,
  r: number,
): { anchorX: number; anchorY: number } {
  const [rx, ry, rw, rh] = rect;
  let ax = anchorX;
  let ay = anchorY;
  if (circle) {
    if (Math.abs(anchorX - r - rx) < WALL_SNAP) ax = rx + r;
    else if (Math.abs(rx + rw - (anchorX + r)) < WALL_SNAP) ax = rx + rw - r;
    if (Math.abs(anchorY - r - ry) < WALL_SNAP) ay = ry + r;
    else if (Math.abs(ry + rh - (anchorY + r)) < WALL_SNAP) ay = ry + rh - r;
  } else {
    if (Math.abs(anchorX - rx) < WALL_SNAP) ax = rx;
    else if (Math.abs(rx + rw - (anchorX + w)) < WALL_SNAP) ax = rx + rw - w;
    if (Math.abs(anchorY - ry) < WALL_SNAP) ay = ry;
    else if (Math.abs(ry + rh - (anchorY + h)) < WALL_SNAP) ay = ry + rh - h;
  }
  return { anchorX: ax, anchorY: ay };
}

// ---- z-order 置顶/置底 (P2-13): 写专用 zorder, 与引擎挤出高度 z 解耦 ---- //

const ZORDER_STEP = 10;

// 选中件置顶: zorder = 【其他件】最大 zorder + STEP (相对其余件, 不掺入自身/高度 z)。
// 无其他件时归 0。返回新 zorder (高 zorder = 后画在上层)。
export function bringToFrontZ(items: Furniture[], selId: string): number {
  const others = items.filter((it) => it.id !== selId);
  if (others.length === 0) return 0;
  const max = others.reduce((m, it) => Math.max(m, furnZOrder(it)), 0);
  return max + ZORDER_STEP;
}

// 选中件置底: zorder = 【其他件】最小 zorder - STEP, 夹取 >=0 (不产负值, 保盘上数据干净)。
export function sendToBackZ(items: Furniture[], selId: string): number {
  const others = items.filter((it) => it.id !== selId);
  if (others.length === 0) return 0;
  const min = others.reduce((m, it) => Math.min(m, furnZOrder(it)), 0);
  return Math.max(0, min - ZORDER_STEP);
}

// ---- 多选: 框选 / 对齐 / 分布 (阶段 5a / P2-7) ---- //

// marquee 矩形 (几何坐标) 框选: 返回包围盒与之相交的件 id。纯函数, 可单测。
export function furnInMarquee(
  items: Furniture[],
  g: Geometry,
  rect: Rect,
): string[] {
  const out: string[] = [];
  for (const it of items) {
    if (!it.id) continue;
    const a = furnAbs(it, g);
    if (rectsIntersect([a.x, a.y, a.w, a.h], rect)) out.push(it.id);
  }
  return out;
}

// 选中件 -> 对齐/分布包围盒 (供通用 alignBoxes/distributeBoxes)。
function furnAlignBoxes(items: Furniture[], g: Geometry): AlignBox[] {
  return items
    .filter((it): it is Furniture & { id: string } => !!it.id)
    .map((it) => {
      const a = furnAbs(it, g);
      return { id: it.id, x: a.x, y: a.y, w: a.w, h: a.h };
    });
}

// 据新左上 (x,y) 反推各件相对键补丁 (reanchor)。矩形件锚=左上; 圆形件锚=中心。
function furnPatchesFromPos(
  items: Furniture[],
  g: Geometry,
  pos: Map<string, { x: number; y: number }>,
): Map<string, Partial<Furniture>> {
  const out = new Map<string, Partial<Furniture>>();
  for (const it of items) {
    if (!it.id) continue;
    const p = pos.get(it.id);
    if (!p) continue;
    const a = furnAbs(it, g);
    if (isCircle(it)) {
      const cx = p.x + a.r;
      const cy = p.y + a.r;
      out.set(it.id, reanchor(it, g, cx, cy, cx, cy));
    } else {
      const cx = p.x + a.w / 2;
      const cy = p.y + a.h / 2;
      out.set(it.id, reanchor(it, g, p.x, p.y, cx, cy));
    }
  }
  return out;
}

// 多选对齐 (P2-7): 选中件按 mode 对齐, 返回 id -> 相对键补丁。入口在 hook 合并入历史一帧。纯函数。
export function furnAlignPatches(
  items: Furniture[],
  g: Geometry,
  mode: AlignMode,
): Map<string, Partial<Furniture>> {
  return furnPatchesFromPos(
    items,
    g,
    alignBoxes(furnAlignBoxes(items, g), mode),
  );
}

// 多选分布 (P2-7): 选中件水平/垂直等距, 返回 id -> 相对键补丁。纯函数。
export function furnDistributePatches(
  items: Furniture[],
  g: Geometry,
  mode: DistributeMode,
): Map<string, Partial<Furniture>> {
  return furnPatchesFromPos(
    items,
    g,
    distributeBoxes(furnAlignBoxes(items, g), mode),
  );
}

// 保存前剥离运行时字段 (id), 保证 save-furniture 往返与盘上数据 byte 不破。
export function stripRuntimeFields(items: Furniture[]): Furniture[] {
  return items.map((it) => {
    if (it.id === undefined) return it;
    const { id: _id, ...rest } = it;
    return rest;
  });
}
