'use client';

import React, { use } from 'react';
import Link from 'next/link';
import Card from 'components/card';
import PageShell from 'components/studio/ui/PageShell';
import LoadingState from 'components/studio/ui/LoadingState';
import { BackendErrorBanner } from 'components/studio/ui/status';
import { useProjectWorkflow } from 'components/studio/workflow/ProjectWorkflowContext';

export default function VersionsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { baselines, currentBaseline, loading, error } = useProjectWorkflow();

  return (
    <PageShell
      title="版本记录"
      description="查看户型版本生命周期。历史版本下的方案不会混入当前方案列表。"
      state={loading ? <LoadingState rows={2} /> : undefined}
    >
      {error && <BackendErrorBanner message={error} />}
      <div className="space-y-3">
        {baselines.map((baseline) => {
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
                  <p className="mt-1 text-sm text-gray-500">
                    状态：{baseline.status}
                  </p>
                </div>
                <div className="flex flex-col gap-2 text-xs text-gray-500 sm:items-end">
                  <div>
                    <p>创建：{baseline.created_at ?? '-'}</p>
                    <p>确认：{baseline.confirmed_at ?? '-'}</p>
                    <p>替代：{baseline.superseded_at ?? '-'}</p>
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
