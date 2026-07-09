'use client';

import React, { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import { StatusBadge, Badge } from 'components/studio/ui/status';
import { Button, LinkButton } from 'components/studio/ui/buttons';
import { StudioCard, TimeAgo } from 'components/studio/ui/primitives';
import { useToastContext } from 'components/studio/ui/ToastHost';
import { useConfirm } from 'components/studio/ui/ConfirmDialog';
import { deleteBaseline, type BaselineMeta } from 'lib/studioApi';

// 某版本的方案/效果图计数 (含归档、已排除 default), 由合并页预取后传入,
// 供列表卡直接展示密度并复用于删除级联提示。
export interface VersionSchemeCount {
  schemes: number;
  renders: number;
}

// 版本号排序键:v2 > v1 > …;非 vN 排最后。
function versionSortKey(vid: string): number {
  const m = /^v(\d+)$/.exec(vid);
  return m ? parseInt(m[1], 10) : -1;
}

// 主从布局左栏:全部户型版本时间线。点卡切 ?version= (右栏展开该版本详情),
// 内联草稿编辑与软删。卡片/按钮一律复用设计系统 (StudioCard/Button), 选中态由
// StudioCard 统一以 brand 描边强调, 不手写浅底(避免深色主题下突兀、白字对比差)。
export default function VersionList({
  projectId,
  baselines,
  currentBaseline,
  viewingId,
  schemeCounts,
  reload,
}: {
  projectId: string;
  baselines: BaselineMeta[];
  currentBaseline: BaselineMeta | null;
  viewingId: string | null;
  schemeCounts: Record<string, VersionSchemeCount>;
  reload: () => Promise<void>;
}) {
  const router = useRouter();
  const { showToast } = useToastContext();
  const confirm = useConfirm();
  const [busy, setBusy] = useState<string | null>(null);

  // 当前版本置顶,其余按版本号倒序(最新在前)。
  const ordered = [...baselines].sort((a, b) => {
    if (a.id === currentBaseline?.id) return -1;
    if (b.id === currentBaseline?.id) return 1;
    return versionSortKey(b.id) - versionSortKey(a.id);
  });

  const select = useCallback(
    (versionId: string) => {
      if (versionId === viewingId) return;
      router.push(
        `/studio/projects/${encodeURIComponent(
          projectId,
        )}/baseline?version=${encodeURIComponent(versionId)}`,
      );
    },
    [projectId, viewingId, router],
  );

  const onDelete = useCallback(
    async (versionId: string, status: string) => {
      // 级联影响: 复用预取的方案/效果图计数 (default 已排除), 用于确认框如实告知。
      const count = schemeCounts[versionId];
      const impact =
        count && count.schemes
          ? `将连带删除 ${count.schemes} 个方案${
              count.renders ? `、${count.renders} 张效果图` : ''
            }。`
          : '';
      const label = status === 'draft' ? '草稿版本' : '历史版本';
      const ok = await confirm({
        title: `删除户型${label} ${versionId}`,
        // 修正原文案「可恢复」的误导 —— 代码库无户型恢复 API/UI, 不作虚假承诺。
        message: `${impact}此操作会将该版本及其方案移入回收站;已生成图片文件不会被删除。`,
        confirmText: '删除',
        cancelText: '取消',
        danger: true,
      });
      if (!ok) return;
      setBusy(`delete:${versionId}`);
      try {
        const res = await deleteBaseline(projectId, versionId);
        const n = res.schemes_trashed?.length ?? 0;
        showToast(
          `户型版本 ${versionId} 已删除${n ? `(连带 ${n} 个方案)` : ''}`,
          'success',
        );
        // 若删的正是当前所看版本, 回落到当前版本视图, 避免右栏停在已删版本。
        if (versionId === viewingId) {
          router.push(
            `/studio/projects/${encodeURIComponent(projectId)}/baseline`,
          );
        }
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
    [projectId, schemeCounts, viewingId, confirm, showToast, reload, router],
  );

  return (
    <div className="space-y-2">
      <h2 className="px-1 text-sm font-semibold text-gray-500 dark:text-gray-400">
        版本时间线
      </h2>
      {ordered.map((baseline) => {
        const current = baseline.id === currentBaseline?.id;
        const active = baseline.id === viewingId;
        // 可删: 非 v1(与根几何绑定)、非当前已确认版本、非最后一个版本、状态草稿/历史
        // (与后端 409 口径一致)。
        const deletable =
          baseline.id !== 'v1' &&
          !current &&
          baselines.length > 1 &&
          (baseline.status === 'draft' || baseline.status === 'superseded');
        const count = schemeCounts[baseline.id];
        return (
          <StudioCard
            key={baseline.id}
            interactive
            selected={active}
            ariaCurrent={active}
            onClick={() => select(baseline.id)}
            extra="!p-3"
          >
            <div className="flex items-center gap-2">
              <span className="font-bold text-navy-700 dark:text-white">
                户型 {baseline.id}
              </span>
              {current && <Badge tone="green">当前</Badge>}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
              <StatusBadge kind="baseline" status={baseline.status} />
              {count && count.schemes > 0 && (
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {count.schemes} 方案
                  {count.renders ? ` · ${count.renders} 图` : ''}
                </span>
              )}
            </div>
            {baseline.source_version_id && (
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                派生自 {baseline.source_version_id}
              </p>
            )}
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              <TimeAgo at={baseline.created_at} prefix="创建" />
              {baseline.confirmed_at && (
                <TimeAgo
                  at={baseline.confirmed_at}
                  prefix=" · 确认"
                  className="text-xs"
                />
              )}
            </div>
            {(baseline.status === 'draft' || deletable) && (
              <div
                className="mt-2 flex flex-wrap gap-2"
                onClick={(e) => e.stopPropagation()}
              >
                {baseline.status === 'draft' && (
                  <LinkButton
                    href={`/studio/projects/${encodeURIComponent(
                      projectId,
                    )}/editor?baseline=${encodeURIComponent(baseline.id)}`}
                    variant="primary"
                    size="sm"
                  >
                    编辑草稿
                  </LinkButton>
                )}
                {deletable && (
                  <Button
                    variant="danger-soft"
                    size="sm"
                    onClick={() => void onDelete(baseline.id, baseline.status)}
                    disabled={busy === `delete:${baseline.id}`}
                  >
                    {busy === `delete:${baseline.id}` ? '删除中…' : '删除'}
                  </Button>
                )}
              </div>
            )}
          </StudioCard>
        );
      })}
    </div>
  );
}
