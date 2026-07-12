'use client';

import React, { use, useCallback, useEffect, useState } from 'react';
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
import { StudioCard, TimeAgo } from 'components/studio/ui/primitives';
import RenderImage from 'components/studio/ui/RenderImage';
import BaselinePhotosCard from 'components/studio/baseline/BaselinePhotosCard';
import BaselineReadinessPanel from 'components/studio/baseline/BaselineReadinessPanel';
import VersionList, {
  type VersionSchemeCount,
} from 'components/studio/baseline/VersionList';
import { useProjectWorkflow } from 'components/studio/workflow/ProjectWorkflowContext';
import { useToastContext } from 'components/studio/ui/ToastHost';
import { useConfirm } from 'components/studio/ui/ConfirmDialog';
import {
  createBaseline,
  confirmBaseline,
  listSchemes,
  API_BASE,
} from 'lib/studioApi';
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
    baselines,
    isHistorical,
    loading,
    error,
    reload,
  } = useProjectWorkflow();
  const { showToast } = useToastContext();
  const confirm = useConfirm();
  const [busy, setBusy] = useState(false);
  // P0-1: 照片/家具变化后 bump, 触发 readiness 面板重取 (避免陈旧)。
  const [readinessTick, setReadinessTick] = useState(0);
  const [schemeCounts, setSchemeCounts] = useState<
    Record<string, VersionSchemeCount>
  >({});
  const baseline = viewingBaseline ?? currentBaseline;

  // 各版本方案/效果图计数 (含归档、排除 default, 与删除级联口径一致): 供版本列表卡与
  // 详情区展示密度、并复用于删除确认。版本数很少 (D 仅 v1), 逐版本拉取成本可忽略。
  useEffect(() => {
    let alive = true;
    void (async () => {
      const entries = await Promise.all(
        baselines.map(async (b) => {
          try {
            const list = (
              await listSchemes(id, {
                baselineVersionId: b.id,
                includeArchived: true,
              })
            ).filter((sc) => sc.id !== 'default');
            const renders = list.reduce((s, sc) => s + (sc.renders ?? 0), 0);
            return [b.id, { schemes: list.length, renders }] as const;
          } catch {
            return [b.id, { schemes: 0, renders: 0 }] as const;
          }
        }),
      );
      if (alive) setSchemeCounts(Object.fromEntries(entries));
    })();
    return () => {
      alive = false;
    };
  }, [id, baselines]);

  // 前置校验(消除晚失败):草稿卡就地展示 validation_issues, 存在 ERROR 时禁用确认按钮。
  const issues = baseline?.validation_issues ?? [];
  const vErrors = issues
    .filter((i) => i.level === 'ERROR')
    .map((i) => i.message);
  const vWarns = issues.filter((i) => i.level === 'WARN').map((i) => i.message);
  const viewingCount = baseline ? schemeCounts[baseline.id] : undefined;
  // 户型平面缩略图仅对「当前生效版本」可用: render 端点渲染的是 current/根几何,
  // 不接受版本参数, 故历史/草稿版本不显示缩略图 (待后端 render 支持 version 参数后再放开)。
  const showThumb = !isHistorical && baseline?.status === 'confirmed';

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

  const description =
    '户型版本是软装方案共享的空间基础；已确认版本只读，调整必须创建新版本。左侧切换版本，右侧查看该版本详情与空房照。';

  if (loading) {
    return (
      <PageShell
        title="户型基线"
        description={description}
        state={<LoadingState rows={2} />}
      />
    );
  }

  if (!baseline) {
    return (
      <PageShell title="户型基线" description={description}>
        {error && <BackendErrorBanner message={error} />}
        <EmptyState
          title="暂无户型基线"
          description="当前项目还没有可查看的户型版本。请先创建或确认户型基线。"
        />
      </PageShell>
    );
  }

  const isDraft = baseline.status === 'draft';
  const readOnlyPhotos = baseline.status === 'superseded' || isHistorical;

  return (
    <PageShell title="户型基线" description={description}>
      {error && <BackendErrorBanner message={error} />}
      <div className="grid gap-4 lg:grid-cols-[minmax(230px,300px)_1fr]">
        {/* 左栏:版本时间线 (主从的「主」) */}
        <VersionList
          projectId={id}
          baselines={baselines}
          currentBaseline={currentBaseline}
          viewingId={baseline.id}
          schemeCounts={schemeCounts}
          reload={reload}
        />

        {/* 右栏:所选版本详情 (主从的「从」) */}
        <div className="space-y-4">
          {/* P0-1: 后端权威的生成就绪度 (户型/家具/照片聚合评估), 取代前端各处派生。 */}
          <BaselineReadinessPanel
            projectId={id}
            versionId={baseline.id}
            reloadKey={readinessTick}
            canEdit={!isHistorical}
          />
          <StudioCard>
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <MdGridView className="h-5 w-5 text-brand-500" />
                <h2 className="text-base font-bold text-navy-700 dark:text-white">
                  户型 {baseline.id}
                </h2>
              </div>
              <StatusRow kind="baseline" status={baseline.status} />
            </div>

            <div className="grid gap-4 sm:grid-cols-[auto_1fr]">
              {showThumb && (
                <RenderImage
                  src={`${API_BASE}/projects/${encodeURIComponent(
                    id,
                  )}/render?mode=plan2d`}
                  alt={`户型 ${baseline.id} 平面`}
                  className="h-36 w-full rounded-xl bg-gray-50 dark:bg-navy-900 sm:w-52"
                  imgClassName="h-full w-full object-contain"
                  fallbackLabel="户型平面"
                />
              )}
              <div className="min-w-0">
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  {isDraft
                    ? '草稿版本可编辑和校验，确认后才允许创建方案。'
                    : baseline.status === 'superseded' || isHistorical
                    ? '历史户型版本只允许查看和导出。'
                    : '已锁定，所有当前方案基于此版本。'}
                </p>
                {/* 元信息:时间戳 / 派生血缘 / 关联方案 —— 数据早已在手, 补齐密度。 */}
                <dl className="mt-3 space-y-1 text-xs text-gray-500 dark:text-gray-400">
                  <div className="flex flex-wrap gap-x-3 gap-y-1">
                    <TimeAgo at={baseline.created_at} prefix="创建" />
                    {baseline.confirmed_at && (
                      <TimeAgo at={baseline.confirmed_at} prefix="确认" />
                    )}
                    {baseline.superseded_at && (
                      <TimeAgo at={baseline.superseded_at} prefix="替代" />
                    )}
                  </div>
                  {baseline.source_version_id && (
                    <div>派生自 {baseline.source_version_id}</div>
                  )}
                  {viewingCount && (
                    <div>
                      关联 {viewingCount.schemes} 个方案
                      {viewingCount.renders
                        ? ` · ${viewingCount.renders} 张效果图`
                        : ''}
                    </div>
                  )}
                </dl>
              </div>
            </div>

            {/* 校验:草稿显示可定位的校验详情(含 ERROR 禁确认);已确认/历史显示当初校验结论。 */}
            <div className="mt-3 border-t border-gray-200 pt-3 dark:border-white/10">
              {isDraft ? (
                <StatusLines
                  errors={vErrors}
                  warns={vWarns}
                  okText="校验通过，可确认并锁定户型。"
                  hintText="进入编辑器编辑户型后会自动校验空间 / 门窗 / 重叠。"
                />
              ) : (
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {issues.length === 0
                    ? '校验：确认时无告警。'
                    : `校验：${
                        vErrors.length ? `${vErrors.length} 处错误 / ` : ''
                      }${vWarns.length} 处警告（确认时记录）。`}
                </p>
              )}
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {isDraft ? (
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
                  {baseline.status === 'confirmed' && (
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
            </div>
          </StudioCard>

          <BaselinePhotosCard
            projectId={id}
            versionId={baseline.id}
            readOnly={readOnlyPhotos}
            onPhotosChanged={() => setReadinessTick((t) => t + 1)}
          />
        </div>
      </div>
    </PageShell>
  );
}
