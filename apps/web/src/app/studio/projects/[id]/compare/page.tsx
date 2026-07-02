'use client';

import React, { use, useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import PageShell from 'components/studio/ui/PageShell';
import EmptyState from 'components/studio/ui/EmptyState';
import LoadingState from 'components/studio/ui/LoadingState';
import RenderImage from 'components/studio/ui/RenderImage';
import { Button, LinkButton } from 'components/studio/ui/buttons';
import { StudioCard } from 'components/studio/ui/primitives';
import {
  BackendErrorBanner,
  PreferredBadge,
  statusLabel,
} from 'components/studio/ui/status';
import {
  API_BASE,
  fetchScheme,
  listRenders,
  listSchemes,
  setPreferredScheme,
  type FurnitureSchemeSummary,
  type RenderRecord,
} from 'lib/studioApi';
import { MdCompare, MdImage } from 'react-icons/md';
import { useToastContext } from 'components/studio/ui/ToastHost';

type CompareMode = 'plan2d' | 'photo' | 'ai';

const VIEW_OPTIONS: Array<{
  value: CompareMode;
  label: string;
  disabled?: boolean;
}> = [
  { value: 'plan2d', label: '家具平面图' },
  { value: 'photo', label: '轴测方案图' },
  { value: 'ai', label: 'AI 效果图' },
  { value: 'ai', label: '实拍效果图（下一阶段）', disabled: true },
];

function renderSrc(
  projectId: string,
  schemeId: string,
  mode: 'plan2d' | 'photo',
) {
  return `${API_BASE}/projects/${encodeURIComponent(
    projectId,
  )}/schemes/${encodeURIComponent(schemeId)}/render?mode=${mode}`;
}

export default function ComparePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const search = useSearchParams();
  const selectedIds = useMemo(
    () =>
      (search.get('schemes') || '')
        .split(',')
        .map((part) => part.trim())
        .filter(Boolean)
        .slice(0, 3),
    [search],
  );
  const [schemes, setSchemes] = useState<FurnitureSchemeSummary[]>([]);
  const [renders, setRenders] = useState<Record<string, RenderRecord[]>>({});
  const [mode, setMode] = useState<CompareMode>('plan2d');
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [error, setError] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<{ src: string; alt: string } | null>(
    null,
  );
  const { showToast } = useToastContext();

  // 灯箱:Esc 关闭。
  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setLightbox(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [lightbox]);

  const reload = useCallback(async () => {
    try {
      setLoadState('loading');
      const metas = await Promise.all(
        selectedIds.map((sid) => fetchScheme(id, sid)),
      );
      // 家具数取所属户型版本的方案列表 _summary(已算),效果图数取 listRenders 长度,
      // 不再硬编码为 0(修复对比列头恒显 0 的误导)。
      const baselines = Array.from(
        new Set(metas.map((m) => m.baseline_version_id || 'v1')),
      );
      const summaryLists = await Promise.all(
        baselines.map((bv) =>
          listSchemes(id, { baselineVersionId: bv, includeArchived: true }),
        ),
      );
      const summaryMap = new Map<string, FurnitureSchemeSummary>();
      for (const list of summaryLists) {
        for (const s of list) summaryMap.set(s.id, s);
      }
      const renderEntries = await Promise.all(
        metas.map(async (m) => [m.id, await listRenders(id, m.id)] as const),
      );
      const rendersMap = Object.fromEntries(renderEntries);
      const selected = metas.map(
        (m) =>
          ({
            id: m.id,
            name: m.name,
            source: m.source,
            status: m.status,
            baseline_version_id: m.baseline_version_id,
            preferred: m.preferred,
            archived_at: m.archived_at,
            items: summaryMap.get(m.id)?.items ?? 0,
            renders: rendersMap[m.id]?.length ?? 0,
            updated_at: m.updated_at ?? null,
          } as FurnitureSchemeSummary),
      );
      setSchemes(selected);
      setRenders(rendersMap);
      setError(null);
      setLoadState('ready');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLoadState('error');
    }
  }, [id, selectedIds]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const baselineIds = Array.from(
    new Set(schemes.map((scheme) => scheme.baseline_version_id || 'v1')),
  );
  const validCount = selectedIds.length >= 2 && selectedIds.length <= 3;
  const sameBaseline = baselineIds.length <= 1;

  const onPreferred = useCallback(
    async (scheme: FurnitureSchemeSummary) => {
      // 乐观更新:本地翻转 preferred 唯一性,不整页 reload(避免坍成 LoadingState、
      // 丢失滚动与对比现场)。失败回滚。
      const prev = schemes;
      setSchemes(schemes.map((s) => ({ ...s, preferred: s.id === scheme.id })));
      try {
        await setPreferredScheme(id, scheme.id);
        showToast('首选方案已更新', 'success');
      } catch (e) {
        setSchemes(prev);
        showToast(
          `设置失败:${e instanceof Error ? e.message : String(e)}`,
          'error',
        );
      }
    },
    [id, schemes, showToast],
  );

  return (
    <PageShell
      title="方案对比"
      description="选择同一户型版本下 2–3 套方案，使用统一视图并排比较。"
      state={loadState === 'loading' ? <LoadingState rows={2} /> : undefined}
    >
      {error && <BackendErrorBanner message={error} />}

      {loadState === 'ready' && !validCount ? (
        <EmptyState
          icon={<MdCompare className="h-6 w-6" />}
          title="请选择 2–3 套方案"
          description="从方案中心勾选方案后进入对比。"
          action={
            <LinkButton
              href={`/studio/projects/${encodeURIComponent(id)}/scheme`}
            >
              返回方案中心
            </LinkButton>
          }
        />
      ) : loadState === 'ready' && !sameBaseline ? (
        <EmptyState
          icon={<MdCompare className="h-6 w-6" />}
          title="不能比较不同户型版本的方案"
          description="请返回方案中心，选择同一户型版本下的方案。"
        />
      ) : (
        <div className="flex flex-col gap-4">
          <StudioCard>
            <div className="flex flex-wrap gap-2">
              {VIEW_OPTIONS.map((option) => (
                <button
                  key={option.label}
                  type="button"
                  disabled={option.disabled}
                  onClick={() => setMode(option.value)}
                  className={`rounded-lg px-3 py-2 text-sm font-medium ${
                    option.disabled
                      ? 'cursor-not-allowed bg-gray-50 text-gray-400 dark:bg-navy-900'
                      : mode === option.value
                      ? 'bg-brand-500 text-white shadow'
                      : 'bg-gray-100 text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white'
                  }`}
                >
                  {option.label}
                </button>
              ))}
              <span className="rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-500 dark:bg-navy-900">
                户型 {baselineIds[0] ?? 'v1'}
              </span>
            </div>
          </StudioCard>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
            {schemes.map((scheme) => {
              const latestRender = renders[scheme.id]?.[0];
              const imgSrc =
                mode === 'ai'
                  ? latestRender?.url
                  : renderSrc(id, scheme.id, mode);
              const imgAlt =
                mode === 'ai'
                  ? `${scheme.name} AI 效果图`
                  : `${scheme.name} ${mode}`;
              return (
                <StudioCard key={scheme.id} extra="flex min-h-[520px] flex-col">
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-lg font-bold text-navy-700 dark:text-white">
                          {scheme.name}
                        </h2>
                        {scheme.preferred && <PreferredBadge />}
                      </div>
                      <p className="mt-1 text-xs text-gray-500">
                        {statusLabel('scheme', scheme.status)} · 家具{' '}
                        {scheme.items} · 效果图 {scheme.renders}
                      </p>
                    </div>
                    {!scheme.preferred && (
                      <Button
                        variant="soft-amber"
                        onClick={() => void onPreferred(scheme)}
                      >
                        设为首选
                      </Button>
                    )}
                  </div>

                  <div className="flex flex-1 items-center justify-center overflow-hidden rounded-xl bg-gray-50 dark:bg-navy-900">
                    {mode === 'ai' && !latestRender ? (
                      <EmptyState
                        icon={<MdImage className="h-6 w-6" />}
                        title="缺少 AI 效果图"
                        description="进入该方案生成效果图后可在此比较。"
                        action={
                          <LinkButton
                            href={`/studio/projects/${encodeURIComponent(
                              id,
                            )}/render?scheme=${encodeURIComponent(scheme.id)}`}
                          >
                            去生成
                          </LinkButton>
                        }
                      />
                    ) : imgSrc ? (
                      <button
                        type="button"
                        onClick={() =>
                          setLightbox({ src: imgSrc, alt: imgAlt })
                        }
                        title="点击放大查看"
                        className="h-full w-full cursor-zoom-in"
                      >
                        <RenderImage
                          src={imgSrc}
                          alt={imgAlt}
                          className="h-[360px] w-full"
                          imgClassName="h-[360px] w-full object-contain"
                          fallbackLabel="方案图加载失败"
                        />
                      </button>
                    ) : null}
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    <LinkButton
                      variant="secondary"
                      href={`/studio/projects/${encodeURIComponent(
                        id,
                      )}/editor?scheme=${encodeURIComponent(scheme.id)}`}
                    >
                      打开方案
                    </LinkButton>
                    <LinkButton
                      variant="secondary"
                      href={`/studio/projects/${encodeURIComponent(id)}/scheme`}
                    >
                      退出对比
                    </LinkButton>
                  </div>
                </StudioCard>
              );
            })}
          </div>
        </div>
      )}

      {lightbox && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="放大查看"
          onClick={() => setLightbox(null)}
          className="bg-black/70 fixed inset-0 z-50 flex items-center justify-center p-6"
        >
          {/* 灯箱直接用原始渲染 URL(SVG/PNG),静态导出下不走 next/image */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={lightbox.src}
            alt={lightbox.alt}
            className="max-h-full max-w-full cursor-zoom-out rounded-lg bg-white object-contain shadow-2xl"
          />
          <button
            type="button"
            aria-label="关闭"
            onClick={() => setLightbox(null)}
            className="absolute right-6 top-6 rounded-full bg-white/90 px-3 py-1 text-sm font-medium text-navy-700 hover:bg-white"
          >
            关闭 ✕
          </button>
        </div>
      )}
    </PageShell>
  );
}
