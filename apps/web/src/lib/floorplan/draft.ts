// 本地草稿兜底 (阶段 5b / P3): 编辑(dirty)时 debounce 写 localStorage, 载入时若存在
// 草稿则提示恢复。仅本地兜底, 不改变保存语义 (保存仍走后端; 保存成功清草稿)。
//
// 键: gtf-draft:<projectId>:<domain> (domain = geometry | furniture)。
// 值: { ts, data } —— ts 为写入时刻 (ms), 用于「比远端新」判断 (载入后任何草稿即视为
//      未保存的更新, 提示恢复)。

export type DraftDomain = 'geometry' | 'furniture';

export interface DraftEnvelope<T> {
  ts: number;
  data: T;
}

export function draftKey(projectId: string, domain: DraftDomain): string {
  return `gtf-draft:${projectId}:${domain}`;
}

export function readDraft<T>(
  projectId: string,
  domain: DraftDomain,
): DraftEnvelope<T> | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(draftKey(projectId, domain));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DraftEnvelope<T>;
    if (!parsed || typeof parsed.ts !== 'number') return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeDraft<T>(
  projectId: string,
  domain: DraftDomain,
  data: T,
): void {
  if (typeof window === 'undefined') return;
  try {
    const env: DraftEnvelope<T> = { ts: Date.now(), data };
    window.localStorage.setItem(draftKey(projectId, domain), JSON.stringify(env));
  } catch {
    /* 配额满 / 隐私模式: 静默 (草稿仅兜底, 失败不影响编辑) */
  }
}

export function clearDraft(projectId: string, domain: DraftDomain): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(draftKey(projectId, domain));
  } catch {
    /* 静默 */
  }
}
