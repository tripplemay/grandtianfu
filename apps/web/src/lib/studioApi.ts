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
export type WallTuple = [number, number, number, number, boolean, string, boolean];

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

export async function fetchGeometry(projectId: string): Promise<Geometry> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/geometry`, {
    headers: { Accept: 'application/json' },
  });
  return unwrap<Geometry>(res);
}

export async function postDerive(geometry: Geometry): Promise<DeriveResult> {
  const res = await fetch(`${API_BASE}/derive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(geometry),
  });
  return unwrap<DeriveResult>(res);
}
