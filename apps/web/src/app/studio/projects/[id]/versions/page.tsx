'use client';

import React, { use, useCallback, useState } from 'react';
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
import { useToastContext } from 'components/studio/ui/ToastHost';
import { useConfirm } from 'components/studio/ui/ConfirmDialog';
import { deleteBaseline, listSchemes } from 'lib/studioApi';

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
  const { baselines, currentBaseline, loading, error, reload } =
    useProjectWorkflow();
  const { showToast } = useToastContext();
  const confirm = useConfirm();
  const [busy, setBusy] = useState<string | null>(null);

  // 当前版本置顶,其余按版本号倒序(最新在前),便于一眼看到当前与最近版本。
  const ordered = [...baselines].sort((a, b) => {
    if (a.id === currentBaseline?.id) return -1;
    if (b.id === currentBaseline?.id) return 1;
    return versionSortKey(b.id) - versionSortKey(a.id);
  });

  const onDelete = useCallback(
    async (versionId: string, status: string) => {
      // 级联影响预取: 该版本绑定的方案数 + 效果图数 (含归档), 用于确认框如实告知。
      let impact = '';
      try {
        // default 方案不进级联回收站 (后端重 pin 到 current), 计数须排除以与后端一致。
        const bound = (
          await listSchemes(id, {
            baselineVersionId: versionId,
            includeArchived: true,
          })
        ).filter((sc) => sc.id !== 'default');
        const renders = bound.reduce((s, sc) => s + (sc.renders ?? 0), 0);
        if (bound.length) {
          impact = `将连带删除 ${bound.length} 个方案${
            renders ? `、${renders} 张效果图` : ''
          }。`;
        }
      } catch {
        /* 预取失败不阻断删除, 确认框退化为不含数量 */
      }
      const label = status === 'draft' ? '草稿版本' : '历史版本';
      const ok = await confirm({
        title: `删除户型${label} ${versionId}`,
        message: `${impact}此操作会移入回收站,可恢复;已生成图片文件不会被删除。`,
        confirmText: '删除',
        cancelText: '取消',
        danger: true,
      });
      if (!ok) return;
      setBusy(`delete:${versionId}`);
      try {
        const res = await deleteBaseline(id, versionId);
        const n = res.schemes_trashed?.length ?? 0;
        showToast(
          `户型版本 ${versionId} 已删除${n ? `(连带 ${n} 个方案)` : ''}`,
          'success',
        );
        await reload();
      } catch (e) {
        showToast(
          `删除失败:${e instanceof Error ? e.message : String(e)}`,
          'error',
        );
      } finally {
        setBusy(null);
      }
    },
    [id, confirm, showToast, reload],
  );

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
          // 可删: 非 v1(与根几何绑定不可删)、非当前已确认版本、非最后一个版本、
          // 状态为草稿/历史 (与后端 409 口径一致)。
          const deletable =
            baseline.id !== 'v1' &&
            !current &&
            baselines.length > 1 &&
            (baseline.status === 'draft' || baseline.status === 'superseded');
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
                    {deletable && (
                      <button
                        type="button"
                        onClick={() =>
                          void onDelete(baseline.id, baseline.status)
                        }
                        disabled={busy === `delete:${baseline.id}`}
                        className="rounded-lg border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-red-500/30 dark:hover:bg-red-900"
                      >
                        {busy === `delete:${baseline.id}` ? '删除中…' : '删除'}
                      </button>
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
