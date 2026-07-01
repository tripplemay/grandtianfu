'use client';

import React, { use } from 'react';
import Link from 'next/link';
import Card from 'components/card';
import PageShell from 'components/studio/ui/PageShell';
import LoadingState from 'components/studio/ui/LoadingState';
import { BackendErrorBanner, StatusBadge } from 'components/studio/ui/status';
import { useProjectWorkflow } from 'components/studio/workflow/ProjectWorkflowContext';
import { relativeTime } from 'lib/time';

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
            <Card
              key={baseline.id}
              extra="w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10"
            >
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-bold text-navy-700 dark:text-white">
                      户型 {baseline.id}
                    </h2>
                    {current && (
                      <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                        当前
                      </span>
                    )}
                  </div>
                  <div className="mt-1">
                    <StatusBadge kind="baseline" status={baseline.status} />
                  </div>
                </div>
                <div className="flex flex-col gap-2 text-xs text-gray-500 sm:items-end">
                  <div className="sm:text-right">
                    <p title={baseline.created_at ?? undefined}>
                      创建 {relativeTime(baseline.created_at)}
                    </p>
                    {baseline.confirmed_at && (
                      <p title={baseline.confirmed_at}>
                        确认 {relativeTime(baseline.confirmed_at)}
                      </p>
                    )}
                    {baseline.superseded_at && (
                      <p title={baseline.superseded_at}>
                        替代 {relativeTime(baseline.superseded_at)}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link
                      href={`/studio/projects/${encodeURIComponent(
                        id,
                      )}/baseline?version=${encodeURIComponent(baseline.id)}`}
                      className="rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
                    >
                      查看
                    </Link>
                    {baseline.status === 'draft' && (
                      <Link
                        href={`/studio/projects/${encodeURIComponent(
                          id,
                        )}/editor?baseline=${encodeURIComponent(baseline.id)}`}
                        className="rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
                      >
                        编辑草稿
                      </Link>
                    )}
                  </div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </PageShell>
  );
}
