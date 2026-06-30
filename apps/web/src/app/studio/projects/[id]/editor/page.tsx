'use client';

import React, { use } from 'react';
import { useSearchParams } from 'next/navigation';
import FloorplanEditor from 'components/studio/editor/FloorplanEditor';
import PageShell from 'components/studio/ui/PageShell';
import SchemeRequiredState from 'components/studio/workflow/SchemeRequiredState';
import { useProjectWorkflow } from 'components/studio/workflow/ProjectWorkflowContext';

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
  const baselineVersionId = search.get('baseline') || undefined;
  const { baselines, currentScheme } = useProjectWorkflow();
  const viewingBaseline = baselineVersionId
    ? baselines.find((b) => b.id === baselineVersionId)
    : null;
  const readOnly = baselineVersionId
    ? viewingBaseline?.status !== 'draft'
    : currentScheme?.status === 'confirmed' || currentScheme?.status === 'archived';
  const readOnlyReason = baselineVersionId
    ? '已确认或历史户型版本只读；如需调整，请在户型基线页创建新版本。'
    : '已确认或归档方案只读；如需调整，请在方案中心创建调整副本。';

  if (!schemeId && !baselineVersionId) {
    return (
      <PageShell
        variant="full"
        title="家具布置"
        description="请选择当前要编辑的软装方案，或从户型基线进入户型查看。"
      >
        <SchemeRequiredState projectId={id} />
      </PageShell>
    );
  }

  return (
    <PageShell
      variant="full"
      title={baselineVersionId ? '户型编辑' : '家具布置'}
      description={
        baselineVersionId
          ? `正在查看/编辑户型版本:${baselineVersionId}。已确认版本保存会被后端拒绝。`
          : `拖房间/把手缩放 · 沿墙滑门窗 · 当前家具方案:${schemeId}。`
      }
    >
      <FloorplanEditor
        projectId={id}
        schemeId={schemeId ?? 'default'}
        baselineVersionId={baselineVersionId}
        readOnly={readOnly}
        readOnlyReason={readOnlyReason}
      />
    </PageShell>
  );
}
