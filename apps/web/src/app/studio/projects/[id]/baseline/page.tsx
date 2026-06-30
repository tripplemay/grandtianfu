'use client';

import React, { use } from 'react';
import Link from 'next/link';
import Card from 'components/card';
import PageShell from 'components/studio/ui/PageShell';
import LoadingState from 'components/studio/ui/LoadingState';
import { BackendErrorBanner } from 'components/studio/ui/status';
import { useProjectWorkflow } from 'components/studio/workflow/ProjectWorkflowContext';
import { MdGridView, MdPhotoCamera } from 'react-icons/md';

export default function BaselinePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { currentBaseline, viewingBaseline, isHistorical, loading, error } =
    useProjectWorkflow();
  const baseline = viewingBaseline ?? currentBaseline;

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
            <Link
              href={`/studio/projects/${encodeURIComponent(id)}/editor`}
              className="rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
            >
              查看几何编辑器
            </Link>
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
