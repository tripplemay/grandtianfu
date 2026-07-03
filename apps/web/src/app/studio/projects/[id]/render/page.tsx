'use client';

import React, { use, useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Card from 'components/card';
import PageShell from 'components/studio/ui/PageShell';
import EmptyState from 'components/studio/ui/EmptyState';
import LoadingState from 'components/studio/ui/LoadingState';
import RenderImage from 'components/studio/ui/RenderImage';
import { BackendErrorBanner, NoticeBanner } from 'components/studio/ui/status';
import { Button, LinkButton, SaveButton } from 'components/studio/ui/buttons';
import { StudioCard } from 'components/studio/ui/primitives';
import { useToastContext } from 'components/studio/ui/ToastHost';
import SchemeRequiredState from 'components/studio/workflow/SchemeRequiredState';
import { useProjectWorkflow } from 'components/studio/workflow/ProjectWorkflowContext';
import { MdAutoAwesome } from 'react-icons/md';
import {
  getAiStatus,
  fetchRenderScene,
  listRenders,
  setPreferredScheme,
  startRenderAi,
  pollJob,
  type AiStatus,
  type RenderRecord,
  type RenderScene,
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
  const schemeId = search.get('scheme');

  if (!schemeId) {
    return (
      <PageShell
        title="AI 效果图"
        description="请选择当前要生成效果图的软装方案。"
      >
        <SchemeRequiredState projectId={id} />
      </PageShell>
    );
  }

  return <RenderWorkspace id={id} schemeId={schemeId} />;
}

function RenderWorkspace({ id, schemeId }: { id: string; schemeId: string }) {
  const { showToast } = useToastContext();
  const {
    currentScheme,
    isHistorical,
    loading: ctxLoading,
  } = useProjectWorkflow();

  // 只读 / 越权门 (P0-1): 历史户型版本、或该方案不属当前已确认版本 (未命中 availableSchemes)、
  // 或方案已归档 → 禁止发起 AI 生成 (§14.17 历史版本禁止生成新成果)。context 加载中不预判「未命中」。
  const schemeLocked =
    isHistorical ||
    (!ctxLoading && !currentScheme) ||
    currentScheme?.status === 'archived';

  const [status, setStatus] = useState<AiStatus | null>(null);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [error, setError] = useState<string | null>(null);
  const [renders, setRenders] = useState<RenderRecord[]>([]);
  const [latest, setLatest] = useState<RenderRecord | null>(null);
  const [scene, setScene] = useState<RenderScene | null>(null);
  const [generating, setGenerating] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const cancelRef = useRef(false);

  // 生成期间每秒更新已用时,给等待以进度反馈(出图 90-360s)。
  useEffect(() => {
    if (!generating) return;
    const t0 = Date.now();
    setElapsed(0);
    const iv = setInterval(
      () => setElapsed(Math.floor((Date.now() - t0) / 1000)),
      1000,
    );
    return () => clearInterval(iv);
  }, [generating]);

  const mounted = useRef(true);
  const reloadRequest = useRef(0);
  const activeScope = useRef(`${id}|${schemeId}`);
  activeScope.current = `${id}|${schemeId}`;
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const reload = useCallback(async () => {
    const request = ++reloadRequest.current;
    const scope = `${id}|${schemeId}`;
    try {
      const [st, list, sc] = await Promise.all([
        getAiStatus(),
        listRenders(id, schemeId),
        fetchRenderScene(id, schemeId),
      ]);
      if (
        !mounted.current ||
        request !== reloadRequest.current ||
        activeScope.current !== scope
      )
        return;
      // mode 受控词表 (P1-2): 正向过滤本页归属的 axon-photoreal, 新增 mode 不会静默混入。
      const aiOnly = list.filter((r) => r.mode === 'axon-photoreal');
      setStatus(st);
      setRenders(aiOnly);
      setLatest(aiOnly[0] ?? null);
      setScene(sc);
      setError(null);
      setLoadState('ready');
    } catch (e) {
      if (
        !mounted.current ||
        request !== reloadRequest.current ||
        activeScope.current !== scope
      )
        return;
      setError(e instanceof Error ? e.message : String(e));
      setLoadState('error');
    }
  }, [id, schemeId]);

  useEffect(() => {
    setLoadState('loading');
    setError(null);
    setRenders([]);
    setLatest(null);
    setScene(null);
    void reload();
    return () => {
      reloadRequest.current += 1;
    };
  }, [reload]);

  const onGenerate = useCallback(async () => {
    // context 加载中一并禁止 (对齐 editor 的 readOnly=loading||!editable): 避免首次加载
    // 时序缝隙里对历史/归档方案越权发起生成。
    if (generating || schemeLocked || ctxLoading) return;
    const scope = `${id}|${schemeId}`;
    cancelRef.current = false;
    setGenerating(true);
    try {
      const { job_id } = await startRenderAi(id, undefined, schemeId);
      const started = Date.now();
      // 轮询直至 done/error/取消/超时。
      // eslint-disable-next-line no-constant-condition
      while (true) {
        await sleep(POLL_MS);
        if (!mounted.current || activeScope.current !== scope) return;
        // 用户取消: 停止前端等待(后端任务继续, 完成后仍会进历史)。
        if (cancelRef.current) {
          showToast('已停止等待,生成完成后可在历史中查看', 'info');
          break;
        }
        const job = await pollJob<RenderRecord>(job_id);
        if (activeScope.current !== scope) return;
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
  }, [id, schemeId, generating, schemeLocked, ctxLoading, showToast, reload]);

  const budget = status?.budget;
  const aiOff = status != null && !status.enabled;
  const sceneErrors = scene?.validation?.errors ?? [];
  const sceneWarnings = scene?.validation?.warnings ?? [];
  const sceneAdjustments = scene?.validation?.adjustments ?? [];
  const sceneBlocked = scene != null && !scene.validation.ok;

  const actions = status?.enabled ? (
    <div className="flex items-center gap-3">
      {budget && (
        <span className="text-xs text-gray-500 dark:text-gray-400">
          今日 {budget.daily_count}/{budget.daily_cap} · {status.model}
        </span>
      )}
      {generating && (
        <Button
          variant="secondary"
          onClick={() => {
            cancelRef.current = true;
          }}
        >
          停止等待
        </Button>
      )}
      <SaveButton
        onClick={onGenerate}
        disabled={generating || sceneBlocked || schemeLocked || ctxLoading}
        title={
          schemeLocked
            ? '历史户型版本或已锁定方案不能生成新效果图'
            : sceneBlocked
            ? '场景校验未通过，已阻断 AI 出图'
            : '基于当前轴测方案生成照片级效果图(约 1-3 分钟，最长 6 分钟)'
        }
      >
        {generating ? `生成中…(已 ${elapsed}s)` : '✨ 生成效果图'}
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
      {schemeLocked && (
        <NoticeBanner>
          {isHistorical
            ? '当前方案属历史户型版本，只能查看已有效果图，不能生成新成果。请先迁移到当前户型版本。'
            : '当前方案已锁定或不属当前户型版本，只能查看已有效果图，不能生成新成果。'}
        </NoticeBanner>
      )}
      {sceneBlocked && (
        <div className="mb-4">
          <BackendErrorBanner
            title="场景校验未通过，已阻断 AI 出图。"
            message={`场景校验未通过，已阻断 AI 出图：${sceneErrors
              .map((issue) => issue.message)
              .join('；')}`}
          />
          {/* 闭环:被拦截时给一键回家具编辑器的入口,避免变成死路(§q3 领域优势) */}
          {!schemeLocked && (
            <LinkButton
              href={`/studio/projects/${encodeURIComponent(
                id,
              )}/editor?scheme=${encodeURIComponent(schemeId)}&tab=furniture`}
              className="mt-2"
            >
              去调整家具 →
            </LinkButton>
          )}
        </div>
      )}
      {!sceneBlocked && sceneAdjustments.length > 0 && (
        <NoticeBanner>
          轴侧转换已自动修正 {sceneAdjustments.length} 项家具参数（墙厚内缩 /
          高度归一化），避免家具体块与墙体相交或高于墙体。
          {sceneWarnings.length > 0
            ? ` 当前还有 ${sceneWarnings.length} 项非阻断提示。`
            : ''}
        </NoticeBanner>
      )}

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
            <StudioCard extra="flex flex-col">
              <div className="mb-3 w-full overflow-hidden rounded-xl bg-gray-50 dark:bg-navy-900">
                <RenderImage
                  src={latest.url}
                  alt={`${id} ${schemeId} AI 效果图`}
                  className="h-[420px]"
                  imgClassName="h-[420px] w-full object-contain"
                  fallbackLabel="效果图加载失败"
                />
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium text-gray-600 dark:text-gray-300">
                  最新效果图 · {latest.model}
                </p>
                {/* 出图后的收尾决策留在手边(§7 主线末段):设首选 / 返回方案中心 / 下载 */}
                <div className="flex items-center gap-2">
                  {!schemeLocked && (
                    <Button
                      variant="soft-amber"
                      onClick={async () => {
                        try {
                          await setPreferredScheme(id, schemeId);
                          showToast('已设为首选方案', 'success');
                        } catch (e) {
                          showToast(
                            `设置失败:${
                              e instanceof Error ? e.message : String(e)
                            }`,
                            'error',
                          );
                        }
                      }}
                    >
                      设为首选
                    </Button>
                  )}
                  <LinkButton
                    href={`/studio/projects/${encodeURIComponent(id)}/scheme`}
                    variant="secondary"
                  >
                    返回方案中心
                  </LinkButton>
                  <LinkButton
                    href={latest.url}
                    download={`${id}-${schemeId}-effect.png`}
                    className="w-fit"
                  >
                    下载 PNG
                  </LinkButton>
                </div>
              </div>
            </StudioCard>
          ) : (
            loadState === 'ready' && (
              <EmptyState
                icon={<MdAutoAwesome className="h-6 w-6" />}
                title="还没有效果图"
                description="点击右上角「生成效果图」,基于当前轴测方案生成照片级写实图(约 1-3 分钟)。"
                action={
                  <SaveButton
                    onClick={onGenerate}
                    disabled={
                      generating || sceneBlocked || schemeLocked || ctxLoading
                    }
                    title={
                      schemeLocked
                        ? '历史户型版本或已锁定方案不能生成新效果图'
                        : sceneBlocked
                        ? '场景校验未通过，已阻断 AI 出图'
                        : undefined
                    }
                  >
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
                        src={r.thumb_url ?? r.url}
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
