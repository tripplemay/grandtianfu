'use client';

import React, { use, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import Card from 'components/card';
import PageShell from 'components/studio/ui/PageShell';
import EmptyState from 'components/studio/ui/EmptyState';
import LoadingState from 'components/studio/ui/LoadingState';
import RenderImage from 'components/studio/ui/RenderImage';
import { BackendErrorBanner } from 'components/studio/ui/status';
import {
  API_BASE,
  listRenders,
  listSchemes,
  setPreferredScheme,
  type FurnitureSchemeSummary,
  type RenderRecord,
} from 'lib/studioApi';
import { MdCompare, MdImage, MdStar } from 'react-icons/md';
import { useToastContext } from 'components/studio/ui/ToastHost';

type CompareMode = 'plan2d' | 'photo' | 'ai';

const VIEW_OPTIONS: Array<{ value: CompareMode; label: string }> = [
  { value: 'plan2d', label: '家具平面图' },
  { value: 'photo', label: '轴测方案图' },
  { value: 'ai', label: 'AI 效果图' },
];

function renderSrc(projectId: string, schemeId: string, mode: 'plan2d' | 'photo') {
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
  const { showToast } = useToastContext();

  const reload = useCallback(async () => {
    try {
      setLoadState('loading');
      const all = await listSchemes(id);
      const selected = selectedIds
        .map((sid) => all.find((scheme) => scheme.id === sid))
        .filter(Boolean) as FurnitureSchemeSummary[];
      const renderEntries = await Promise.all(
        selected.map(async (scheme) => [
          scheme.id,
          await listRenders(id, scheme.id),
        ] as const),
      );
      setSchemes(selected);
      setRenders(Object.fromEntries(renderEntries));
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
      try {
        await setPreferredScheme(id, scheme.id);
        showToast('首选方案已更新', 'success');
        await reload();
      } catch (e) {
        showToast(`设置失败:${e instanceof Error ? e.message : String(e)}`, 'error');
      }
    },
    [id, showToast, reload],
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
            <Link
              href={`/studio/projects/${encodeURIComponent(id)}/scheme`}
              className="rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
            >
              返回方案中心
            </Link>
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
          <Card extra="w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10">
            <div className="flex flex-wrap gap-2">
              {VIEW_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setMode(option.value)}
                  className={`rounded-lg px-3 py-2 text-sm font-medium ${
                    mode === option.value
                      ? 'bg-brand-500 text-white'
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
          </Card>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
            {schemes.map((scheme) => {
              const latestRender = renders[scheme.id]?.[0];
              return (
                <Card
                  key={scheme.id}
                  extra="flex min-h-[520px] flex-col w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10"
                >
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-lg font-bold text-navy-700 dark:text-white">
                          {scheme.name}
                        </h2>
                        {scheme.preferred && (
                          <span className="inline-flex items-center gap-1 rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                            <MdStar className="h-3 w-3" />
                            首选
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-xs text-gray-500">
                        {scheme.status} · 家具 {scheme.items} · 效果图 {scheme.renders}
                      </p>
                    </div>
                    {!scheme.preferred && (
                      <button
                        type="button"
                        onClick={() => void onPreferred(scheme)}
                        className="rounded-lg bg-amber-50 px-3 py-2 text-sm font-medium text-amber-700 hover:bg-amber-100"
                      >
                        设为首选
                      </button>
                    )}
                  </div>

                  <div className="flex flex-1 items-center justify-center overflow-hidden rounded-xl bg-gray-50 dark:bg-navy-900">
                    {mode === 'ai' ? (
                      latestRender ? (
                        <RenderImage
                          src={latestRender.url}
                          alt={`${scheme.name} AI 效果图`}
                          className="h-[360px] w-full"
                          imgClassName="h-[360px] w-full object-contain"
                          fallbackLabel="效果图加载失败"
                        />
                      ) : (
                        <EmptyState
                          icon={<MdImage className="h-6 w-6" />}
                          title="缺少 AI 效果图"
                          description="进入该方案生成效果图后可在此比较。"
                          action={
                            <Link
                              href={`/studio/projects/${encodeURIComponent(
                                id,
                              )}/render?scheme=${encodeURIComponent(scheme.id)}`}
                              className="rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
                            >
                              去生成
                            </Link>
                          }
                        />
                      )
                    ) : (
                      <RenderImage
                        src={renderSrc(id, scheme.id, mode)}
                        alt={`${scheme.name} ${mode}`}
                        className="h-[360px] w-full"
                        imgClassName="h-[360px] w-full object-contain"
                        fallbackLabel="方案图加载失败"
                      />
                    )}
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    <Link
                      href={`/studio/projects/${encodeURIComponent(
                        id,
                      )}/editor?scheme=${encodeURIComponent(scheme.id)}`}
                      className="rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
                    >
                      打开方案
                    </Link>
                    <Link
                      href={`/studio/projects/${encodeURIComponent(id)}/scheme`}
                      className="rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
                    >
                      退出对比
                    </Link>
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      )}
    </PageShell>
  );
}
