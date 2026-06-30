'use client';

import React, { use } from 'react';
import Link from 'next/link';
import Card from 'components/card';
import PageShell from 'components/studio/ui/PageShell';
import LoadingState from 'components/studio/ui/LoadingState';
import RenderImage from 'components/studio/ui/RenderImage';
import { BackendErrorBanner } from 'components/studio/ui/status';
import { useProjectWorkflow } from 'components/studio/workflow/ProjectWorkflowContext';
import { MdChair, MdGridView, MdStar } from 'react-icons/md';

export default function OverviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const {
    project,
    currentBaseline,
    availableSchemes,
    loading,
    error,
  } = useProjectWorkflow();

  const preferred = availableSchemes.find((scheme) => scheme.preferred);
  const latest = [...availableSchemes]
    .filter((scheme) => !!scheme.updated_at)
    .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))[0];
  const latestArtifact = [...availableSchemes]
    .filter((scheme) => !!scheme.latest_render_url)
    .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))[0];
  const warnings =
    currentBaseline?.validation_issues?.filter((issue) => issue.level !== 'INFO') ??
    [];

  return (
    <PageShell
      title="项目概览"
      description={
        project
          ? `${project.name} / 户型 ${currentBaseline?.id ?? project.current_baseline_version_id}`
          : `项目 ${id}`
      }
      state={loading ? <LoadingState rows={2} /> : undefined}
    >
      {error && <BackendErrorBanner message={error} />}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card extra="w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10">
          <div className="mb-3 flex items-center gap-2">
            <MdGridView className="h-5 w-5 text-brand-500" />
            <h2 className="text-base font-bold text-navy-700 dark:text-white">
              当前户型版本
            </h2>
          </div>
          <p className="text-3xl font-bold text-navy-700 dark:text-white">
            {currentBaseline?.id ?? 'v1'}
          </p>
          <p className="mt-1 text-sm text-gray-500">
            状态：{currentBaseline?.status ?? 'confirmed'}
          </p>
          <Link
            href={`/studio/projects/${encodeURIComponent(id)}/baseline`}
            className="mt-4 inline-flex rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
          >
            查看户型基线
          </Link>
        </Card>

        <Card extra="w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10">
          <div className="mb-3 flex items-center gap-2">
            <MdChair className="h-5 w-5 text-brand-500" />
            <h2 className="text-base font-bold text-navy-700 dark:text-white">
              当前版本方案
            </h2>
          </div>
          <p className="text-3xl font-bold text-navy-700 dark:text-white">
            {availableSchemes.length}
          </p>
          <p className="mt-1 text-sm text-gray-500">
            默认仅统计当前户型版本下未归档方案。
          </p>
          <Link
            href={`/studio/projects/${encodeURIComponent(id)}/scheme`}
            className="mt-4 inline-flex rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
          >
            进入方案中心
          </Link>
        </Card>

        <Card extra="w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10">
          <div className="mb-3 flex items-center gap-2">
            <MdStar className="h-5 w-5 text-amber-500" />
            <h2 className="text-base font-bold text-navy-700 dark:text-white">
              首选方案
            </h2>
          </div>
          {preferred ? (
            <>
              <p className="text-xl font-bold text-navy-700 dark:text-white">
                {preferred.name}
              </p>
              <p className="mt-1 text-sm text-gray-500">
                状态：{preferred.status}
              </p>
              <Link
                href={`/studio/projects/${encodeURIComponent(
                  id,
                )}/editor?scheme=${encodeURIComponent(preferred.id)}`}
                className="mt-4 inline-flex rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
              >
                查看首选方案
              </Link>
            </>
          ) : (
            <p className="text-sm text-gray-500">尚未设置首选方案。</p>
          )}
        </Card>
      </div>

      <Card extra="mt-4 w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10">
        <h2 className="text-base font-bold text-navy-700 dark:text-white">
          最近更新
        </h2>
        {latestArtifact ? (
          <div className="mt-3 grid gap-3 md:grid-cols-[220px_1fr]">
            <RenderImage
              src={latestArtifact.latest_render_url || ''}
              alt={`${latestArtifact.name} 最近成果`}
              className="h-32 rounded-xl bg-gray-50 dark:bg-navy-900"
              imgClassName="h-32 w-full object-cover"
              fallbackLabel="最近成果加载失败"
            />
            <p className="text-sm text-gray-600 dark:text-gray-300">
              {latestArtifact.name} · 家具 {latestArtifact.items} · 效果图{' '}
              {latestArtifact.renders} · {latestArtifact.updated_at}
            </p>
          </div>
        ) : latest ? (
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
            {latest.name} · 家具 {latest.items} · 效果图 {latest.renders} ·{' '}
            {latest.updated_at}
          </p>
        ) : (
          <p className="mt-2 text-sm text-gray-500">暂无最近更新。</p>
        )}
      </Card>

      <Card extra="mt-4 w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10">
        <h2 className="text-base font-bold text-navy-700 dark:text-white">
          待处理警告
        </h2>
        {warnings.length > 0 ? (
          <div className="mt-2 space-y-1">
            {warnings.map((issue, idx) => (
              <p key={`${issue.message}-${idx}`} className="text-sm text-amber-600">
                {issue.level}: {issue.message}
              </p>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-gray-500">暂无待处理警告。</p>
        )}
      </Card>
    </PageShell>
  );
}
