'use client';

import React, { use } from 'react';
import PageShell from 'components/studio/ui/PageShell';
import LoadingState from 'components/studio/ui/LoadingState';
import {
  BackendErrorBanner,
  StatusBadge,
  Badge,
} from 'components/studio/ui/status';
import { LinkButton } from 'components/studio/ui/buttons';
import { StudioCard, TimeAgo } from 'components/studio/ui/primitives';
import { useProjectWorkflow } from 'components/studio/workflow/ProjectWorkflowContext';

// 版本号排序键:v2 > v1 > …;非 vN 排最后。
function versionSortKey(vid: string): number {
  const m = /^v(\d+)$/.exec(vid);
  return m ? parseInt(m[1], 10) : -1;
}

export default function VersionsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { baselines, currentBaseline, loading, error } = useProjectWorkflow();

  // 当前版本置顶,其余按版本号倒序(最新在前),便于一眼看到当前与最近版本。
  const ordered = [...baselines].sort((a, b) => {
    if (a.id === currentBaseline?.id) return -1;
    if (b.id === currentBaseline?.id) return 1;
    return versionSortKey(b.id) - versionSortKey(a.id);
  });

  return (
    <PageShell
      title="版本记录"
      description="查看户型版本生命周期。历史版本下的方案不会混入当前方案列表。"
      state={loading ? <LoadingState rows={2} /> : undefined}
    >
      {error && <BackendErrorBanner message={error} />}
      <div className="space-y-3">
        {ordered.map((baseline) => {
          const current = baseline.id === currentBaseline?.id;
          return (
            <StudioCard key={baseline.id}>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-bold text-navy-700 dark:text-white">
                      户型 {baseline.id}
                    </h2>
                    {current && <Badge tone="green">当前</Badge>}
                  </div>
                  <div className="mt-1">
                    <StatusBadge kind="baseline" status={baseline.status} />
                  </div>
                </div>
                <div className="flex flex-col gap-2 text-xs text-gray-500 sm:items-end">
                  <div className="sm:text-right">
                    <TimeAgo
                      at={baseline.created_at}
                      prefix="创建"
                      className="block text-xs text-gray-500"
                    />
                    {baseline.confirmed_at && (
                      <TimeAgo
                        at={baseline.confirmed_at}
                        prefix="确认"
                        className="block text-xs text-gray-500"
                      />
                    )}
                    {baseline.superseded_at && (
                      <TimeAgo
                        at={baseline.superseded_at}
                        prefix="替代"
                        className="block text-xs text-gray-500"
                      />
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <LinkButton
                      href={`/studio/projects/${encodeURIComponent(
                        id,
                      )}/baseline?version=${encodeURIComponent(baseline.id)}`}
                      variant="secondary"
                    >
                      查看
                    </LinkButton>
                    {baseline.status === 'draft' && (
                      <LinkButton
                        href={`/studio/projects/${encodeURIComponent(
                          id,
                        )}/editor?baseline=${encodeURIComponent(baseline.id)}`}
                        variant="primary"
                      >
                        编辑草稿
                      </LinkButton>
                    )}
                  </div>
                </div>
              </div>
            </StudioCard>
          );
        })}
      </div>
    </PageShell>
  );
}
