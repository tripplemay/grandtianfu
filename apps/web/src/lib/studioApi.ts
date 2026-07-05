// 同源数据层:全程 baseURL='/api'(dev 经 next.config rewrites 代理到 FastAPI;
// prod 路 A 由 nginx 把 /api 转给 api 容器)。不开 CORS。
// 统一信封约定 { success, data, error };同时兼容引擎直出的裸对象(parity 基准)。

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

export interface BaselinePhoto {
  id: string;
  url: string;
  thumb_url?: string | null;
  room_id?: string | null;
  direction?: string | null;
  note?: string | null;
  purpose?: string | null; // P2 材质C: 'wall_material' = 墙面实拍参考; 缺省/'empty' = 空房底图
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

export type SchemeSource = 'legacy' | 'manual' | 'duplicate' | 'ai';
export type SchemeStatus = 'draft' | 'confirmed' | 'archived';

export interface FurnitureSchemeSummary {
  id: string;
  name: string;
  source: SchemeSource;
  style_prompt?: string;
  status: SchemeStatus;
  baseline_version_id?: string;
  preferred?: boolean;
  archived_at?: string | null;
  items: number;
  renders: number;
  latest_render_url?: string | null;
  latest_render_thumb_url?: string | null;
  updated_at: string | null;
}

export interface FurnitureSchemeMeta {
  id: string;
  name: string;
  source: SchemeSource;
  style_prompt?: string;
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
  payload: { name?: string; status?: SchemeStatus },
): Promise<FurnitureSchemeMeta> {
  const res = await fetch(schemePath(projectId, schemeId), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  });
  return unwrap<FurnitureSchemeMeta>(res);
}

export async function confirmScheme(
  projectId: string,
  schemeId: string,
): Promise<FurnitureSchemeMeta> {
  const res = await fetch(`${schemePath(projectId, schemeId)}/confirm`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  });
  return unwrap<FurnitureSchemeMeta>(res);
}

export async function adjustScheme(
  projectId: string,
  schemeId: string,
  payload: { id: string; name: string },
): Promise<FurnitureSchemeMeta> {
  const res = await fetch(`${schemePath(projectId, schemeId)}/adjust`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  });
  return unwrap<FurnitureSchemeMeta>(res);
}

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
}

export async function getAiStatus(): Promise<AiStatus> {
  const res = await fetch(`${API_BASE}/ai/status`, {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  return unwrap<AiStatus>(res);
}

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

export interface RenderScene {
  version: number;
  project_id?: string;
  baseline_version_id?: string;
  scheme_id?: string;
  validation: SceneValidation;
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
export async function startRenderReal(
  projectId: string,
  schemeId: string,
  photoId: string,
  model?: string,
): Promise<{ job_id: string }> {
  const res = await fetch(`${schemePath(projectId, schemeId)}/render-real`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(
      model ? { photo_id: photoId, model } : { photo_id: photoId },
    ),
  });
  return unwrap<{ job_id: string }>(res);
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
