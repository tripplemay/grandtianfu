'use client';

import React from 'react';
import type { DraftPending } from '../hooks/useDraftAutosave';

interface Props {
  pending: DraftPending;
  onRecover: () => void;
  onDiscard: () => void;
}

// 草稿恢复提示条 (阶段 5b / P3): 载入时存在未保存草稿 -> 提示恢复/丢弃。
// 自带 data-testid 便于 CDP 驱动 (不依赖原生 confirm)。
export default function DraftRecoverBanner({
  pending,
  onRecover,
  onDiscard,
}: Props) {
  const domains = [
    pending.hasGeo ? '几何' : null,
    pending.hasFurn ? '家具' : null,
  ]
    .filter(Boolean)
    .join(' / ');
  return (
    <div
      data-testid="draft-recover-banner"
      className="mb-3 flex flex-wrap items-center gap-3 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200"
    >
      <span className="font-semibold">发现未保存的本地草稿({domains})</span>
      <span className="opacity-80">是否恢复上次未保存的编辑?</span>
      <div className="ml-auto flex gap-2">
        <button
          type="button"
          data-testid="draft-recover"
          onClick={onRecover}
          className="rounded-lg bg-brand-500 px-3 py-1 text-xs font-medium text-white hover:bg-brand-600"
        >
          恢复草稿
        </button>
        <button
          type="button"
          data-testid="draft-discard"
          onClick={onDiscard}
          className="rounded-lg bg-gray-200 px-3 py-1 text-xs font-medium text-navy-700 hover:bg-gray-300 dark:bg-navy-700 dark:text-white"
        >
          丢弃
        </button>
      </div>
    </div>
  );
}
