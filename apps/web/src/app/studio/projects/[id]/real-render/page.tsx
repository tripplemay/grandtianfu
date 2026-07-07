'use client';

import React, { use, useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
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
import { MdPhotoCamera } from 'react-icons/md';
import {
  API_BASE,
  deleteRender,
  getAiStatus,
  listBaselinePhotos,
  listRenders,
  patchBaselinePhoto,
  pollJob,
  startRenderReal,
  suggestView,
  viewHints,
  type AiStatus,
  type BaselinePhoto,
  type RenderRecord,
} from 'lib/studioApi';
import { useConfirm } from 'components/studio/ui/ConfirmDialog';

// 第7步: 空房实拍照 (真实结构锚点) + 轴测参考 (家具方案) -> gpt-image-2 多图 img2img
// -> 实拍效果图。照片在户型基线页上传/标注 (绑定户型版本), 此页按方案生成并归档。

const POLL_MS = 3000;
const TIMEOUT_MS = 6 * 60 * 1000;

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

const VIEWS = ['v0', 'v1', 'v2', 'v3'] as const;

// 生成当口的视角选择器 (问题1): 显示该房 4 张旋转轴测缩略图, gpt-5.5 自动预标「推荐」,
// 点选即把照片 direction 落盘 (生成链路读它对齐落位)。仅在照片已标注房间时出现。
function RenderViewPicker({
  projectId,
  schemeId,
  photo,
  onPicked,
}: {
  projectId: string;
  schemeId: string;
  photo: BaselinePhoto;
  onPicked: (direction: string | null) => void;
}) {
  const [suggested, setSuggested] = useState<string | null>(null);
  const [hints, setHints] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const roomId = photo.room_id ?? '';
  const value = photo.direction ?? null;

  useEffect(() => {
    let alive = true;
    setSuggested(null);
    if (!roomId) return;
    void suggestView(projectId, schemeId, photo.id)
      .then((r) => {
        if (alive) setSuggested(r.suggested);
      })
      .catch(() => {
        if (alive) setSuggested(null);
      });
    return () => {
      alive = false;
    };
  }, [projectId, schemeId, photo.id, roomId]);

  // 各视角主窗方位 (窗在左/右), 让用户按窗户方位对上照片, 避免选错。
  useEffect(() => {
    let alive = true;
    setHints({});
    if (!roomId) return;
    void viewHints(projectId, schemeId, roomId)
      .then((r) => {
        if (alive) setHints(r.hints || {});
      })
      .catch(() => {
        if (alive) setHints({});
      });
    return () => {
      alive = false;
    };
  }, [projectId, schemeId, roomId]);

  const windowLabel = (v: string): string => {
    const s = hints[v];
    if (s === '左') return '窗在左';
    if (s === '右') return '窗在右';
    if (s === '正对') return '窗正对';
    if (s === '无窗') return '无窗';
    return '';
  };

  if (!roomId) return null;

  const url = (v: string) =>
    `${API_BASE}/projects/${encodeURIComponent(
      projectId,
    )}/schemes/${encodeURIComponent(
      schemeId,
    )}/axon-view?room_id=${encodeURIComponent(roomId)}&view=${v}`;

  const pick = async (v: string) => {
    if (saving) return;
    setSaving(true);
    const next = value === v ? null : v;
    try {
      await patchBaselinePhoto(projectId, 'v1', photo.id, { direction: next });
      onPicked(next);
    } finally {
      setSaving(false);
    }
  };

  return (
    <StudioCard>
      <p className="mb-1 text-sm font-bold text-navy-700 dark:text-white">
        拍摄视角(对齐家具落位)
      </p>
      <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
        选与你照片<b>窗户方位</b>一致的那张 ——
        轴测会转到同角度,家具按对应墙面落位。
        {value == null && (
          <span className="text-amber-600 dark:text-amber-400">
            {' '}
            未选视角,家具落位可能不准。
          </span>
        )}
      </p>
      <div className="flex flex-wrap gap-3">
        {VIEWS.map((v, i) => (
          <button
            key={v}
            type="button"
            disabled={saving}
            onClick={() => void pick(v)}
            className={`relative overflow-hidden rounded-xl border-2 transition ${
              value === v
                ? 'border-brand-500'
                : 'border-transparent hover:border-gray-300'
            }`}
            title={`视角 #${i + 1}`}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={url(v)}
              alt={`视角 ${i + 1}`}
              loading="lazy"
              className="h-24 w-32 bg-gray-50 object-contain dark:bg-navy-900"
            />
            {windowLabel(v) && (
              <span className="block bg-gray-100 py-0.5 text-center text-[11px] font-medium text-navy-700 dark:bg-navy-800 dark:text-gray-200">
                {windowLabel(v)}
              </span>
            )}
            {value == null && suggested === v && (
              <span className="absolute left-1 top-1 rounded bg-brand-500 px-1.5 py-0.5 text-[10px] font-medium text-white">
                推荐
              </span>
            )}
            {value === v && (
              <span className="absolute right-1 top-1 rounded bg-brand-500 px-1.5 py-0.5 text-[10px] font-medium text-white">
                ✓
              </span>
            )}
          </button>
        ))}
      </div>
    </StudioCard>
  );
}

export default function RealRenderPage({
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
        title="实拍效果图"
        description="请选择当前要生成实拍效果图的软装方案。"
      >
        <SchemeRequiredState projectId={id} />
      </PageShell>
    );
  }

  return <RealRenderWorkspace id={id} schemeId={schemeId} />;
}

function RealRenderWorkspace({
  id,
  schemeId,
}: {
  id: string;
  schemeId: string;
}) {
  const { showToast } = useToastContext();
  const confirm = useConfirm();
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const {
    currentScheme,
    currentBaseline,
    isHistorical,
    loading: ctxLoading,
  } = useProjectWorkflow();

  // 只读/越权门 (与 render 页同款): 历史版本、未知/归档方案、context 加载中一律禁止生成。
  const schemeLocked =
    isHistorical ||
    (!ctxLoading && !currentScheme) ||
    currentScheme?.status === 'archived';
  const baselineId =
    currentScheme?.baseline_version_id ?? currentBaseline?.id ?? 'v1';

  const [status, setStatus] = useState<AiStatus | null>(null);
  const [photos, setPhotos] = useState<BaselinePhoto[]>([]);
  const [selectedPhoto, setSelectedPhoto] = useState<string | null>(null);
  const [renders, setRenders] = useState<RenderRecord[]>([]);
  const [latest, setLatest] = useState<RenderRecord | null>(null);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const cancelRef = useRef(false);

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
  const activeScope = useRef(`${id}|${schemeId}`);
  activeScope.current = `${id}|${schemeId}`;
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const reload = useCallback(async () => {
    const scope = `${id}|${schemeId}`;
    try {
      const [st, photoList, renderList] = await Promise.all([
        getAiStatus(),
        listBaselinePhotos(id, baselineId),
        listRenders(id, schemeId),
      ]);
      if (!mounted.current || activeScope.current !== scope) return;
      const realRenders = renderList.filter((r) => r.mode === 'real-photo');
      setStatus(st);
      setPhotos(photoList);
      // 默认选「已标注房间」的最新照片 (P1-5): 未标注走整宅参考是质量最差路径。
      const preferred =
        photoList.find((p) => p.room_id)?.id ?? photoList[0]?.id ?? null;
      setSelectedPhoto((prev) =>
        prev && photoList.some((p) => p.id === prev) ? prev : preferred,
      );
      setRenders(realRenders);
      setLatest(realRenders[0] ?? null);
      setError(null);
      setLoadState('ready');
    } catch (e) {
      if (!mounted.current || activeScope.current !== scope) return;
      setError(e instanceof Error ? e.message : String(e));
      setLoadState('error');
    }
  }, [id, schemeId, baselineId]);

  useEffect(() => {
    setLoadState('loading');
    setPhotos([]);
    setRenders([]);
    setLatest(null);
    void reload();
  }, [reload]);

  // 删除一张实拍效果图 (记录 + 自有产物文件; 共享空房照保留)。删后 reload 重算 latest。
  const onDelete = useCallback(
    async (r: RenderRecord) => {
      const ok = await confirm({
        title: '删除实拍效果图',
        message:
          '此操作不可恢复,该效果图的图片文件会被删除(空房照片不受影响)。',
        confirmText: '删除',
        cancelText: '取消',
        danger: true,
      });
      if (!ok) return;
      setDeletingId(r.id);
      try {
        await deleteRender(id, schemeId, r.id);
        showToast('效果图已删除', 'success');
        await reload();
      } catch (e) {
        showToast(
          `删除失败:${e instanceof Error ? e.message : String(e)}`,
          'error',
        );
      } finally {
        setDeletingId(null);
      }
    },
    [id, schemeId, confirm, showToast, reload],
  );

  const onGenerate = useCallback(async () => {
    if (generating || schemeLocked || ctxLoading || !selectedPhoto) return;
    const scope = `${id}|${schemeId}`;
    cancelRef.current = false;
    setGenerating(true);
    try {
      const { job_id } = await startRenderReal(id, schemeId, selectedPhoto);
      const started = Date.now();
      // eslint-disable-next-line no-constant-condition
      while (true) {
        await sleep(POLL_MS);
        if (!mounted.current || activeScope.current !== scope) return;
        if (cancelRef.current) {
          showToast('已停止等待,生成完成后可在历史中查看', 'info');
          break;
        }
        const job = await pollJob<RenderRecord>(job_id);
        if (activeScope.current !== scope) return;
        if (job.status === 'done' && job.result) {
          setLatest(job.result);
          showToast('实拍效果图已生成', 'success');
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
  }, [
    id,
    schemeId,
    generating,
    schemeLocked,
    ctxLoading,
    selectedPhoto,
    showToast,
    reload,
  ]);

  const aiOff = status != null && !status.enabled;
  const budget = status?.budget;

  const actions =
    status?.enabled && photos.length > 0 ? (
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
          disabled={generating || schemeLocked || ctxLoading || !selectedPhoto}
          title={
            schemeLocked
              ? '历史户型版本或已锁定方案不能生成新效果图'
              : !selectedPhoto
              ? '请先选择一张空房照片'
              : '空房照 + 轴测参考 → 实拍效果图(约 1-3 分钟,最长 6 分钟)'
          }
        >
          {generating ? `生成中…(已 ${elapsed}s)` : '✨ 生成实拍效果图'}
        </SaveButton>
      </div>
    ) : undefined;

  return (
    <PageShell
      title="实拍效果图"
      description={`户型 ${id} · 方案 ${schemeId} · 空房实拍照 + 轴测方案 → 照片级实拍效果图(保真实结构)。`}
      actions={actions}
      state={loadState === 'loading' ? <LoadingState rows={2} /> : undefined}
    >
      {error && <BackendErrorBanner message={error} />}
      {schemeLocked && (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-900 dark:text-amber-200">
          {isHistorical
            ? '当前方案属历史户型版本,只能查看已有效果图,不能生成新成果。'
            : '当前方案已锁定或不属当前户型版本,只能查看已有效果图。'}
        </div>
      )}

      {aiOff ? (
        <EmptyState
          icon={<MdPhotoCamera className="h-6 w-6" />}
          title="实拍效果图 · 未配置"
          description="当前运行环境未配置图像模型凭据(OPENAI_API_KEY / OPENAI_BASE_URL),AI 生成暂不可用。"
        />
      ) : loadState === 'ready' && photos.length === 0 ? (
        <EmptyState
          icon={<MdPhotoCamera className="h-6 w-6" />}
          title="还没有空房照片"
          description="先在户型基线页上传空房实拍照并标注房间,再回到这里生成实拍效果图。"
          action={
            <LinkButton
              href={`/studio/projects/${encodeURIComponent(id)}/baseline`}
              variant="primary"
            >
              去上传空房照片 →
            </LinkButton>
          }
        />
      ) : (
        <div className="flex flex-col gap-6">
          {/* 未标注房间提示 (P1-5): 整宅参考是质量最差路径, 明示用户去标注 */}
          {photos.length > 0 &&
            selectedPhoto &&
            !photos.find((p) => p.id === selectedPhoto)?.room_id && (
              <NoticeBanner tone="warn">
                所选照片未标注房间, 将使用整宅轴测做参考, 出图匹配度较差 ——
                建议先到户型基线页为照片标注房间。
              </NoticeBanner>
            )}
          {/* 照片选择 */}
          {photos.length > 0 && (
            <StudioCard>
              <p className="mb-3 text-sm font-bold text-navy-700 dark:text-white">
                选择空房照片({photos.length})
              </p>
              <div className="flex flex-wrap gap-3">
                {photos.map((photo) => {
                  const selected = selectedPhoto === photo.id;
                  return (
                    <button
                      key={photo.id}
                      type="button"
                      onClick={() => setSelectedPhoto(photo.id)}
                      title={photo.note || photo.room_id || '空房照片'}
                      className={`overflow-hidden rounded-xl border-2 transition ${
                        selected
                          ? 'border-brand-500'
                          : 'border-transparent hover:border-gray-300'
                      }`}
                    >
                      <div className="relative">
                        <RenderImage
                          src={photo.thumb_url ?? photo.url}
                          alt={photo.note || '空房照片'}
                          className="h-24 w-32"
                          imgClassName="h-24 w-32 object-cover"
                          fallbackLabel="照片加载失败"
                        />
                        <span
                          className={`absolute left-1 top-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                            photo.room_id
                              ? 'bg-green-100 text-green-700'
                              : 'bg-amber-100 text-amber-700'
                          }`}
                        >
                          {photo.room_id || '未标注房间'}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </StudioCard>
          )}

          {/* 拍摄视角对齐 (问题1): 选好照片后在此选视角, 生成即用它对齐落位 */}
          {(() => {
            const sel = photos.find((p) => p.id === selectedPhoto);
            return sel?.room_id ? (
              <RenderViewPicker
                projectId={id}
                schemeId={schemeId}
                photo={sel}
                onPicked={(dir) =>
                  setPhotos((prev) =>
                    prev.map((p) =>
                      p.id === sel.id ? { ...p, direction: dir } : p,
                    ),
                  )
                }
              />
            ) : null;
          })()}

          {/* 最新结果 */}
          {latest ? (
            <StudioCard extra="flex flex-col">
              <div className="mb-3 w-full overflow-hidden rounded-xl bg-gray-50 dark:bg-navy-900">
                <RenderImage
                  src={latest.preview_url ?? latest.url}
                  alt={`${id} ${schemeId} 实拍效果图`}
                  className="h-[420px]"
                  imgClassName="h-[420px] w-full object-contain"
                  fallbackLabel="效果图加载失败"
                />
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium text-gray-600 dark:text-gray-300">
                  最新实拍效果图 · {latest.model}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void onDelete(latest)}
                    disabled={deletingId === latest.id}
                    className="rounded-lg border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-red-500/30 dark:hover:bg-red-900"
                  >
                    {deletingId === latest.id ? '删除中…' : '删除'}
                  </button>
                  <LinkButton
                    href={latest.url}
                    download={`${id}-${schemeId}-real.png`}
                    variant="primary"
                  >
                    下载 PNG
                  </LinkButton>
                </div>
              </div>
            </StudioCard>
          ) : (
            loadState === 'ready' && (
              <EmptyState
                icon={<MdPhotoCamera className="h-6 w-6" />}
                title="还没有实拍效果图"
                description="选择一张空房照片,点击右上角「生成实拍效果图」(约 1-3 分钟)。"
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
                  <StudioCard key={r.id} extra="flex flex-col !p-3">
                    <button
                      type="button"
                      onClick={() => setLatest(r)}
                      className="mb-2 w-full overflow-hidden rounded-lg bg-gray-50 dark:bg-navy-900"
                      title="设为大图查看"
                    >
                      <RenderImage
                        src={r.thumb_url ?? r.url}
                        alt={`${id} ${schemeId} 实拍效果图 ${r.id}`}
                        className="h-32"
                        imgClassName="h-32 w-full object-cover"
                        fallbackLabel="加载失败"
                      />
                    </button>
                    <div className="flex items-center justify-center gap-3">
                      <a
                        href={r.url}
                        download={`${id}-${schemeId}-${r.id}.png`}
                        className="text-xs font-medium text-brand-500 hover:text-brand-600"
                      >
                        下载
                      </a>
                      <button
                        type="button"
                        onClick={() => void onDelete(r)}
                        disabled={deletingId === r.id}
                        className="text-xs font-medium text-red-600 hover:text-red-700 disabled:opacity-50"
                      >
                        {deletingId === r.id ? '删除中…' : '删除'}
                      </button>
                    </div>
                  </StudioCard>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </PageShell>
  );
}
