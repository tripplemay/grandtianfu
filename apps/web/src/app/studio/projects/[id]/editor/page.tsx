'use client';

import React, { use } from 'react';
import { useSearchParams } from 'next/navigation';
import FloorplanEditor from 'components/studio/editor/FloorplanEditor';
import PageShell from 'components/studio/ui/PageShell';
import EmptyState from 'components/studio/ui/EmptyState';
import SchemeRequiredState from 'components/studio/workflow/SchemeRequiredState';
import { useProjectWorkflow } from 'components/studio/workflow/ProjectWorkflowContext';
import { LinkButton } from 'components/studio/ui/buttons';

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
  const { baselines, currentScheme, isHistorical, loading } =
    useProjectWorkflow();
  const viewingBaseline = baselineVersionId
    ? baselines.find((b) => b.id === baselineVersionId) ?? null
    : null;

  // 只读判定统一由 ProjectWorkflowContext 驱动 (P0-1): 仅当正向确认「草稿户型版本」或
  // 「当前已确认户型下的非归档方案」才可写。加载中 / 历史版本 / 未知或已锁定方案一律只读,
  // 杜绝直链历史方案或 context 加载竞态窗口以可写模式挂载编辑器 (数据安全 / 越权红线)。
  const editable = baselineVersionId
    ? viewingBaseline?.status === 'draft'
    : !isHistorical &&
      !!currentScheme &&
      currentScheme.status !== 'confirmed' &&
      currentScheme.status !== 'archived';
  const readOnly = loading || !editable;
  const readOnlyReason = baselineVersionId
    ? '已确认或历史户型版本只读；如需调整，请在户型基线页创建新版本。'
    : '已确认、归档或历史版本方案只读；如需调整，请在方案中心创建调整副本。';

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

  // scheme 模式且确定不可编辑 (排除加载中): 历史 / 归档 / 未知方案 → 锁定空状态, 不挂载可写编辑器。
  if (!baselineVersionId && !loading && !editable) {
    return (
      <PageShell variant="full" title="家具布置" description={readOnlyReason}>
        <EmptyState
          title="该方案已锁定"
          description={readOnlyReason}
          action={
            <LinkButton
              href={`/studio/projects/${encodeURIComponent(id)}/scheme`}
            >
              去方案中心继续调整
            </LinkButton>
          }
        />
      </PageShell>
    );
  }

  return (
    // P4 全屏: canvas 变体让编辑器逃出 Studio 壳, 画布真正 100dvh。上下文(户型/方案/退出)
    // 由 FloorplanEditor 自带顶栏承载。
    <PageShell variant="canvas">
      {/* key 随户型版本 / 方案变化强制重挂载 (P0-4): 重置 undo 历史栈与草稿状态,
          防止客户端换版本/换方案后 undo 把上一上下文数据还原进当前方案。 */}
      <FloorplanEditor
        key={`${baselineVersionId ?? ''}::${schemeId ?? 'default'}`}
        projectId={id}
        schemeId={schemeId ?? 'default'}
        baselineVersionId={baselineVersionId}
        readOnly={readOnly}
        readOnlyReason={readOnlyReason}
      />
    </PageShell>
  );
}
