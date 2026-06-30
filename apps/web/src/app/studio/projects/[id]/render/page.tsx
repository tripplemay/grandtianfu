'use client';

import React, { use, useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Card from 'components/card';
import PageShell from 'components/studio/ui/PageShell';
import EmptyState from 'components/studio/ui/EmptyState';
import LoadingState from 'components/studio/ui/LoadingState';
import RenderImage from 'components/studio/ui/RenderImage';
import { BackendErrorBanner } from 'components/studio/ui/status';
import { SaveButton } from 'components/studio/ui/buttons';
import { useToastContext } from 'components/studio/ui/ToastHost';
import { MdAutoAwesome } from 'react-icons/md';
import {
  getAiStatus,
  listRenders,
  startRenderAi,
  pollJob,
  type AiStatus,
  type RenderRecord,
} from 'lib/studioApi';

// AI 效果图 (#6 / 第5步): 轴测 photo 底图 -> gpt-image-2 img2img -> 照片级轴测效果图。
// 后端异步: POST /render-ai -> job_id, 轮询 /api/ai/jobs/{id}; 完成后 result.url 即产物 (自托管)。
// Next 15: client 组件 params 为 Promise, 用 use 解包。SSG: [id] 由上层 layout 的 generateStaticParams 枚举。

const POLL_MS = 3000;
const TIMEOUT_MS = 6 * 60 * 1000;

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

export default function RenderPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const search = useSearchParams();
  const schemeId = search.get('scheme') || 'default';
  const { showToast } = useToastContext();

  const [status, setStatus] = useState<AiStatus | null>(null);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [error, setError] = useState<string | null>(null);
  const [renders, setRenders] = useState<RenderRecord[]>([]);
  const [latest, setLatest] = useState<RenderRecord | null>(null);
  const [generating, setGenerating] = useState(false);

  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const reload = useCallback(async () => {
    try {
      const [st, list] = await Promise.all([
        getAiStatus(),
        listRenders(id, schemeId),
      ]);
      if (!mounted.current) return;
      setStatus(st);
      setRenders(list);
      setLatest(list[0] ?? null);
      setError(null);
      setLoadState('ready');
    } catch (e) {
      if (!mounted.current) return;
      setError(e instanceof Error ? e.message : String(e));
      setLoadState('error');
    }
  }, [id, schemeId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const onGenerate = useCallback(async () => {
    if (generating) return;
    setGenerating(true);
    try {
      const { job_id } = await startRenderAi(id, undefined, schemeId);
      const started = Date.now();
      // 轮询直至 done/error/超时。
      // eslint-disable-next-line no-constant-condition
      while (true) {
        await sleep(POLL_MS);
        if (!mounted.current) return;
        const job = await pollJob<RenderRecord>(job_id);
        if (job.status === 'done' && job.result) {
          setLatest(job.result);
          showToast('效果图已生成', 'success');
          await reload();
          break;
        }
        if (job.status === 'error') {
          throw new Error(job.error || '生成失败');
        }
        if (Date.now() - started > TIMEOUT_MS) {
          throw new Error('生成超时 (>6 分钟),请稍后在历史中查看或重试');
        }
      }
    } catch (e) {
      if (mounted.current) {
        showToast(
          `生成失败:${e instanceof Error ? e.message : String(e)}`,
          'error',
        );
      }
    } finally {
      if (mounted.current) setGenerating(false);
    }
  }, [id, schemeId, generating, showToast, reload]);

  const budget = status?.budget;
  const aiOff = status != null && !status.enabled;

  const actions =
    status?.enabled ? (
      <div className="flex items-center gap-3">
        {budget && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            今日 {budget.daily_count}/{budget.daily_cap} · {status.model}
          </span>
        )}
        <SaveButton
          onClick={onGenerate}
          disabled={generating}
          title="基于当前轴测方案生成照片级效果图"
        >
          {generating ? '生成中…(约 1-3 分钟)' : '✨ 生成效果图'}
        </SaveButton>
      </div>
    ) : undefined;

  return (
    <PageShell
      title="效果图"
      description={`户型 ${id} · 方案 ${schemeId} · 轴测方案 → gpt-image-2 照片级写实(保结构、保布局)。`}
      actions={actions}
      state={loadState === 'loading' ? <LoadingState rows={2} /> : undefined}
    >
      {error && <BackendErrorBanner message={error} />}

      {aiOff ? (
        <EmptyState
          icon={<MdAutoAwesome className="h-6 w-6" />}
          title="AI 效果图 · 未配置"
          description="当前运行环境未配置图像模型凭据(OPENAI_API_KEY / OPENAI_BASE_URL),AI 生成暂不可用。配置后此处即可一键出图。"
        />
      ) : (
        <div className="flex flex-col gap-6">
          {/* 最新结果 (大图) */}
          {latest ? (
            <Card extra="flex flex-col w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10">
              <div className="mb-3 w-full overflow-hidden rounded-xl bg-gray-50 dark:bg-navy-900">
                <RenderImage
                  src={latest.url}
                  alt={`${id} ${schemeId} AI 效果图`}
                  className="h-[420px]"
                  imgClassName="h-[420px] w-full object-contain"
                  fallbackLabel="效果图加载失败"
                />
              </div>
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-gray-600 dark:text-gray-300">
                  最新效果图 · {latest.model}
                </p>
                <a
                  href={latest.url}
                  download={`${id}-${schemeId}-effect.png`}
                  className="inline-flex w-fit items-center rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
                >
                  下载 PNG
                </a>
              </div>
            </Card>
          ) : (
            loadState === 'ready' && (
              <EmptyState
                icon={<MdAutoAwesome className="h-6 w-6" />}
                title="还没有效果图"
                description="点击右上角「生成效果图」,基于当前轴测方案生成照片级写实图(约 1-3 分钟)。"
                action={
                  <SaveButton onClick={onGenerate} disabled={generating}>
                    {generating ? '生成中…' : '✨ 生成效果图'}
                  </SaveButton>
                }
              />
            )
          )}

          {/* 历史 */}
          {renders.length > 1 && (
            <div>
              <p className="mb-3 text-sm font-bold text-navy-700 dark:text-white">
                历史({renders.length})
              </p>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                {renders.map((r) => (
                  <Card
                    key={r.id}
                    extra="flex flex-col w-full !p-3 border border-gray-200 !shadow-none dark:border-white/10"
                  >
                    <button
                      type="button"
                      onClick={() => setLatest(r)}
                      className="mb-2 w-full overflow-hidden rounded-lg bg-gray-50 dark:bg-navy-900"
                      title="设为大图查看"
                    >
                      <RenderImage
                        src={r.url}
                        alt={`${id} ${schemeId} 效果图 ${r.id}`}
                        className="h-32"
                        imgClassName="h-32 w-full object-cover"
                        fallbackLabel="加载失败"
                      />
                    </button>
                    <a
                      href={r.url}
                      download={`${id}-${schemeId}-${r.id}.png`}
                      className="text-center text-xs font-medium text-brand-500 hover:text-brand-600"
                    >
                      下载
                    </a>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </PageShell>
  );
}
