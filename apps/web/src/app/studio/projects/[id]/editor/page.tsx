'use client';

import React, { use } from 'react';
import { useSearchParams } from 'next/navigation';
import FloorplanEditor from 'components/studio/editor/FloorplanEditor';
import PageShell from 'components/studio/ui/PageShell';
import SchemeRequiredState from 'components/studio/workflow/SchemeRequiredState';

// Next 15:client component 中 params 为 Promise,用 React.use 解包。
// Phase 2:套 PageShell 满高变体(画布尽量大);标题/副标题统一,容器单一来源。
export default function EditorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const search = useSearchParams();
  const schemeId = search.get('scheme');

  if (!schemeId) {
    return (
      <PageShell
        variant="full"
        title="家具布置"
        description="请选择当前要编辑的软装方案。"
      >
        <SchemeRequiredState projectId={id} />
      </PageShell>
    );
  }

  return (
    <PageShell
      variant="full"
      title="家具布置"
      description={`拖房间/把手缩放 · 沿墙滑门窗 · 当前家具方案:${schemeId}。`}
    >
      <FloorplanEditor projectId={id} schemeId={schemeId} />
    </PageShell>
  );
}
