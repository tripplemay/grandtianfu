// 同源数据层:全程 baseURL='/api'(dev 经 next.config rewrites 代理到 FastAPI;
// prod 路 A 由 nginx 把 /api 转给 api 容器)。不开 CORS。
// 统一信封约定 { success, data, error };同时兼容引擎直出的裸对象(parity 基准)。

import type { Plan2dPart } from './floorplan/furnShapes';

export const API_BASE = '/api';

export interface GeometryMeta {
  origin: [number, number];
  mm_per_px: number;
  canvas_viewbox: [number, number, number, number];
  [k: string]: unknown;
}

export interface Geometry {
  meta: GeometryMeta;
  [k: string]: unknown;
}

// 派生墙 tuple:[ax, ay, bx, by, ext, style, lowz](几何坐标,需加 origin 偏移)
export type WallTuple = [
  number,
  number,
  number,
  number,
  boolean,
  string,
  boolean,
];

export interface DeriveResult {
  walls: WallTuple[];
  doors: unknown[];
  windows: unknown[];
  dims: Record<string, unknown>;
  conflicts: string[];
  warns: string[];
}

interface Envelope<T> {
  success?: boolean;
  data?: T;
  error?: string;
}

async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as Envelope<T> & { detail?: string };
      detail = body.error || body.detail || detail;
    } catch {
      /* 非 JSON 错误体,沿用状态行 */
    }
    throw new Error(detail);
  }
  const body = (await res.json()) as Envelope<T> | T;
  if (body && typeof body === 'object' && 'success' in (body as object)) {
    const env = body as Envelope<T>;
    if (env.success === false) throw new Error(env.error || 'request failed');
    return env.data as T;
  }
  return body as T;
}

// 家具目录 (P2 前后端同源): /api/catalog 单一真源 —— 前端家具库据此出类型清单 +
// 真实默认尺寸 + 分组, 新增类型只需改引擎 catalog.py, 前端无需再改硬编码词表。
export interface CatalogEntry {
  t: string;
  en: string;
  shape: 'rect' | 'round';
  w?: number;
  h?: number;
  r?: number;
  z?: number;
  color?: string;
  rooms: string[];
  zh: string;
  category: string;
  color2d?: string; // 2D 平面/编辑器画布填充色 (前端缩略图/画布)
  tall?: boolean;
  directional?: boolean;
  swap_group?: string; // 换件分组 (Phase C): 换件下拉在同组内约束
  plan2d_spec?: Plan2dPart[]; // 声明式俯视外形 (Phase C-3): 画布/平面图内部细节
}

export interface CatalogResponse {
  rev: number;
  types: CatalogEntry[];
}

export async function fetchCatalog(): Promise<CatalogResponse> {
  const res = await fetch(`${API_BASE}/catalog`, {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  return unwrap<CatalogResponse>(res);
}

// 项目台 (Stage C): 项目列表 / 新建 / 删除。同源 /api, 不开 CORS。
export interface ProjectSummary {
  id: string;
  name: string;
  rooms: number;
}

export interface ProjectMeta {
  id: string;
  name: string;
  current_baseline_version_id: string | null;
  next_baseline_version?: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export type BaselineStatus = 'draft' | 'confirmed' | 'superseded';

export interface BaselineMeta {
  id: string;
  status: BaselineStatus;
  validation_issues?: Array<{ level: string; message: string }>;
  source_version_id?: string | null;
  created_at?: string | null;
  confirmed_at?: string | null;
  superseded_at?: string | null;
}

export async function listProjects(): Promise<ProjectSummary[]> {
  const res = await fetch(`${API_BASE}/projects`, {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  return unwrap<ProjectSummary[]>(res);
}

export async function createProject(
  id: string,
  name: string,
): Promise<ProjectSummary> {
  const res = await fetch(`${API_BASE}/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ id, name }),
  });
  return unwrap<ProjectSummary>(res);
}

export async function deleteProject(id: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  });
  return unwrap<{ ok: boolean }>(res);
}

export async function fetchProject(projectId: string): Promise<ProjectMeta> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}`,
    {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    },
  );
  return unwrap<ProjectMeta>(res);
}

// P0-1: 户型版本"可生成质量"评估 (后端权威, 前端不再自行派生)。
export interface ReadinessItem {
  code: string;
  message: string;
  room_id?: string | null;
  fix?: 'editor' | 'baseline' | string;
}
export interface BaselineReadiness {
  ok: boolean;
  blocking: ReadinessItem[];
  warning: ReadinessItem[];
  summary: {
    has_geometry?: boolean;
    furniture_count?: number;
    scene_ok?: boolean;
    photos_total?: number;
    photos_ready?: number;
    photos_calibrated?: number;
  };
}

export async function getBaselineReadiness(
  projectId: string,
  versionId: string,
): Promise<BaselineReadiness> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(
      projectId,
    )}/baselines/${encodeURIComponent(versionId)}/readiness`,
    { cache: 'no-store', headers: { Accept: 'application/json' } },
  );
  return unwrap<BaselineReadiness>(res);
}

export async function listBaselines(
  projectId: string,
): Promise<BaselineMeta[]> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}/baselines`,
    { cache: 'no-store', headers: { Accept: 'application/json' } },
  );
  return unwrap<BaselineMeta[]>(res);
}

export async function createBaseline(
  projectId: string,
  sourceVersionId: string,
): Promise<BaselineMeta> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}/baselines`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({ source_version_id: sourceVersionId }),
    },
  );
  return unwrap<BaselineMeta>(res);
}

export async function confirmBaseline(
  projectId: string,
  versionId: string,
): Promise<{ ok: boolean; project: ProjectMeta; baseline: BaselineMeta }> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(
      projectId,
    )}/baselines/${encodeURIComponent(versionId)}/confirm`,
    { method: 'POST', headers: { Accept: 'application/json' } },
  );
  return unwrap<{ ok: boolean; project: ProjectMeta; baseline: BaselineMeta }>(
    res,
  );
}

// 软删户型版本 (级联绑定方案入回收站)。当前已确认版本/最后一版由后端 409 保护,
// 非 ok 时 unwrap 抛出后端 error 文案供 UI 展示。
export async function deleteBaseline(
  projectId: string,
  versionId: string,
): Promise<{ ok: boolean; trashed?: string; schemes_trashed?: string[] }> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(
      projectId,
    )}/baselines/${encodeURIComponent(versionId)}`,
    { method: 'DELETE', headers: { Accept: 'application/json' } },
  );
  return unwrap<{
    ok: boolean;
    trashed?: string;
    schemes_trashed?: string[];
  }>(res);
}

export async function fetchBaselineGeometry(
  projectId: string,
  versionId: string,
): Promise<Geometry> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(
      projectId,
    )}/baselines/${encodeURIComponent(versionId)}/geometry`,
    { cache: 'no-store', headers: { Accept: 'application/json' } },
  );
  return unwrap<Geometry>(res);
}

// ---- 第6步: 空房照片 (绑定户型版本, 不绑定方案) ---- //

// 工作流改造 (B5): 服务器派生的照片质量评分 (上传归一化时算, 只读)。
export interface PhotoQuality {
  score: number; // 0-100 (= 100 - 25*告警数)
  warnings: string[]; // low_res | extreme_aspect | too_dark | too_bright | blurry
  brightness?: number;
  sharpness?: number;
  megapixels?: number;
}

// P2b 透视标定 (几何锁定实拍): 用户在空房照上标出的两组正交地面墙线 + >=2 个已知地面角。
// 世界系: 单位 mm, X=东(+), Y=南(+), Z=上(+), 地面 z=0。像素端点均为照片原始像素 (naturalW/H)。
export type CalibrationLine = [[number, number], [number, number]];
export interface CalibrationAnchor {
  world: [number, number, number]; // 世界 mm [X, Y, Z(=0)]
  px: [number, number]; // 照片原始像素 [u, v]
}
export interface CalibrationPayload {
  x_lines: CalibrationLine[]; // 沿世界 X 方向 (南墙/落地窗水平边) 的 >=2 条平行线
  y_lines: CalibrationLine[]; // 沿世界 Y 方向 (东墙/电视墙水平边) 的 >=2 条平行线
  anchors: CalibrationAnchor[]; // >=2 个已知地面角
  img_wh: [number, number]; // 照片原始像素尺寸 [naturalWidth, naturalHeight]
}
// 存盘态 = 入参 + 反解出的相机 (camera 由后端计算, 前端只读其存在性)。
export interface PhotoCalibration extends CalibrationPayload {
  camera?: Record<string, unknown>;
}

// calib-cure-b1 F002: 标定 dry-run 预览响应 (spec §D4)。质量评级与阈值由后端单一真源
// 判定 (good=reproj<25px 且无 reasons / suspect=25-50px 或有软信号 / bad=硬门命中即
// quality.ok=false), 前端只消费 level/reasons, 不复算阈值。
export interface CalibrationQualityMetrics {
  reproj_px: number;
  camera_z_mm: number;
  camera_room_dist_mm: number;
  hfov_deg: number;
}
export interface CalibrationQuality {
  ok: boolean; // false = 坏标定 (真保存会被后端 400 BAD_CALIBRATION 拒绝)
  level: 'good' | 'suspect' | 'bad';
  reasons: string[];
  metrics: CalibrationQualityMetrics;
}
// 标定房 merge 组每成员房间的投影线框: 地面 z=0 / 天花 z=2700 各 4 角 (NW/NE/SE/SW 序),
// 照片原始像素 [u,v]。叠回照片供用户核对"推算轮廓 vs 实际墙线"。
export interface CalibrationWireframeRoom {
  room_id: string;
  floor: [number, number][];
  ceiling: [number, number][];
}
export interface CalibrationPreviewResult {
  ok: boolean; // 恒 true (解算失败后端直接 400, unwrap 抛错)
  camera: Record<string, unknown>;
  reprojection_error: number;
  quality: CalibrationQuality;
  wireframe: CalibrationWireframeRoom[];
}

export interface BaselinePhoto {
  id: string;
  url: string;
  thumb_url?: string | null;
  room_id?: string | null;
  direction?: string | null;
  note?: string | null;
  purpose?: string | null; // P2 材质C: 'wall_material' = 墙面实拍参考; 缺省/'empty' = 空房底图
  quality?: PhotoQuality | null; // B5: 照片可用性评分 (只读)
  calibration?: PhotoCalibration | null; // P2b: 透视标定 (存在则实拍走几何锁定路径)
  calibration_stale?: boolean; // P0-5: 标定所依赖的房间/几何/图像已变更 -> 需重新标定 (只读派生)
  created_at?: string;
  updated_at?: string;
}

function photosPath(projectId: string, versionId: string): string {
  return `${API_BASE}/projects/${encodeURIComponent(
    projectId,
  )}/baselines/${encodeURIComponent(versionId)}/photos`;
}

export async function listBaselinePhotos(
  projectId: string,
  versionId: string,
): Promise<BaselinePhoto[]> {
  const res = await fetch(photosPath(projectId, versionId), {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  return unwrap<BaselinePhoto[]>(res);
}

export async function uploadBaselinePhoto(
  projectId: string,
  versionId: string,
  file: File,
  fields?: {
    room_id?: string;
    direction?: string;
    note?: string;
    purpose?: string;
  },
): Promise<BaselinePhoto> {
  const form = new FormData();
  form.append('file', file);
  for (const [key, value] of Object.entries(fields ?? {})) {
    if (value) form.append(key, value);
  }
  const res = await fetch(photosPath(projectId, versionId), {
    method: 'POST',
    body: form,
    headers: { Accept: 'application/json' },
  });
  return unwrap<BaselinePhoto>(res);
}

export async function patchBaselinePhoto(
  projectId: string,
  versionId: string,
  photoId: string,
  fields: {
    room_id?: string | null;
    direction?: string | null;
    note?: string | null;
  },
): Promise<BaselinePhoto> {
  const res = await fetch(
    `${photosPath(projectId, versionId)}/${encodeURIComponent(photoId)}`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(fields),
    },
  );
  return unwrap<BaselinePhoto>(res);
}

// P2b 透视标定: 提交两组正交墙线 + >=2 锚点 + img_wh -> 后端反解相机并存照片记录。
// 成功返回更新后的 photo (含 calibration); 400 表示校验/标定失败 (unwrap 抛后端 error 文案)。
export async function setPhotoCalibration(
  projectId: string,
  versionId: string,
  photoId: string,
  payload: CalibrationPayload,
): Promise<BaselinePhoto> {
  const res = await fetch(
    `${photosPath(projectId, versionId)}/${encodeURIComponent(
      photoId,
    )}/calibration`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(payload),
    },
  );
  return unwrap<BaselinePhoto>(res);
}

// calib-cure-b1 F002: 标定 dry-run 预览 —— 同 payload 只解算不落盘 (GEOM_READONLY 下同样
// 可用), 返回相机/重投影误差/质量评级/线框投影, 供「确认保存」前叠照片核对 (spec §D4)。
// 解算失败 400 由 unwrap 抛后端 error 文案; 质量 bad 也返回 200 (前端要画出"有多歪")。
export async function previewPhotoCalibration(
  projectId: string,
  versionId: string,
  photoId: string,
  payload: CalibrationPayload,
): Promise<CalibrationPreviewResult> {
  const res = await fetch(
    `${photosPath(projectId, versionId)}/${encodeURIComponent(
      photoId,
    )}/calibration?dry_run=1`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(payload),
    },
  );
  return unwrap<CalibrationPreviewResult>(res);
}

// calib-cure-b1 F007: 清除透视标定 —— 坏标定的自助出口 (有标定就优先走几何锁定,
// 坏标定比没标定更糟)。幂等; 删后照片回退未标定态。
export async function deletePhotoCalibration(
  projectId: string,
  versionId: string,
  photoId: string,
): Promise<{ ok: boolean; removed?: boolean }> {
  const res = await fetch(
    `${photosPath(projectId, versionId)}/${encodeURIComponent(
      photoId,
    )}/calibration`,
    { method: 'DELETE', headers: { Accept: 'application/json' } },
  );
  return unwrap<{ ok: boolean; removed?: boolean }>(res);
}

export async function deleteBaselinePhoto(
  projectId: string,
  versionId: string,
  photoId: string,
): Promise<{ ok: boolean }> {
  const res = await fetch(
    `${photosPath(projectId, versionId)}/${encodeURIComponent(photoId)}`,
    { method: 'DELETE', headers: { Accept: 'application/json' } },
  );
  return unwrap<{ ok: boolean }>(res);
}

export async function saveBaselineGeometry(
  projectId: string,
  versionId: string,
  geometry: Geometry,
): Promise<SaveGeometryResponse> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(
      projectId,
    )}/baselines/${encodeURIComponent(versionId)}/save-geometry`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(geometry),
    },
  );
  let body: Partial<SaveGeometryResponse> & { error?: string } = {};
  try {
    body = (await res.json()) as Partial<SaveGeometryResponse>;
  } catch {
    /* 非 JSON 错误体 */
  }
  if (!res.ok) {
    return {
      ok: false,
      warns: body.warns ?? [],
      errors: body.errors ?? [body.error || `${res.status} ${res.statusText}`],
    };
  }
  return {
    ok: body.ok ?? true,
    warns: body.warns ?? [],
    errors: body.errors,
    derived: body.derived,
  };
}

export async function fetchGeometry(projectId: string): Promise<Geometry> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}/geometry`,
    {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    },
  );
  return unwrap<Geometry>(res);
}

// 家具读写 (B2): 后端返回 / 接收裸数组 (相对键 {room_id,dx,dy})。同源 /api, 不开 CORS。
export type FurnitureItem = Record<string, unknown>;

const DEFAULT_SCHEME_ID = 'default';

function schemePath(projectId: string, schemeId?: string): string {
  const pid = encodeURIComponent(projectId);
  const sid = encodeURIComponent(schemeId || DEFAULT_SCHEME_ID);
  return `${API_BASE}/projects/${pid}/schemes/${sid}`;
}

export async function fetchFurniture(
  projectId: string,
  schemeId?: string,
): Promise<FurnitureItem[]> {
  const url =
    !schemeId || schemeId === DEFAULT_SCHEME_ID
      ? `${API_BASE}/projects/${encodeURIComponent(projectId)}/furniture`
      : `${schemePath(projectId, schemeId)}/furniture`;
  const res = await fetch(url, {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  return unwrap<FurnitureItem[]>(res);
}

// 基线标准布局家具 (Phase A: 家具下沉基线)。草稿版本编辑器读写这里而非方案。
export async function fetchBaselineFurniture(
  projectId: string,
  versionId: string,
): Promise<FurnitureItem[]> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(
      projectId,
    )}/baselines/${encodeURIComponent(versionId)}/furniture`,
    { cache: 'no-store', headers: { Accept: 'application/json' } },
  );
  return unwrap<FurnitureItem[]>(res);
}

export async function saveBaselineFurniture(
  projectId: string,
  versionId: string,
  furniture: FurnitureItem[],
): Promise<SaveFurnitureResponse> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(
      projectId,
    )}/baselines/${encodeURIComponent(versionId)}/save-furniture`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(furniture),
    },
  );
  return unwrap<SaveFurnitureResponse>(res);
}

export interface SaveFurnitureResponse {
  ok: boolean;
}

export async function saveFurniture(
  projectId: string,
  furniture: FurnitureItem[],
  schemeId?: string,
): Promise<SaveFurnitureResponse> {
  const url =
    !schemeId || schemeId === DEFAULT_SCHEME_ID
      ? `${API_BASE}/projects/${encodeURIComponent(projectId)}/save-furniture`
      : `${schemePath(projectId, schemeId)}/save-furniture`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(furniture),
  });
  return unwrap<SaveFurnitureResponse>(res);
}

export type SchemeSource =
  | 'legacy'
  | 'manual'
  | 'duplicate'
  | 'ai'
  | 'migrated';
export type SchemeStatus = 'draft' | 'confirmed' | 'archived';

// 工作流改造 (B3): 结构化设计 Brief —— 把自由文本需求结构化, 后端编译进轴测/实拍 prompt。
// 全部可选; 后端 _normalize_brief 去空白/丢空值, 全空 -> null。
export interface SchemeBrief {
  occupants?: string;
  budget_tier?: string;
  style_direction?: string;
  keep_hardscape?: boolean;
  primary_materials?: string[];
  banned_materials?: string[];
  primary_colors?: string[];
  banned_colors?: string[];
  focus_rooms?: string[];
  avoid_elements?: string[];
  // decor-b2 F005: 配饰偏好 (多/少配饰、偏好挂画/绿植/摆件等)。后端 brief_prompt.compile_brief
  // 编译为 "soft furnishing preferences: ..." 进出图 prompt。
  decor_preferences?: string[];
}

export interface FurnitureSchemeSummary {
  id: string;
  name: string;
  source: SchemeSource;
  style_prompt?: string;
  brief?: SchemeBrief | null;
  status: SchemeStatus;
  baseline_version_id?: string;
  preferred?: boolean;
  archived_at?: string | null;
  items: number;
  renders: number;
  // 工作流改造 (F): 按 mode 拆分的计数 + 实拍验收标记, 供概览 stepper 第 4/6/7 步 done 判定。
  axon_render_count?: number;
  real_render_count?: number;
  has_accepted_real?: boolean;
  has_confirmed_axon?: boolean; // B4: 存在被确认为方案参考的轴测出图

  latest_render_url?: string | null;
  latest_render_thumb_url?: string | null;
  updated_at: string | null;
}

export interface FurnitureSchemeMeta {
  id: string;
  name: string;
  source: SchemeSource;
  style_prompt?: string;
  brief?: SchemeBrief | null;
  base_scheme_id?: string | null;
  status: SchemeStatus;
  baseline_version_id?: string;
  preferred?: boolean;
  archived_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export async function listSchemes(
  projectId: string,
  options?: { baselineVersionId?: string; includeArchived?: boolean },
): Promise<FurnitureSchemeSummary[]> {
  const params = new URLSearchParams();
  if (options?.baselineVersionId) {
    params.set('baseline_version_id', options.baselineVersionId);
  }
  if (options?.includeArchived) params.set('include_archived', 'true');
  const query = params.toString();
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}/schemes${
      query ? `?${query}` : ''
    }`,
    { cache: 'no-store', headers: { Accept: 'application/json' } },
  );
  return unwrap<FurnitureSchemeSummary[]>(res);
}

export async function createScheme(
  projectId: string,
  payload: {
    id: string;
    name: string;
    source?: SchemeSource;
    base_scheme_id?: string;
    furniture?: FurnitureItem[];
  },
): Promise<FurnitureSchemeMeta> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}/schemes`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(payload),
    },
  );
  return unwrap<FurnitureSchemeMeta>(res);
}

export async function fetchScheme(
  projectId: string,
  schemeId: string,
): Promise<FurnitureSchemeMeta> {
  const res = await fetch(schemePath(projectId, schemeId), {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  return unwrap<FurnitureSchemeMeta>(res);
}

export async function duplicateScheme(
  projectId: string,
  schemeId: string,
  payload: { id: string; name: string },
): Promise<FurnitureSchemeMeta> {
  const res = await fetch(`${schemePath(projectId, schemeId)}/duplicate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  });
  return unwrap<FurnitureSchemeMeta>(res);
}

export async function patchScheme(
  projectId: string,
  schemeId: string,
  payload: { name?: string; style_prompt?: string; brief?: SchemeBrief | null },
): Promise<FurnitureSchemeMeta> {
  const res = await fetch(schemePath(projectId, schemeId), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  });
  return unwrap<FurnitureSchemeMeta>(res);
}

// Phase D (D-2): confirmScheme / adjustScheme 已下线 —— 方案无确认锁, 副本走 duplicateScheme。

export async function archiveScheme(
  projectId: string,
  schemeId: string,
): Promise<FurnitureSchemeMeta> {
  const res = await fetch(`${schemePath(projectId, schemeId)}/archive`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  });
  return unwrap<FurnitureSchemeMeta>(res);
}

// 恢复已归档方案 (Phase D / D-5): archived -> draft。
export async function restoreScheme(
  projectId: string,
  schemeId: string,
): Promise<FurnitureSchemeMeta> {
  const res = await fetch(`${schemePath(projectId, schemeId)}/restore`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  });
  return unwrap<FurnitureSchemeMeta>(res);
}

export async function setPreferredScheme(
  projectId: string,
  schemeId: string,
): Promise<FurnitureSchemeMeta> {
  const res = await fetch(`${schemePath(projectId, schemeId)}/set-preferred`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  });
  return unwrap<FurnitureSchemeMeta>(res);
}

export async function migrateScheme(
  projectId: string,
  schemeId: string,
  payload: { target_baseline_version_id: string; id: string; name: string },
): Promise<FurnitureSchemeMeta> {
  const res = await fetch(`${schemePath(projectId, schemeId)}/migrate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  });
  return unwrap<FurnitureSchemeMeta>(res);
}

export async function deleteScheme(
  projectId: string,
  schemeId: string,
): Promise<{ ok: boolean; trashed: string }> {
  const res = await fetch(schemePath(projectId, schemeId), {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  });
  return unwrap<{ ok: boolean; trashed: string }>(res);
}

export interface FurnishRequest {
  style_prompt: string;
  count: number;
  base_scheme_id?: string;
  model?: string;
}

export interface FurnishResult {
  schemes: Array<{ id: string; name: string; items?: number }>;
  warnings: string[];
}

export async function startFurnish(
  projectId: string,
  payload: FurnishRequest,
): Promise<{ job_id: string }> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}/furnish`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(payload),
    },
  );
  return unwrap<{ job_id: string }>(res);
}

export async function postDerive(
  geometry: Geometry,
  signal?: AbortSignal,
): Promise<DeriveResult> {
  const res = await fetch(`${API_BASE}/derive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(geometry),
    signal,
  });
  return unwrap<DeriveResult>(res);
}

// 校验保存 (§⑨): POST save-geometry。后端 validate; 有 ERROR -> 400 不落盘。
// 与 unwrap 不同: 这里需要在 400 时读取 errors/warns 结构, 故直接处理 Response。
export interface SaveGeometryResponse {
  ok: boolean;
  warns: string[];
  errors?: string[];
  derived?: DeriveResult;
}

export async function saveGeometry(
  projectId: string,
  geometry: Geometry,
): Promise<SaveGeometryResponse> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}/save-geometry`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(geometry),
    },
  );
  let body: Partial<SaveGeometryResponse> = {};
  try {
    body = (await res.json()) as Partial<SaveGeometryResponse>;
  } catch {
    /* 非 JSON 错误体 */
  }
  if (!res.ok) {
    // 校验失败 (400): 返回 ok:false + errors/warns, 由调用方展示, 不抛异常。
    return {
      ok: false,
      warns: body.warns ?? [],
      errors: body.errors ?? [`${res.status} ${res.statusText}`],
    };
  }
  return {
    ok: true,
    warns: body.warns ?? [],
    derived: body.derived,
  };
}

// --------------------------------------------------------------------------- //
//  AI 子系统 (Phase 2): 状态 / 异步生成 / 任务轮询 / 渲染历史。同源 /api。
// --------------------------------------------------------------------------- //
export interface AiBudget {
  day: string;
  daily_count: number;
  daily_cap: number;
  per_project_cap: number;
  total_tokens: number;
}

export interface AiStatus {
  enabled: boolean;
  provider: string;
  model: string;
  budget: AiBudget;
  // 几何锁定编辑后端: "换后端重试"按钮据此判断目标后端是否可用 (旧后端无此字段时 undefined)。
  geometry_edit_backend?: GeometryEditBackend;
  fal_enabled?: boolean;
}

// 几何锁定编辑后端: relay=gpt-image-2 (默认), fal=nano-banana。
export type GeometryEditBackend = 'relay' | 'fal';

// P4 自动验收摘要 (仅 method=geometry-lock 记录有; 旧记录/轴测路径为 undefined)。
// 退化形态: 验收关闭 {ok:true, skipped:true}; 验收自身异常 {ok:true, error:"…"}。
export interface RenderAutoCheck {
  ok: boolean;
  score?: number;
  fail_reasons?: string[];
  attempts?: number;
  skipped?: boolean;
  error?: string;
}

export async function getAiStatus(): Promise<AiStatus> {
  const res = await fetch(`${API_BASE}/ai/status`, {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  return unwrap<AiStatus>(res);
}

// 工作流改造 (F): render 记录验收/确认状态。draft=未处理; accepted=实拍验收通过 / 轴测
// 确认为方案参考; rejected=驳回 (feedback_reason 记不满意原因)。缺省视为 draft。
export type RenderStatus = 'draft' | 'accepted' | 'rejected';

export interface RenderRecord {
  id: string;
  url: string;
  mode: string;
  scheme_id?: string;
  model: string;
  with_positions?: boolean;
  photo_id?: string;
  room_id?: string | null;
  thumb_url?: string | null;
  preview_url?: string | null; // 中等预览 (页面主图用, ~几百KB; url 是 ~2MB 全图仅下载)
  status?: RenderStatus; // 验收/确认状态 (缺省 draft)
  feedback_reason?: string | null; // rejected 时的不满意原因 (溯源)
  comment?: string | null; // render-note-b1: 单条可编辑备注 (缺省视为无; 与 status/feedback_reason 正交)
  low_accuracy?: boolean; // B2: 低准确度模式生成 (未标注房间/视角时显式降级)
  method?: string; // "geometry-lock"=路线A 几何锁定; 缺省=轴测软参考路径
  edit_backend?: GeometryEditBackend; // 几何锁定生效编辑后端 (换后端重试溯源)
  auto_check?: RenderAutoCheck | null; // P4 自动验收 (与人工 status 互不相干)
  usage?: Record<string, unknown>;
  scene_manifest?: Record<string, unknown>;
}

export interface SceneIssue {
  level: 'ERROR' | 'WARN' | 'INFO';
  code: string;
  message: string;
  index?: number;
  room_id?: string;
  [k: string]: unknown;
}

export interface SceneValidation {
  ok: boolean;
  issues: SceneIssue[];
  errors: SceneIssue[];
  warnings: SceneIssue[];
  adjustments: Array<Record<string, unknown>>;
}

// 布局质量 lint (批2): 设计质量体检 (悬空/背贴玻璃幕墙/家具碰撞), 与渲染安全的
// SceneValidation 并列。信封同构但无 adjustments (lint 只读不自愈)。
export interface LayoutLint {
  ok: boolean;
  issues: SceneIssue[];
  errors: SceneIssue[];
  warnings: SceneIssue[];
}

// 布局门禁错误 (render-real/render-ai 返 400 code=LAYOUT_NOT_READY): 携带 issues 供前端
// 展示 + 提供"忽略并继续"降级入口。区别于普通 Error 让调用页可专门处理。
export class LayoutGateError extends Error {
  readonly layoutLint: LayoutLint;
  constructor(message: string, layoutLint: LayoutLint) {
    super(message);
    this.name = 'LayoutGateError';
    this.layoutLint = layoutLint;
  }
}

export interface RenderScene {
  version: number;
  project_id?: string;
  baseline_version_id?: string;
  scheme_id?: string;
  validation: SceneValidation;
  layout_lint?: LayoutLint; // 批2: 布局质量体检 (仅 scene 端点透出)
}

export async function fetchRenderScene(
  projectId: string,
  schemeId?: string,
): Promise<RenderScene> {
  const url =
    !schemeId || schemeId === DEFAULT_SCHEME_ID
      ? `${API_BASE}/projects/${encodeURIComponent(projectId)}/scene`
      : `${schemePath(projectId, schemeId)}/scene`;
  const res = await fetch(url, {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  return unwrap<RenderScene>(res);
}

export async function listRenders(
  projectId: string,
  schemeId?: string,
): Promise<RenderRecord[]> {
  const url =
    !schemeId || schemeId === DEFAULT_SCHEME_ID
      ? `${API_BASE}/projects/${encodeURIComponent(projectId)}/renders`
      : `${schemePath(projectId, schemeId)}/renders`;
  const res = await fetch(url, {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  return unwrap<RenderRecord[]>(res);
}

// 删除一条效果图: 摘记录 + 后端 unlink 该记录自有产物文件 (共享空房照 photo_url 保留)。
// 方案级端点 (default 走 schemes/default, 后端另摘 legacy 账本)。
export async function deleteRender(
  projectId: string,
  schemeId: string,
  renderId: string,
): Promise<{ ok: boolean; deleted: string; files_removed: number }> {
  const res = await fetch(
    `${schemePath(projectId, schemeId)}/renders/${encodeURIComponent(
      renderId,
    )}`,
    { method: 'DELETE', headers: { Accept: 'application/json' } },
  );
  return unwrap<{ ok: boolean; deleted: string; files_removed: number }>(res);
}

// 工作流改造 (F): 给一条效果图记录写验收/确认状态 (实拍验收 / 轴测确认为方案参考)。
// body: {status, feedback_reason?}。返回更新后的记录。
export async function setRenderStatus(
  projectId: string,
  schemeId: string,
  renderId: string,
  status: RenderStatus,
  feedbackReason?: string,
): Promise<RenderRecord> {
  const res = await fetch(
    `${schemePath(projectId, schemeId)}/renders/${encodeURIComponent(
      renderId,
    )}`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(
        feedbackReason !== undefined
          ? { status, feedback_reason: feedbackReason }
          : { status },
      ),
    },
  );
  return unwrap<RenderRecord>(res);
}

// render-note-b1: 给一条效果图记录写单条可编辑备注 (与验收 status 正交)。
// body: {comment}。空串 = 清除备注。返回更新后的记录。
export async function setRenderComment(
  projectId: string,
  schemeId: string,
  renderId: string,
  comment: string,
): Promise<RenderRecord> {
  const res = await fetch(
    `${schemePath(projectId, schemeId)}/renders/${encodeURIComponent(
      renderId,
    )}`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({ comment }),
    },
  );
  return unwrap<RenderRecord>(res);
}

export type JobStatus = 'queued' | 'running' | 'done' | 'error';

export interface AiJob<T = unknown> {
  id: string;
  status: JobStatus;
  result: T | null;
  error: string | null;
}

export async function startRenderAi(
  projectId: string,
  model?: string,
  schemeId?: string,
): Promise<{ job_id: string }> {
  const url =
    !schemeId || schemeId === DEFAULT_SCHEME_ID
      ? `${API_BASE}/projects/${encodeURIComponent(projectId)}/render-ai`
      : `${schemePath(projectId, schemeId)}/render-ai`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(model ? { model } : {}),
  });
  return unwrap<{ job_id: string }>(res);
}

// 第7步: 空房照 + 轴测参考 -> 实拍效果图 (异步 job)。
// allowUnlabeled: B2 低准确度模式 —— 未标注房间/视角时显式降级绕过 readiness gate。
// backend: 几何锁定编辑后端单次覆盖 (换后端重试; 仅已标定照片有效, 后端严格校验)。
// allowLayoutIssues: 批2 布局 lint 门禁降级 —— 忽略柜类悬空/背贴玻璃幕墙/家具碰撞继续生成。
export async function startRenderReal(
  projectId: string,
  schemeId: string,
  photoId: string,
  options?: {
    model?: string;
    allowUnlabeled?: boolean;
    backend?: GeometryEditBackend;
    allowLayoutIssues?: boolean;
  },
): Promise<{ job_id: string }> {
  const body: Record<string, unknown> = { photo_id: photoId };
  if (options?.model) body.model = options.model;
  if (options?.allowUnlabeled) body.allow_unlabeled = true;
  if (options?.backend) body.backend = options.backend;
  if (options?.allowLayoutIssues) body.allow_layout_issues = true;
  const res = await fetch(`${schemePath(projectId, schemeId)}/render-real`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    // 布局门禁 (400 LAYOUT_NOT_READY): 抛结构化错误保留 issues, 让页面提供降级入口。
    let parsed: {
      code?: string;
      error?: string;
      detail?: string;
      layout_lint?: LayoutLint;
    } | null = null;
    try {
      parsed = await res.json();
    } catch {
      /* 非 JSON 错误体 */
    }
    if (
      res.status === 400 &&
      parsed?.code === 'LAYOUT_NOT_READY' &&
      parsed.layout_lint
    ) {
      throw new LayoutGateError(
        parsed.error || '家具布局存在设计问题',
        parsed.layout_lint,
      );
    }
    // 保留 unwrap 的 error/detail 兜底 (FastAPI 默认错误体是 {detail}, 别退化成裸状态行)。
    throw new Error(
      parsed?.error || parsed?.detail || `${res.status} ${res.statusText}`,
    );
  }
  return res.json() as Promise<{ job_id: string }>;
}

// 拍摄视角自动判定 (问题1): gpt-5.5 视觉比对空房照与 4 张轴测视角, 返回建议视角 (可能 null)。
// 尽力而为、不阻断 —— 失败/未启用时返回 { suggested: null }, 前端仍可手动选。
export async function suggestView(
  projectId: string,
  schemeId: string,
  photoId: string,
): Promise<{ suggested: string | null }> {
  const res = await fetch(`${schemePath(projectId, schemeId)}/suggest-view`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ photo_id: photoId }),
  });
  return unwrap<{ suggested: string | null }>(res);
}

// 4 视角各自的主窗方位 (给选择器标注"窗在左/右", 让用户按窗户方位对上照片)。纯读、无 AI。
export async function viewHints(
  projectId: string,
  schemeId: string,
  roomId: string,
): Promise<{ hints: Record<string, string> }> {
  const res = await fetch(
    `${schemePath(projectId, schemeId)}/view-hints?room_id=${encodeURIComponent(
      roomId,
    )}`,
    { headers: { Accept: 'application/json' } },
  );
  return unwrap<{ hints: Record<string, string> }>(res);
}

export async function pollJob<T = RenderRecord>(
  jobId: string,
): Promise<AiJob<T>> {
  const res = await fetch(`${API_BASE}/ai/jobs/${encodeURIComponent(jobId)}`, {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  return unwrap<AiJob<T>>(res);
}
