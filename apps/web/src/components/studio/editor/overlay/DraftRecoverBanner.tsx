'use client';

import React from 'react';
import type { DraftPending } from '../hooks/useDraftAutosave';
import { NoticeBanner } from '../../ui/status';
import { Button } from '../../ui/buttons';

interface Props {
  pending: DraftPending;
  onRecover: () => void;
  onDiscard: () => void;
}

// 草稿恢复提示条 (阶段 5b / P3): 载入时存在未保存草稿 -> 提示恢复/丢弃。
// 复用 NoticeBanner + Button(均透传 data-testid, 便于 CDP 驱动, 不依赖原生 confirm)。
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
    <NoticeBanner
      tone="warn"
      dataTestId="draft-recover-banner"
      className="flex flex-wrap items-center gap-3"
    >
      <span className="font-semibold">发现未保存的本地草稿({domains})</span>
      <span className="opacity-80">是否恢复上次未保存的编辑?</span>
      <div className="ml-auto flex gap-2">
        <Button
          variant="primary"
          size="sm"
          dataTestId="draft-recover"
          onClick={onRecover}
        >
          恢复草稿
        </Button>
        <Button
          variant="secondary"
          size="sm"
          dataTestId="draft-discard"
          onClick={onDiscard}
        >
          丢弃
        </Button>
      </div>
    </NoticeBanner>
  );
}
