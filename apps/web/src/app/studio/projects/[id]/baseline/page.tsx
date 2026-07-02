'use client';

import React, { use, useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import PageShell from 'components/studio/ui/PageShell';
import EmptyState from 'components/studio/ui/EmptyState';
import LoadingState from 'components/studio/ui/LoadingState';
import {
  BackendErrorBanner,
  StatusLines,
  StatusRow,
} from 'components/studio/ui/status';
import { Button, LinkButton } from 'components/studio/ui/buttons';
import { StudioCard } from 'components/studio/ui/primitives';
import BaselinePhotosCard from 'components/studio/baseline/BaselinePhotosCard';
import { useProjectWorkflow } from 'components/studio/workflow/ProjectWorkflowContext';
import { useToastContext } from 'components/studio/ui/ToastHost';
import { useConfirm } from 'components/studio/ui/ConfirmDialog';
import { createBaseline, confirmBaseline } from 'lib/studioApi';
import { MdGridView } from 'react-icons/md';

export default function BaselinePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const {
    currentBaseline,
    viewingBaseline,
    isHistorical,
    loading,
    error,
    reload,
  } = useProjectWorkflow();
  const { showToast } = useToastContext();
  const confirm = useConfirm();
  const [busy, setBusy] = useState(false);
  const baseline = viewingBaseline ?? currentBaseline;

  // 前置校验(消除晚失败):草稿卡就地展示 validation_issues, 存在 ERROR 时禁用确认按钮。
  const issues = baseline?.validation_issues ?? [];
  const vErrors = issues
    .filter((i) => i.level === 'ERROR')
    .map((i) => i.message);
  const vWarns = issues.filter((i) => i.level === 'WARN').map((i) => i.message);

  const onCreateVersion = useCallback(async () => {
    if (!currentBaseline) return;
    const ok = await confirm({
      title: `从户型 ${currentBaseline.id} 创建新版本`,
      message: `系统将复制当前户型形成新草稿。${currentBaseline.id} 及其所有方案和效果图保持不变。`,
      confirmText: '创建新版本',
    });
    if (!ok) return;
    setBusy(true);
    try {
      const created = await createBaseline(id, currentBaseline.id);
      showToast('新户型草稿版本已创建', 'success');
      await reload();
      router.push(
        `/studio/projects/${encodeURIComponent(
          id,
        )}/baseline?version=${encodeURIComponent(created.id)}`,
      );
    } catch (e) {
      showToast(
        `创建失败:${e instanceof Error ? e.message : String(e)}`,
        'error',
      );
    } finally {
      setBusy(false);
    }
  }, [id, currentBaseline, confirm, showToast, reload, router]);

  const onConfirmDraft = useCallback(async () => {
    if (!baseline || baseline.status !== 'draft') return;
    // 文案按场景分支(§9.1 首次锁定 / §9.3 顶替旧版本):首次确认时并无「旧版本进历史」,
    // 用中性锁定文案,避免虚假且吓人的后果描述在最关键闸门前吓退用户。
    const isFirstConfirm = !currentBaseline;
    const ok = await confirm(
      isFirstConfirm
        ? {
            title: `确认并锁定户型 ${baseline.id}？`,
            message:
              '确认后，本版本将作为软装方案的共同空间基础，不能直接覆盖修改。后续调整需要创建新的户型版本。',
            confirmText: '确认户型',
          }
        : {
            title: `确认并启用户型 ${baseline.id}？`,
            message: `${baseline.id} 将成为当前户型，${
              currentBaseline?.id ?? '原当前版本'
            } 及其方案进入历史版本。旧方案不会自动迁移。`,
            confirmText: '确认并启用',
            danger: true,
          },
    );
    if (!ok) return;
    setBusy(true);
    try {
      await confirmBaseline(id, baseline.id);
      showToast('户型已确认,进入方案中心创建方案', 'success');
      await reload();
      // 确认户型解锁了方案创建, 放行到方案中心(§7 下一步), 不把用户留在基线页自己找路。
      router.push(`/studio/projects/${encodeURIComponent(id)}/scheme`);
    } catch (e) {
      showToast(
        `确认失败:${e instanceof Error ? e.message : String(e)}`,
        'error',
      );
    } finally {
      setBusy(false);
    }
  }, [id, baseline, currentBaseline, confirm, showToast, reload, router]);

  if (loading) {
    return (
      <PageShell
        title="户型基线"
        description="户型版本是软装方案共享的空间基础；已确认版本只读，调整必须创建新版本。"
        state={<LoadingState rows={2} />}
      />
    );
  }

  if (!baseline) {
    return (
      <PageShell
        title="户型基线"
        description="户型版本是软装方案共享的空间基础；已确认版本只读，调整必须创建新版本。"
      >
        {error && <BackendErrorBanner message={error} />}
        <EmptyState
          title="暂无户型基线"
          description="当前项目还没有可查看的户型版本。请先创建或确认户型基线。"
        />
      </PageShell>
    );
  }

  return (
    <PageShell
      title="户型基线"
      description="户型版本是软装方案共享的空间基础；已确认版本只读，调整必须创建新版本。"
    >
      {error && <BackendErrorBanner message={error} />}
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <StudioCard>
          <div className="mb-3 flex items-center gap-2">
            <MdGridView className="h-5 w-5 text-brand-500" />
            <h2 className="text-base font-bold text-navy-700 dark:text-white">
              户型 {baseline?.id ?? 'v1'}
            </h2>
          </div>
          <div className="rounded-xl bg-gray-50 p-4 text-sm text-gray-600 dark:bg-navy-900 dark:text-gray-300">
            <StatusRow kind="baseline" status={baseline?.status} />
            <p className="mt-1">
              {baseline?.status === 'draft'
                ? '草稿版本可编辑和校验，确认后才允许创建方案。'
                : baseline?.status === 'superseded' || isHistorical
                ? '历史户型版本只允许查看和导出。'
                : '已锁定，所有当前方案基于此版本。'}
            </p>
            {baseline?.status === 'draft' && (
              <div className="mt-3 border-t border-gray-200 pt-3 dark:border-white/10">
                <StatusLines
                  errors={vErrors}
                  warns={vWarns}
                  okText="校验通过，可确认并锁定户型。"
                  hintText="进入编辑器编辑户型后会自动校验空间 / 门窗 / 重叠。"
                />
              </div>
            )}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {baseline?.status === 'draft' ? (
              <>
                <LinkButton
                  href={`/studio/projects/${encodeURIComponent(
                    id,
                  )}/editor?baseline=${encodeURIComponent(baseline.id)}`}
                  variant="primary"
                >
                  编辑草稿户型
                </LinkButton>
                <Button
                  variant="success-solid"
                  onClick={() => void onConfirmDraft()}
                  disabled={busy || vErrors.length > 0}
                  title={
                    vErrors.length > 0
                      ? `请先在编辑器解决 ${vErrors.length} 处错误再确认`
                      : undefined
                  }
                >
                  {currentBaseline ? '确认并启用' : '确认户型'}
                </Button>
              </>
            ) : (
              <>
                <LinkButton
                  href={`/studio/projects/${encodeURIComponent(
                    id,
                  )}/editor?baseline=${encodeURIComponent(baseline.id)}`}
                  variant="secondary"
                >
                  查看户型
                </LinkButton>
                {baseline?.status === 'confirmed' && (
                  <Button
                    variant="primary"
                    onClick={() => void onCreateVersion()}
                    disabled={busy}
                  >
                    创建新版本
                  </Button>
                )}
              </>
            )}
            <LinkButton
              href={`/studio/projects/${encodeURIComponent(id)}/versions`}
              variant="secondary"
            >
              查看版本记录
            </LinkButton>
          </div>
        </StudioCard>

        <BaselinePhotosCard
          projectId={id}
          versionId={baseline.id}
          readOnly={baseline.status === 'superseded' || isHistorical}
        />
      </div>
    </PageShell>
  );
}
