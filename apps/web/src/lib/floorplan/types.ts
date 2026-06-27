// 几何编辑器领域类型 — 与引擎 (packages/floorplan_core/geometry.py) 数据契约对齐。
// 坐标单位 1 = 10mm (几何坐标), 画布坐标 = 几何坐标 + origin (见 coords.ts)。

export interface GeometryMeta {
  origin: [number, number];
  mm_per_px: number;
  canvas_viewbox: [number, number, number, number];
  grid?: number;
  eps?: number;
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

export interface Room {
  id: string;
  space: string;
  type: string;
  rect: [number, number, number, number]; // [x, y, w, h] 几何坐标(轴线)
  label?: RoomLabel;
  merge?: string; // 合并组 id (元数据): 同组房间允许净矩形重叠; derive 不读此字段。
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

export interface DerivedDoor {
  id: string;
  kind: string;
  door_type?: string;
  axis: 'h' | 'v';
  at: number;
  span: [number, number];
  hinge?: string;
  swing?: string;
  hinge_pt?: [number, number];
  jamb_pt?: [number, number];
  open_tip?: [number, number];
  width?: number;
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
