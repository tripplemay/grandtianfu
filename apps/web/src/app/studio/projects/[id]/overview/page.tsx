'use client';

import React, { use } from 'react';
import PageShell from 'components/studio/ui/PageShell';
import LoadingState from 'components/studio/ui/LoadingState';
import RenderImage from 'components/studio/ui/RenderImage';
import {
  BackendErrorBanner,
  StatusRow,
  StatusLines,
} from 'components/studio/ui/status';
import { LinkButton } from 'components/studio/ui/buttons';
import { StudioCard, TimeAgo } from 'components/studio/ui/primitives';
import { useProjectWorkflow } from 'components/studio/workflow/ProjectWorkflowContext';
import ProjectWorkflowGuide from 'components/studio/workflow/ProjectWorkflowGuide';
import { MdChair, MdGridView, MdStar } from 'react-icons/md';

export default function OverviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { project, currentBaseline, availableSchemes, loading, error } =
    useProjectWorkflow();

  const preferred = availableSchemes.find((scheme) => scheme.preferred);
  const latest = [...availableSchemes]
    .filter((scheme) => !!scheme.updated_at)
    .sort((a, b) =>
      String(b.updated_at).localeCompare(String(a.updated_at)),
    )[0];
  const latestArtifact = [...availableSchemes]
    .filter((scheme) => !!scheme.latest_render_url)
    .sort((a, b) =>
      String(b.updated_at).localeCompare(String(a.updated_at)),
    )[0];
  const issues =
    currentBaseline?.validation_issues?.filter(
      (issue) => issue.level !== 'INFO',
    ) ?? [];
  const issueErrors = issues
    .filter((issue) => issue.level === 'ERROR')
    .map((issue) => issue.message);
  const issueWarns = issues
    .filter((issue) => issue.level !== 'ERROR')
    .map((issue) => issue.message);

  return (
    <PageShell
      title="项目概览"
      description={
        project
          ? `${project.name} / 户型 ${
              currentBaseline?.id ?? project.current_baseline_version_id
            }`
          : `项目 ${id}`
      }
      state={loading ? <LoadingState rows={2} /> : undefined}
    >
      {error && <BackendErrorBanner message={error} />}
      <ProjectWorkflowGuide projectId={id} />
      <div className="grid gap-4 lg:grid-cols-3">
        <StudioCard>
          <div className="mb-3 flex items-center gap-2">
            <MdGridView className="h-5 w-5 text-brand-500" />
            <h2 className="text-base font-bold text-navy-700 dark:text-white">
              当前户型版本
            </h2>
          </div>
          <p className="text-3xl font-bold text-navy-700 dark:text-white">
            {currentBaseline?.id ?? 'v1'}
          </p>
          <div className="mt-1">
            <StatusRow kind="baseline" status={currentBaseline?.status} />
          </div>
          <LinkButton
            href={`/studio/projects/${encodeURIComponent(id)}/baseline`}
            variant="secondary"
            className="mt-4"
          >
            查看户型基线
          </LinkButton>
        </StudioCard>

        <StudioCard>
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
          <LinkButton
            href={`/studio/projects/${encodeURIComponent(id)}/scheme`}
            variant="secondary"
            className="mt-4"
          >
            进入方案中心
          </LinkButton>
        </StudioCard>

        <StudioCard>
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
              <div className="mt-1">
                <StatusRow kind="scheme" status={preferred.status} />
              </div>
              <LinkButton
                href={`/studio/projects/${encodeURIComponent(
                  id,
                )}/editor?scheme=${encodeURIComponent(preferred.id)}`}
                variant="primary"
                className="mt-4"
              >
                查看首选方案
              </LinkButton>
            </>
          ) : (
            <p className="text-sm text-gray-500">尚未设置首选方案。</p>
          )}
        </StudioCard>
      </div>

      <StudioCard extra="mt-4">
        <h2 className="text-base font-bold text-navy-700 dark:text-white">
          最近更新
        </h2>
        {latestArtifact ? (
          <div className="mt-3 grid gap-3 md:grid-cols-[220px_1fr]">
            <RenderImage
              src={
                latestArtifact.latest_render_thumb_url ??
                (latestArtifact.latest_render_url || '')
              }
              alt={`${latestArtifact.name} 最近成果`}
              className="h-32 rounded-xl bg-gray-50 dark:bg-navy-900"
              imgClassName="h-32 w-full object-cover"
              fallbackLabel="最近成果加载失败"
            />
            <p className="text-sm text-gray-600 dark:text-gray-300">
              {latestArtifact.name} · 家具 {latestArtifact.items} · 效果图{' '}
              {latestArtifact.renders} ·{' '}
              <TimeAgo
                at={latestArtifact.updated_at}
                prefix="更新"
                className=""
              />
            </p>
          </div>
        ) : latest ? (
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
            {latest.name} · 家具 {latest.items} · 效果图 {latest.renders} ·{' '}
            <TimeAgo at={latest.updated_at} prefix="更新" className="" />
          </p>
        ) : (
          <p className="mt-2 text-sm text-gray-500">暂无最近更新。</p>
        )}
      </StudioCard>

      <StudioCard extra="mt-4">
        <h2 className="text-base font-bold text-navy-700 dark:text-white">
          待处理警告
        </h2>
        {issues.length > 0 ? (
          <div className="mt-2">
            <StatusLines errors={issueErrors} warns={issueWarns} />
          </div>
        ) : (
          <p className="mt-2 text-sm text-gray-500">暂无待处理警告。</p>
        )}
      </StudioCard>
    </PageShell>
  );
}
