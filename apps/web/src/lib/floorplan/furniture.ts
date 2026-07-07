// 家具领域类型 + 工具 — 从 轴测图POC/editor.html【家具】Tab 精确移植。
// B1 后家具用相对键 {room_id, dx, dy}(矩形)/ {room_id, dcx, dcy}(圆形);
// 绝对坐标 = 房间矩形原点 (rect[0],rect[1]) + delta。画布坐标再叠加 origin。

import type { Geometry, Room, Rect } from './types';
import {
  roomById,
  rectsIntersect,
  alignBoxes,
  distributeBoxes,
  groupPrimary,
  type SnapGuide,
  type AlignBox,
  type AlignMode,
  type DistributeMode,
} from './geometry';
import { nextId } from './ids';
import type { CatalogEntry } from 'lib/studioApi';

export type Orient = 'N' | 'S' | 'W' | 'E';

// ---- 家具目录缓存 (P2 前后端同源) ---- //
// /api/catalog 拉取后灌入本模块级缓存, 供同步纯函数 (建件/圆判定/分组) 读取真实默认尺寸
// 与类型清单。缓存未就位时全部回退历史占位值 -> SSR / 首帧 / 单测 (不 fetch) 行为不变。
let _catalogMap: Map<string, CatalogEntry> | null = null;

export function setFurnitureCatalog(entries: CatalogEntry[]): void {
  _catalogMap = new Map(entries.map((e) => [e.t, e]));
}

export function catalogEntry(t: string): CatalogEntry | undefined {
  return _catalogMap?.get(t);
}

export function catalogTypes(): string[] {
  return _catalogMap ? [..._catalogMap.keys()] : [];
}

// 家具库拖入画布的 DnD MIME (阶段 5b / P3): 库项 dragstart 写入类型, 画布 drop 读取。
export const FURN_DND_MIME = 'application/x-gtf-furn';

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
  // 目录标签优先 (引擎新增类型自带 zh), 回退本地词表 (结构件/缓存未就位), 最后类型 key。
  return catalogEntry(t)?.zh ?? FURN_ZH[t] ?? t;
}

// 2D 画布/缩略图填充色: 本地词表优先 (与历史一致), 回退目录 2D 色/3D 基色; 皆无则 undefined
// (调用方自带兜底)。引擎新增类型据此获得合理画布色, 无需在前端补 FURN_COLORS。
export function furnColor(t: string): string | undefined {
  const e = catalogEntry(t);
  return FURN_COLORS[t] ?? e?.color2d ?? e?.color;
}

// ---- 家具库分类 (阶段 5b / P3): 把全部类型按用途归类, 库面板按组展示 ---- //
export interface FurnCategory {
  key: string;
  label: string;
  types: string[];
}

// 显式分组 (覆盖 FURN_COLORS 全部键)。furnCategories() 兜底把未归类的塞入「其他」,
// 保证未来新增类型不丢失。
const FURN_CATEGORY_DEFS: FurnCategory[] = [
  { key: 'bedroom', label: '卧室', types: ['bed', 'nightstand', 'wardrobe'] },
  {
    key: 'living',
    label: '客厅',
    types: [
      'sofa',
      'chaise',
      'chair',
      'swivel_chair',
      'coffee_table',
      'media',
      'bench',
    ],
  },
  {
    key: 'kitchen',
    label: '厨卫',
    types: [
      'kitchen',
      'island',
      'dining_table',
      'round_table',
      'fridge',
      'washer_dryer',
      'vanity',
      'toilet',
      'tub',
      'shower',
    ],
  },
  {
    key: 'storage',
    label: '收纳',
    types: ['cabinet', 'tall_cabinet', 'bookshelf', 'desk'],
  },
  {
    key: 'decor',
    label: '装饰',
    types: ['plant', 'rug', 'partition', 'entry_door'],
  },
];

// 返回完整分类 (含兜底「其他」组收纳未显式归类的类型)。纯函数, 可单测。
// P2: 目录 (catalog) 类型未在静态分组者, 按其 category 归入对应组 -> 引擎新增类型自动
// 现身家具库, 无需改前端。传参优先 (供组件按 hook state 重渲染), 缺省读模块缓存。
export function furnCategories(catalog?: CatalogEntry[]): FurnCategory[] {
  const cat = catalog ?? (_catalogMap ? [..._catalogMap.values()] : []);
  const defs: FurnCategory[] = FURN_CATEGORY_DEFS.map((c) => ({
    ...c,
    types: [...c.types],
  }));
  const byKey = new Map(defs.map((c) => [c.key, c]));
  const placed = new Set<string>();
  defs.forEach((c) => c.types.forEach((t) => placed.add(t)));
  for (const e of cat) {
    if (placed.has(e.t)) continue;
    const grp = byKey.get(e.category);
    if (grp) {
      grp.types.push(e.t);
      placed.add(e.t);
    }
  }
  const others = [...new Set([...FURN_TYPES, ...cat.map((e) => e.t)])].filter(
    (t) => !placed.has(t),
  );
  return others.length
    ? [...defs, { key: 'other', label: '其他', types: others }]
    : defs;
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
  // 异形 (P3): 落点命中组内任一腿 -> 归到组代表, 使整组家具共一稳定 room_id + dx/dy 基点。
  // 非组房 groupPrimary 返回自身, 行为不变。
  const raw = roomAtGeo(g, centerX, centerY);
  const room = raw ? groupPrimary(g, raw) : roomById(g, it.room_id ?? null);
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

// 圆形件判定 (类型层面, 建件用): 目录 shape 优先, 回退本地 CIRCLE_TYPES (缓存未就位/本地件)。
export function isCircleType(t: string): boolean {
  const e = catalogEntry(t);
  if (e) return e.shape === 'round';
  return CIRCLE_TYPES.has(t);
}

// 在指定房间内创建默认家具件 (添加按钮)。落房间中心; 默认尺寸取自目录真实尺寸
// (P2 拖入尺寸真实化), 目录缓存未就位时回退历史占位 (rect 120x60 / circle r22)。
export function buildDefaultFurniture(t: string, room: Room): Furniture {
  const [, , rw, rh] = room.rect;
  const e = catalogEntry(t);
  if (isCircleType(t)) {
    const r = e?.r ?? 22;
    return {
      t,
      id: nextId('f'),
      room_id: room.id,
      dcx: Math.round(rw / 2),
      dcy: Math.round(rh / 2),
      r,
    };
  }
  const fw = e?.w ?? 120;
  const fh = e?.h ?? 60;
  return {
    t,
    id: nextId('f'),
    room_id: room.id,
    dx: Math.max(0, Math.round(rw / 2 - fw / 2)),
    dy: Math.max(0, Math.round(rh / 2 - fh / 2)),
    w: fw,
    h: fh,
    orient: 'N',
  };
}

// 拖入画布落点建件 (阶段 5b / P3): 以默认尺寸建件, 但锚定到落点 (件中心=落点),
// 并夹取到房内。gx/gy 为落点绝对几何坐标 (已去 origin)。纯函数, 可单测。
export function buildFurnitureAt(
  t: string,
  room: Room,
  gx: number,
  gy: number,
): Furniture {
  const base = buildDefaultFurniture(t, room);
  const [rx, ry] = room.rect;
  if (isCircle(base)) {
    const r = base.r ?? 22;
    const c = clampToRoom(room.rect, gx, gy, 0, 0, true, r);
    return {
      ...base,
      dcx: Math.round(c.anchorX - rx),
      dcy: Math.round(c.anchorY - ry),
    };
  }
  const w = base.w ?? 0;
  const h = base.h ?? 0;
  const c = clampToRoom(room.rect, gx - w / 2, gy - h / 2, w, h, false, 0);
  return {
    ...base,
    dx: Math.round(c.anchorX - rx),
    dy: Math.round(c.anchorY - ry),
  };
}

// 家具件包围盒 (几何坐标, 未叠 origin): 供 zoomToSelection (阶段 5b / P2-12)。
export function furnGeoBox(
  it: Furniture,
  g: Geometry,
): { x: number; y: number; w: number; h: number } {
  const a = furnAbs(it, g);
  return { x: a.x, y: a.y, w: a.w, h: a.h };
}

// 保存前校验 (阶段 5b / P2-12): 件中心未落任何房间 -> warning (不阻断保存)。
// 返回 {id, msg}; msg 内含件 id 以便点击定位。纯函数, 可单测。
export function furnitureSaveWarnings(
  items: Furniture[],
  g: Geometry,
): Array<{ id: string; msg: string }> {
  const out: Array<{ id: string; msg: string }> = [];
  for (const it of items) {
    if (!it.id) continue;
    const a = furnAbs(it, g);
    if (!roomAtGeo(g, a.cx, a.cy)) {
      out.push({
        id: it.id,
        msg: `家具 ${furnZh(it.t)}(${it.id}) 中心落在房间外`,
      });
    }
  }
  return out;
}

// 从校验文案定位家具 id (阶段 5b / P2-12): 子串匹配 (家具 id 含连字符, 不可用 token)。
export function locateFurnInMessage(
  items: Furniture[],
  msg: string,
): string | null {
  for (const it of items) {
    if (it.id && msg.includes(it.id)) return it.id;
  }
  return null;
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

// 家具↔家具对齐吸附 (纯函数, 可单测): 被拖件的 左/中/右、上/中/下 与其它家具的对应边
// 在阈值内命中 -> 逐轴取最近命中平移, 并产出跨两者的对齐辅助线。范式同房间 bestSnap +
// rectSnapGuides, 但作用于家具 AABB。box=轴对齐包围盒 {x0,y0,x1,y1,cx,cy}。
export const FURN_ALIGN_SNAP = 6; // 家具间吸附阈值 (几何单位, ≈60mm)

export interface AlignBoxLite {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  cx: number;
  cy: number;
}

export function boxOf(a: FurnAbs): AlignBoxLite {
  return { x0: a.x, y0: a.y, x1: a.x + a.w, y1: a.y + a.h, cx: a.cx, cy: a.cy };
}

export function furnAlignSnap(
  d: AlignBoxLite,
  others: AlignBoxLite[],
  threshold = FURN_ALIGN_SNAP,
): { dx: number; dy: number; guides: SnapGuide[] } {
  // 单轴最近命中: 被拖件三条边对每个 other 三条边求残差, 取阈值内最小者。
  const snap = (dEdges: number[], oEdges: (o: AlignBoxLite) => number[]) => {
    let hit = false;
    let off = 0;
    let cand = 0;
    let err = threshold;
    for (const o of others) {
      for (const oe of oEdges(o)) {
        for (const de of dEdges) {
          const e = Math.abs(oe - de);
          if (e < err - 1e-9) {
            err = e;
            off = oe - de;
            cand = oe;
            hit = true;
          }
        }
      }
    }
    return { hit, off, cand };
  };
  const bx = snap([d.x0, d.cx, d.x1], (o) => [o.x0, o.cx, o.x1]);
  const by = snap([d.y0, d.cy, d.y1], (o) => [o.y0, o.cy, o.y1]);
  const dx = bx.hit ? bx.off : 0;
  const dy = by.hit ? by.off : 0;
  const guides: SnapGuide[] = [];
  if (bx.hit) {
    // 竖向对齐线: 跨"平移后的被拖件"与命中该 x 线的其它家具的 y 范围并集。
    const ys = [d.y0 + dy, d.y1 + dy];
    for (const o of others) {
      if ([o.x0, o.cx, o.x1].some((e) => Math.abs(e - bx.cand) < 1e-6)) {
        ys.push(o.y0, o.y1);
      }
    }
    guides.push({
      axis: 'v',
      pos: bx.cand,
      from: Math.min(...ys),
      to: Math.max(...ys),
    });
  }
  if (by.hit) {
    const xs = [d.x0 + dx, d.x1 + dx];
    for (const o of others) {
      if ([o.y0, o.cy, o.y1].some((e) => Math.abs(e - by.cand) < 1e-6)) {
        xs.push(o.x0, o.x1);
      }
    }
    guides.push({
      axis: 'h',
      pos: by.cand,
      from: Math.min(...xs),
      to: Math.max(...xs),
    });
  }
  return { dx, dy, guides };
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
