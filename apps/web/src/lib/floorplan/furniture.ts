// 家具领域类型 + 工具 — 从 轴测图POC/editor.html【家具】Tab 精确移植。
// B1 后家具用相对键 {room_id, dx, dy}(矩形)/ {room_id, dcx, dcy}(圆形);
// 绝对坐标 = 房间矩形原点 (rect[0],rect[1]) + delta。画布坐标再叠加 origin。

import type { Geometry, Room, Rect } from './types';
import { roomById, type SnapGuide } from './geometry';
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
  z?: number;
  color?: string;
  label?: string;
  [k: string]: unknown;
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

// 保存前剥离运行时字段 (id), 保证 save-furniture 往返与盘上数据 byte 不破。
export function stripRuntimeFields(items: Furniture[]): Furniture[] {
  return items.map((it) => {
    if (it.id === undefined) return it;
    const { id: _id, ...rest } = it;
    return rest;
  });
}
