// 几何编辑器领域类型 — 与引擎 (packages/floorplan_core/geometry.py) 数据契约对齐。
// 坐标单位 1 = 10mm (几何坐标), 画布坐标 = 几何坐标 + origin (见 coords.ts)。

// 底图描摹 (P6): 参考底图 (实拍/CAD) 在编辑器画布下方半透明叠放, 供描摹。引擎不读
// meta.underlay -> plan2d/shell 字节不受影响。scale/dx/dy 把图像贴到 10mm/px 网格。
export interface UnderlayMeta {
  photo_id?: string;
  url?: string;
  opacity: number; // 0.1–0.9
  scale: number; // 图像原始 px -> 几何 px 的缩放
  dx: number; // 几何坐标左上偏移
  dy: number;
}

export interface GeometryMeta {
  origin: [number, number];
  mm_per_px: number;
  canvas_viewbox: [number, number, number, number];
  grid?: number;
  eps?: number;
  underlay?: UnderlayMeta;
  [k: string]: unknown;
}

export interface SpaceDef {
  category: string;
  label: string;
  style?: string;
  [k: string]: unknown;
}

export interface RoomLabel {
  zh?: string;
  at?: [number, number];
  style?: string;
  [k: string]: unknown;
}

// 并房前原 space 快照 (CP5v2 编辑器元数据): 「分隔」时还原原名称/类别; 引擎不读此键。
export interface PrevSpace {
  id: string; // 原 space id: 分隔还原时优先复用, 使开洞 between 引用保持一致。
  label: string;
  category: string;
  style?: string;
}

export interface Room {
  id: string;
  space: string;
  type: string;
  rect: [number, number, number, number]; // [x, y, w, h] 几何坐标(轴线)
  label?: RoomLabel;
  merge?: string; // 合并组 id (元数据): 同组房间允许净矩形重叠; derive 不读此字段。
  prev_space?: PrevSpace; // 并房前原 space 快照 (CP5v2): 仅编辑器读写。
  [k: string]: unknown;
}

// 开洞宿主墙定位 (沿墙滑块): axis/at/span 几何坐标。
export interface OpeningWall {
  axis: 'h' | 'v';
  at: number;
  span: [number, number];
}

export interface Opening {
  id: string;
  kind: 'door' | 'window' | 'passage';
  wall: OpeningWall;
  door_type?: 'swing' | 'sliding' | 'double';
  hinge?: 'lo' | 'hi';
  swing?: '+' | '-';
  // 门材质 (P5 门批次): 缺省 wood (不写键, 保盘上字节不变); glass 复用窗玻璃配方。
  material?: 'wood' | 'glass';
  wtype?: 'normal' | 'full' | 'high';
  cut?: boolean;
  between?: [string, string];
  panels?: number;
  [k: string]: unknown;
}

export interface FreeWall {
  id: string;
  axis: 'h' | 'v';
  at: number;
  span: [number, number];
  role: string;
  style?: string;
  [k: string]: unknown;
}

export interface Geometry {
  meta: GeometryMeta;
  spaces: Record<string, SpaceDef>;
  rooms: Room[];
  openings: Opening[];
  free_walls?: FreeWall[];
  annotations?: unknown;
  dims?: unknown;
  [k: string]: unknown;
}

// 派生墙 dict 形式 (_walls_raw): 渲染叠加层用。style 可为 null。
export interface WallRaw {
  axis: 'h' | 'v';
  at: number;
  lo: number;
  hi: number;
  role: string;
  style: string | null;
  ext?: boolean;
}

// 派生墙 tuple:[ax, ay, bx, by, ext, style, lowz]
export type WallTuple = [
  number,
  number,
  number,
  number,
  boolean,
  string,
  boolean,
];

// 对开双扇的单扇 (P5): 引擎 build_door double -> leaves[]。
export interface DerivedLeaf {
  hinge_pt: [number, number];
  jamb_pt: [number, number];
  open_tip: [number, number];
  width: number;
}

export interface DerivedDoor {
  id: string;
  kind: string;
  door_type?: string;
  material?: string; // P5: 'wood'(默认) | 'glass'
  axis: 'h' | 'v';
  at: number;
  span: [number, number];
  hinge?: string;
  swing?: string;
  hinge_pt?: [number, number];
  jamb_pt?: [number, number];
  open_tip?: [number, number];
  width?: number;
  leaves?: DerivedLeaf[]; // P5 对开双扇: 两扇
  panels?: number;
  [k: string]: unknown;
}

export interface DerivedWindow {
  id: string;
  kind: string;
  wtype?: string;
  axis: 'h' | 'v';
  at: number;
  span: [number, number];
  cut?: boolean;
  [k: string]: unknown;
}

export interface DeriveResult {
  walls: WallTuple[];
  doors: DerivedDoor[];
  windows: DerivedWindow[];
  dims: Record<string, unknown>;
  conflicts: string[];
  warns: string[];
  _walls_raw: WallRaw[];
}

export interface SaveGeometryResult {
  ok: boolean;
  warns: string[];
  errors?: string[];
  derived?: DeriveResult;
}

// 房间矩形别名, 用于纯几何函数。
export type Rect = [number, number, number, number];
