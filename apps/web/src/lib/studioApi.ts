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

// 项目台 (Stage C): 项目列表 / 新建 / 删除。同源 /api, 不开 CORS。
export interface ProjectSummary {
  id: string;
  name: string;
  rooms: number;
}

export async function listProjects(): Promise<ProjectSummary[]> {
  const res = await fetch(`${API_BASE}/projects`, {
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

export async function fetchGeometry(projectId: string): Promise<Geometry> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}/geometry`,
    {
      headers: { Accept: 'application/json' },
    },
  );
  return unwrap<Geometry>(res);
}

// 家具读写 (B2): 后端返回 / 接收裸数组 (相对键 {room_id,dx,dy})。同源 /api, 不开 CORS。
export type FurnitureItem = Record<string, unknown>;

export async function fetchFurniture(
  projectId: string,
): Promise<FurnitureItem[]> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}/furniture`,
    {
      headers: { Accept: 'application/json' },
    },
  );
  return unwrap<FurnitureItem[]>(res);
}

export interface SaveFurnitureResponse {
  ok: boolean;
}

export async function saveFurniture(
  projectId: string,
  furniture: FurnitureItem[],
): Promise<SaveFurnitureResponse> {
  const res = await fetch(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}/save-furniture`,
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

export async function postDerive(geometry: Geometry): Promise<DeriveResult> {
  const res = await fetch(`${API_BASE}/derive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(geometry),
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
