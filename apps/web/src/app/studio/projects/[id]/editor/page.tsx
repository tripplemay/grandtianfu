'use client';

import React, { use } from 'react';
import FloorplanEditor from 'components/studio/editor/FloorplanEditor';
import PageShell from 'components/studio/ui/PageShell';

// Next 15:client component 中 params 为 Promise,用 React.use 解包。
// Phase 2:套 PageShell 满高变体(画布尽量大);标题/副标题统一,容器单一来源。
export default function EditorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  return (
    <PageShell
      variant="full"
      title="编辑器"
      description="拖房间/把手缩放 · 沿墙滑门窗 · 实时派生预览 · 校验保存(/save-geometry)。"
    >
      <FloorplanEditor projectId={id} />
    </PageShell>
  );
}
