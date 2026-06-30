'use client';

import React, { use, useCallback, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import Card from 'components/card';
import PageShell from 'components/studio/ui/PageShell';
import LoadingState from 'components/studio/ui/LoadingState';
import { BackendErrorBanner } from 'components/studio/ui/status';
import { useProjectWorkflow } from 'components/studio/workflow/ProjectWorkflowContext';
import { useToastContext } from 'components/studio/ui/ToastHost';
import { useConfirm } from 'components/studio/ui/ConfirmDialog';
import { createBaseline, confirmBaseline } from 'lib/studioApi';
import { MdGridView, MdPhotoCamera } from 'react-icons/md';

export default function BaselinePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { currentBaseline, viewingBaseline, isHistorical, loading, error, reload } =
    useProjectWorkflow();
  const { showToast } = useToastContext();
  const confirm = useConfirm();
  const [busy, setBusy] = useState(false);
  const baseline = viewingBaseline ?? currentBaseline;

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
        `/studio/projects/${encodeURIComponent(id)}/baseline?version=${encodeURIComponent(
          created.id,
        )}`,
      );
    } catch (e) {
      showToast(`创建失败:${e instanceof Error ? e.message : String(e)}`, 'error');
    } finally {
      setBusy(false);
    }
  }, [id, currentBaseline, confirm, showToast, reload, router]);

  const onConfirmDraft = useCallback(async () => {
    if (!baseline || baseline.status !== 'draft') return;
    const ok = await confirm({
      title: `确认并启用户型 ${baseline.id}？`,
      message: `${baseline.id} 将成为当前户型，原当前版本及其方案进入历史版本。旧方案不会自动迁移。`,
      confirmText: '确认并启用',
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await confirmBaseline(id, baseline.id);
      showToast('户型版本已确认并启用', 'success');
      await reload();
    } catch (e) {
      showToast(`确认失败:${e instanceof Error ? e.message : String(e)}`, 'error');
    } finally {
      setBusy(false);
    }
  }, [id, baseline, confirm, showToast, reload]);

  return (
    <PageShell
      title="户型基线"
      description="户型版本是软装方案共享的空间基础；已确认版本只读，调整必须创建新版本。"
      state={loading ? <LoadingState rows={2} /> : undefined}
    >
      {error && <BackendErrorBanner message={error} />}
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Card extra="w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10">
          <div className="mb-3 flex items-center gap-2">
            <MdGridView className="h-5 w-5 text-brand-500" />
            <h2 className="text-base font-bold text-navy-700 dark:text-white">
              户型 {baseline?.id ?? 'v1'}
            </h2>
          </div>
          <div className="rounded-xl bg-gray-50 p-4 text-sm text-gray-600 dark:bg-navy-900 dark:text-gray-300">
            <p>状态：{baseline?.status ?? 'confirmed'}</p>
            <p className="mt-1">
              {baseline?.status === 'draft'
                ? '草稿版本可编辑和校验，确认后才允许创建方案。'
                : baseline?.status === 'superseded' || isHistorical
                ? '历史户型版本只允许查看和导出。'
                : '已锁定，所有当前方案基于此版本。'}
            </p>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {baseline?.status === 'draft' ? (
              <>
                <Link
                  href={`/studio/projects/${encodeURIComponent(
                    id,
                  )}/editor?baseline=${encodeURIComponent(baseline.id)}`}
                  className="rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
                >
                  编辑草稿户型
                </Link>
                <button
                  type="button"
                  onClick={() => void onConfirmDraft()}
                  disabled={busy}
                  className="rounded-lg bg-green-600 px-3 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
                >
                  确认并启用
                </button>
              </>
            ) : (
              <>
                <Link
                  href={`/studio/projects/${encodeURIComponent(
                    id,
                  )}/editor?baseline=${encodeURIComponent(baseline.id)}`}
                  className="rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
                >
                  查看户型
                </Link>
                {baseline?.status === 'confirmed' && (
                  <button
                    type="button"
                    onClick={() => void onCreateVersion()}
                    disabled={busy}
                    className="rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
                  >
                    创建新版本
                  </button>
                )}
              </>
            )}
            <Link
              href={`/studio/projects/${encodeURIComponent(id)}/versions`}
              className="rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
            >
              查看版本记录
            </Link>
          </div>
        </Card>

        <Card extra="w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10">
          <div className="mb-3 flex items-center gap-2">
            <MdPhotoCamera className="h-5 w-5 text-gray-400" />
            <h2 className="text-base font-bold text-navy-700 dark:text-white">
              空房照片
            </h2>
          </div>
          <p className="text-sm text-gray-500">
            下一阶段实施。照片将绑定户型版本，不绑定软装方案。
          </p>
          <span className="mt-4 inline-flex rounded bg-gray-100 px-2 py-1 text-xs font-medium text-gray-500 dark:bg-navy-900">
            下一阶段
          </span>
        </Card>
      </div>
    </PageShell>
  );
}
