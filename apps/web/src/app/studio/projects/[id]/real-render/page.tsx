'use client';

import React, { use, useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import PageShell from 'components/studio/ui/PageShell';
import EmptyState from 'components/studio/ui/EmptyState';
import LoadingState from 'components/studio/ui/LoadingState';
import RenderImage from 'components/studio/ui/RenderImage';
import {
  BackendErrorBanner,
  NoticeBanner,
  Badge,
} from 'components/studio/ui/status';
import { Button, LinkButton, SaveButton } from 'components/studio/ui/buttons';
import { StudioCard } from 'components/studio/ui/primitives';
import { useToastContext } from 'components/studio/ui/ToastHost';
import SchemeRequiredState from 'components/studio/workflow/SchemeRequiredState';
import { useProjectWorkflow } from 'components/studio/workflow/ProjectWorkflowContext';
import { MdPhotoCamera, MdContentCopy, MdEditNote } from 'react-icons/md';
import { inputCls } from 'lib/floorplan/fieldStyles';
import {
  API_BASE,
  deleteRender,
  fetchBaselineGeometry,
  getAiStatus,
  LayoutGateError,
  listBaselinePhotos,
  listRenders,
  patchBaselinePhoto,
  pollJob,
  setRenderStatus,
  setRenderComment,
  startRenderReal,
  suggestView,
  viewHints,
  type AiStatus,
  type BaselinePhoto,
  type GeometryEditBackend,
  type LayoutLint,
  type RenderRecord,
} from 'lib/studioApi';
import { roomById } from 'lib/floorplan/geometry';
import { roomDisplayName } from 'lib/floorplan/merge';
import type { Geometry as FpGeometry } from 'lib/floorplan/types';
import { useConfirm } from 'components/studio/ui/ConfirmDialog';
import PerspectiveCalibrator from 'components/studio/real-render/PerspectiveCalibrator';
import {
  AutoCheckFailedBadge,
  AutoCheckFailedPanel,
  RenderQualityBadges,
  autoCheckFailed,
  retryBackendOf,
  shouldCollapseFailed,
} from 'components/studio/real-render/AutoCheckPanel';

// 第7步: 空房实拍照 (真实结构锚点) + 轴测参考 (家具方案) -> gpt-image-2 多图 img2img
// -> 实拍效果图。照片在户型基线页上传/标注 (绑定户型版本), 此页按方案生成并归档。

const POLL_MS = 3000;
const TIMEOUT_MS = 6 * 60 * 1000;

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// render-note-b1: 效果图唯一标识。显示短 id (前 8 位), 点击复制完整 id —— 供用户精确指代某张图。
function RenderIdChip({
  id,
  onCopy,
}: {
  id: string;
  onCopy: (id: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onCopy(id)}
      title={`点击复制完整 ID：${id}`}
      className="inline-flex items-center gap-1 rounded-md bg-gray-100 px-1.5 py-0.5 font-mono text-[11px] font-normal text-gray-500 transition-colors hover:bg-gray-200 hover:text-gray-700 dark:bg-white/10 dark:text-gray-400 dark:hover:bg-white/20 dark:hover:text-gray-200"
    >
      <MdContentCopy className="h-3 w-3" />
      {id.slice(0, 8)}
    </button>
  );
}

const VIEWS = ['v0', 'v1', 'v2', 'v3'] as const;

// B4 反馈闭环: 不满意原因 -> 对应修正入口。sub 为空表示留在本页 (换视角/重试)。
type FeedbackReason = {
  key: string;
  label: string;
  fixLabel: string;
  sub?: 'baseline' | 'scheme' | 'editor';
};
const FEEDBACK_REASONS: FeedbackReason[] = [
  {
    key: 'structure',
    label: '结构错',
    fixLabel: '去校对空房照 / 房间标注',
    sub: 'baseline',
  },
  {
    key: 'furniture',
    label: '家具位置错',
    fixLabel: '重选拍摄视角或去编辑家具',
    sub: 'editor',
  },
  {
    key: 'style',
    label: '风格不符',
    fixLabel: '去调整风格 / 设计 Brief',
    sub: 'scheme',
  },
  {
    key: 'material',
    label: '材质不符',
    fixLabel: '去补充墙面材质参考',
    sub: 'baseline',
  },
  { key: 'quality', label: '画质问题', fixLabel: '换个视角或重试生成' },
  { key: 'other', label: '其他', fixLabel: '按需调整照片 / 家具 / 风格后重试' },
];

// 生成当口的视角选择器 (问题1): 显示该房 4 张旋转轴测缩略图, gpt-5.5 自动预标「推荐」,
// 点选即把照片 direction 落盘 (生成链路读它对齐落位)。仅在照片已标注房间时出现。
function RenderViewPicker({
  projectId,
  schemeId,
  baselineId,
  photo,
  onPicked,
  onError,
}: {
  projectId: string;
  schemeId: string;
  // 照片按户型版本分目录存储 (baselines/<v>/photos.json); 写 direction 必须打到方案绑定
  // 的 baseline 版本, 而非硬编码 v1 (多版本项目会写错版本 -> 404 静默丢失视角)。
  baselineId: string;
  photo: BaselinePhoto;
  onPicked: (direction: string | null) => void;
  onError: (msg: string) => void;
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
      await patchBaselinePhoto(projectId, baselineId, photo.id, {
        direction: next,
      });
      onPicked(next);
    } catch (e) {
      // 此前无 catch: PATCH 失败 (如写错版本 404) 会静默吞掉, 视角选择丢失。
      onError(e instanceof Error ? e.message : '视角保存失败,请重试');
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
    reload: reloadWorkflow,
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
  // F003: 户型几何 (含 rooms[].label.zh) -> 角标显中文房名而非裸 room_id; 非关键, 拉取失败不阻断。
  const [geometry, setGeometry] = useState<FpGeometry | null>(null);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  // B2 低准确度模式: 所选照片未标注房间/视角时, 需用户显式勾选才允许(降级)生成。
  const [lowAccuracyConfirmed, setLowAccuracyConfirmed] = useState(false);
  const [settingVerdict, setSettingVerdict] = useState<string | null>(null);
  // P4 透出: 验收未过的结果默认折叠, 用户点"仍要查看"后记住已展开的记录 id。
  const [failedExpandedId, setFailedExpandedId] = useState<string | null>(null);
  // 正在换后端重试的记录 id (区分无关的普通生成, 面板"重试中…"只对本记录显示)。
  const [retryingId, setRetryingId] = useState<string | null>(null);
  // 批2 布局门禁: 生成被布局 lint 拦下时暂存 issues, 展示"去修正 / 忽略并继续"。
  const [layoutGate, setLayoutGate] = useState<LayoutLint | null>(null);
  // 被门禁拦下的那次生成参数 (照片 + 后端覆盖等), "忽略并继续"照原样重放, 不丢换后端/目标照片。
  const [pendingRender, setPendingRender] = useState<{
    photoId: string;
    options: {
      allowUnlabeled?: boolean;
      backend?: GeometryEditBackend;
    };
  } | null>(null);
  // B4: 正在为哪张结果选择驳回原因 (展开原因 chips)。
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  // render-note-b1: 当前大图的备注草稿 (随 latest 切换重置) + 保存中态。
  const [commentDraft, setCommentDraft] = useState('');
  const [savingComment, setSavingComment] = useState(false);
  // P2b: 正在为哪张照片做透视标定 (打开 PerspectiveCalibrator 模态)。
  const [calibratingId, setCalibratingId] = useState<string | null>(null);
  const cancelRef = useRef(false);

  const selectedObj = photos.find((p) => p.id === selectedPhoto) ?? null;
  // F003: room_id -> 中文房名 (label.zh → space 标签 → id); 几何未载时回退裸 id, 空则空串。
  const roomName = (roomId: string | null | undefined): string => {
    if (!roomId) return '';
    const room = geometry ? roomById(geometry, roomId) : null;
    return room && geometry ? roomDisplayName(geometry, room) : roomId;
  };
  // 就绪 = 已标注房间 且 已选合法视角(v0..v3)。
  const selReady = !!(
    selectedObj?.room_id &&
    selectedObj?.direction &&
    (VIEWS as readonly string[]).includes(selectedObj.direction)
  );
  const canGenerate = !!selectedPhoto && (selReady || lowAccuracyConfirmed);

  // 切换照片后重置低准确度确认(避免上一张的降级意外带到新照片)。
  useEffect(() => {
    setLowAccuracyConfirmed(false);
  }, [selectedPhoto]);

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
      const [st, photoList, renderList, geo] = await Promise.all([
        getAiStatus(),
        listBaselinePhotos(id, baselineId),
        listRenders(id, schemeId),
        fetchBaselineGeometry(id, baselineId).catch(() => null),
      ]);
      if (!mounted.current || activeScope.current !== scope) return;
      const realRenders = renderList.filter((r) => r.mode === 'real-photo');
      // P0 用途过滤: 只有空房照 (purpose=empty 或历史缺省 null) 能做实拍底图; 墙面材质/底图
      // 描摹等被误选会白烧额度, 后端亦硬校验, 此处先在 UI 层不展示。
      const emptyPhotos = photoList.filter(
        (p) => p.purpose == null || p.purpose === 'empty',
      );
      setStatus(st);
      setGeometry(geo ? (geo as unknown as FpGeometry) : null);
      setPhotos(emptyPhotos);
      // 默认选「已标注房间」的最新照片 (P1-5): 未标注走整宅参考是质量最差路径。
      const preferred =
        emptyPhotos.find((p) => p.room_id)?.id ?? emptyPhotos[0]?.id ?? null;
      setSelectedPhoto((prev) =>
        prev && emptyPhotos.some((p) => p.id === prev) ? prev : preferred,
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
    setLayoutGate(null); // 切方案/项目: 清掉上一方案的布局门禁提示 (reload 依赖 schemeId)
    setPendingRender(null);
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

  // 生成主流程 (onGenerate 与换后端重试共用): 提交 job -> 3s 轮询 -> 完成落 latest。
  const runRender = useCallback(
    async (
      photoId: string,
      options?: {
        allowUnlabeled?: boolean;
        backend?: GeometryEditBackend;
        allowLayoutIssues?: boolean;
      },
    ) => {
      if (generating || schemeLocked || ctxLoading) return;
      const scope = `${id}|${schemeId}`;
      cancelRef.current = false;
      setGenerating(true);
      setLayoutGate(null); // 新一轮生成: 清掉上次的布局门禁提示
      setPendingRender(null);
      try {
        const { job_id } = await startRenderReal(
          id,
          schemeId,
          photoId,
          options,
        );
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
            // P4 透出: 验收未过时不报"成功"误导 (结果卡片会折叠展示失败原因)。
            if (autoCheckFailed(job.result)) {
              showToast('已生成,但自动验收未通过,详见结果卡片', 'info');
            } else {
              showToast('实拍效果图已生成', 'success');
            }
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
        if (!mounted.current) return;
        // 批2 布局门禁: 不当"失败"报, 展示 issues + 记住本次参数供"忽略并继续"原样重放。
        if (e instanceof LayoutGateError) {
          setLayoutGate(e.layoutLint);
          setPendingRender({ photoId, options: options ?? {} });
        } else {
          const msg = e instanceof Error ? e.message : String(e);
          showToast(`生成失败:${msg}`, 'error');
          // P0-5: 标定失效导致的 409 —— 刷新照片列表让"标定已过期"徽标即时出现 (状态一致)。
          if (msg.includes('标定')) void reload();
        }
      } finally {
        if (mounted.current) setGenerating(false);
      }
    },
    [id, schemeId, generating, schemeLocked, ctxLoading, showToast, reload],
  );

  const onGenerate = useCallback(async () => {
    if (!canGenerate || !selectedPhoto) return;
    // 未就绪但已确认低准确度 -> 显式降级绕过后端 readiness gate。
    await runRender(selectedPhoto, { allowUnlabeled: !selReady });
  }, [runRender, canGenerate, selectedPhoto, selReady]);

  // 批2 布局门禁降级: 忽略布局问题, 用被拦下时的原参数 (含换后端/目标照片) 重放生成。
  const onIgnoreLayoutAndGenerate = useCallback(async () => {
    if (!pendingRender) return;
    await runRender(pendingRender.photoId, {
      ...pendingRender.options,
      allowLayoutIssues: true,
    });
  }, [runRender, pendingRender]);

  // 换后端重试 (P4 决策③): 同一张已标定照片, 单次覆盖为另一个几何锁定编辑后端重新生成。
  // 目标后端由记录推导 (retryBackendOf), retryingId 区分"本记录在重试"与无关的普通生成。
  const onRetryBackend = useCallback(
    async (r: RenderRecord) => {
      if (!r.photo_id) return;
      setRetryingId(r.id);
      try {
        await runRender(r.photo_id, { backend: retryBackendOf(r) });
      } finally {
        setRetryingId(null);
      }
    },
    [runRender],
  );

  // 换后端重试的可用性 (禁用原因; null=可用)。与 runRender 的守卫一一对应 (锁定/加载/在途
  // 生成), 否则按钮可点却静默无反应; 另查原照片仍存在且已标定、目标 fal 已配 key。
  const retryDisabledReason = useCallback(
    (r: RenderRecord): string | null => {
      if (schemeLocked) return '历史/已归档方案仅可查看,无法重新生成';
      if (ctxLoading) return '加载中…';
      if (status && !status.enabled) return 'AI 未配置,无法生成';
      if (generating) return '已有生成任务进行中';
      const photo = photos.find((p) => p.id === r.photo_id);
      if (!photo) return '原空房照已不存在或已改作他用,无法重试';
      if (!photo.calibration) return '原照片未标定透视,无法几何锁定重试';
      if (photo.calibration_stale)
        return '原照片标定已过期 (户型/房间已变更),请先重新标定';
      if (retryBackendOf(r) === 'fal' && !status?.fal_enabled)
        return 'fal 后端未配置 (缺 FAL_KEY)';
      return null;
    },
    [schemeLocked, ctxLoading, generating, photos, status],
  );

  // B2 验收 + B4 反馈: 给一条实拍效果图打验收/驳回状态 (最终交付图)。驳回可带不满意原因
  // (feedback_reason), 打完 reload 重算并同步概览 stepper。
  const onSetVerdict = useCallback(
    async (r: RenderRecord, next: 'accepted' | 'rejected', reason?: string) => {
      setSettingVerdict(r.id);
      try {
        await setRenderStatus(id, schemeId, r.id, next, reason);
        showToast(next === 'accepted' ? '已通过验收' : '已驳回', 'success');
        setRejectingId(null);
        await Promise.all([reload(), reloadWorkflow()]);
      } catch (e) {
        showToast(
          `操作失败:${e instanceof Error ? e.message : String(e)}`,
          'error',
        );
      } finally {
        setSettingVerdict(null);
      }
    },
    [id, schemeId, showToast, reload, reloadWorkflow],
  );

  // render-note-b1: 备注草稿随大图切换重置为该图已存备注。
  useEffect(() => {
    setCommentDraft(latest?.comment ?? '');
  }, [latest?.id, latest?.comment]);

  const copyRenderId = useCallback(
    async (rid: string) => {
      try {
        await navigator.clipboard.writeText(rid);
        showToast('已复制完整 ID', 'success');
      } catch {
        showToast('复制失败,请手动选择文本', 'error');
      }
    },
    [showToast],
  );

  // render-note-b1: 写单条可编辑备注 (空串=清除)。用服务端返回记录就地更新本地态 (immutable)。
  const onSaveComment = useCallback(
    async (r: RenderRecord, value: string) => {
      setSavingComment(true);
      try {
        const updated = await setRenderComment(id, schemeId, r.id, value);
        setRenders((prev) =>
          prev.map((p) => (p.id === updated.id ? updated : p)),
        );
        setLatest((prev) => (prev && prev.id === updated.id ? updated : prev));
        showToast(value.trim() ? '备注已保存' : '备注已清除', 'success');
      } catch (e) {
        showToast(
          `备注保存失败：${e instanceof Error ? e.message : String(e)}`,
          'error',
        );
      } finally {
        setSavingComment(false);
      }
    },
    [id, schemeId, showToast],
  );

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
          disabled={generating || schemeLocked || ctxLoading || !canGenerate}
          title={
            schemeLocked
              ? '历史户型版本或已锁定方案不能生成新效果图'
              : !selectedPhoto
              ? '请先选择一张空房照片'
              : !canGenerate
              ? '所选照片未标注房间或视角 —— 先标注,或勾选下方「低准确度模式」继续'
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
        <NoticeBanner tone="warn" className="mb-4">
          {isHistorical
            ? '当前方案属历史户型版本,只能查看已有效果图,不能生成新成果。'
            : '当前方案已锁定或不属当前户型版本,只能查看已有效果图。'}
        </NoticeBanner>
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
                      title={
                        photo.note || roomName(photo.room_id) || '空房照片'
                      }
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
                        <span className="absolute left-1 top-1">
                          <Badge
                            tone={photo.room_id ? 'green' : 'amber'}
                            size="xs"
                          >
                            {roomName(photo.room_id) || '未标注房间'}
                          </Badge>
                        </span>
                        {/* B5: 质量偏低的空房照右上角预警 (过暗/过曝/过小/糊)。 */}
                        {(photo.quality?.warnings?.length ?? 0) > 0 && (
                          <span
                            className="absolute right-1 top-1"
                            title={`可用性 ${photo.quality?.score}/100`}
                          >
                            <Badge tone="amber" size="xs">
                              质量偏低
                            </Badge>
                          </span>
                        )}
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
                baselineId={baselineId}
                photo={sel}
                onPicked={(dir) =>
                  setPhotos((prev) =>
                    prev.map((p) =>
                      p.id === sel.id ? { ...p, direction: dir } : p,
                    ),
                  )
                }
                onError={(msg) => showToast(msg, 'error')}
              />
            ) : null;
          })()}

          {/* 透视标定 (P2b): 选中已标注房间的照片后, 提供「几何锁定」标定入口。标定与否都不
              阻断生成 —— 已标定走 fal 几何锁定(家具按平面几何精准投影), 否则回退 gpt-image-2。 */}
          {selectedObj?.room_id && (
            <StudioCard>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="flex items-center gap-2 text-sm font-bold text-navy-700 dark:text-white">
                    精准落位 · 透视标定
                    {selectedObj.calibration &&
                    selectedObj.calibration_stale ? (
                      <Badge tone="amber" size="xs">
                        标定已过期
                      </Badge>
                    ) : selectedObj.calibration ? (
                      <Badge tone="green" size="xs">
                        已标定 ✓
                      </Badge>
                    ) : (
                      <Badge tone="gray" size="xs">
                        未标定
                      </Badge>
                    )}
                  </p>
                  <p className="mt-1 max-w-2xl text-xs text-gray-500 dark:text-gray-400">
                    {selectedObj.calibration && selectedObj.calibration_stale
                      ? '户型几何或房间标注已变更,此前的透视标定已失效 —— 直接出图会落位错乱。请重新标定后再生成(几何锁定出图会阻断过期标定)。'
                      : selectedObj.calibration
                      ? '本照片已标定,生成将走「几何锁定」路径:家具按平面几何精准投影落位(硬约束),结构与家具更贴合。'
                      : '在空房照上标出两组正交墙线 + 2 个墙角,即可启用「几何锁定」精准落位。不标定也能生成(自动回退旧路径),但落位可能不准。'}
                  </p>
                </div>
                <Button
                  variant={
                    selectedObj.calibration && !selectedObj.calibration_stale
                      ? 'neutral-outline'
                      : 'soft-brand'
                  }
                  onClick={() => setCalibratingId(selectedObj.id)}
                >
                  {selectedObj.calibration
                    ? '重新标定'
                    : '透视标定(启用精准落位)'}
                </Button>
              </div>
            </StudioCard>
          )}

          {/* P0-3 方案B: 轴测=独立预览, 实拍=独立生成。轴测效果图不作为实拍输入 (实拍仅锚定
              空房照 + 几何落位), 故不把"确认轴测"表达成实拍质量前置; 仅作可选的风格自检建议。 */}
          {currentScheme && currentScheme.has_confirmed_axon === false && (
            <NoticeBanner tone="info">
              实拍为独立生成,锚定空房照与几何落位,不会自动沿用轴测效果图。如想先校准整体风格,可到
              <a
                href={`/studio/projects/${encodeURIComponent(
                  id,
                )}/render?scheme=${encodeURIComponent(schemeId)}`}
                className="font-medium text-brand-600 underline dark:text-brand-400"
              >
                {' '}
                轴测效果图页{' '}
              </a>
              生成一张预览(可选,不影响实拍出图)。
            </NoticeBanner>
          )}

          {/* 生成前输入确认面板 (B2): 聚合展示本次实拍将用到的输入栈, 让用户生成前一眼核对。 */}
          {selectedObj && (
            <StudioCard>
              <p className="mb-3 text-sm font-bold text-navy-700 dark:text-white">
                生成前确认
              </p>
              <div className="flex flex-wrap gap-4">
                {/* 选中空房照 */}
                <div>
                  <RenderImage
                    src={selectedObj.thumb_url ?? selectedObj.url}
                    alt="选中空房照"
                    className="h-24 w-32"
                    imgClassName="h-24 w-32 object-cover rounded-lg"
                    fallbackLabel="照片加载失败"
                  />
                  <p className="mt-1 text-center text-[11px] text-gray-500 dark:text-gray-400">
                    空房底图
                  </p>
                </div>
                {/* 轴测参考 (按房切片+按视角旋转; 未标注则整宅) */}
                <div>
                  {selectedObj.room_id && selectedObj.direction ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={`${API_BASE}/projects/${encodeURIComponent(
                        id,
                      )}/schemes/${encodeURIComponent(
                        schemeId,
                      )}/axon-view?room_id=${encodeURIComponent(
                        selectedObj.room_id,
                      )}&view=${selectedObj.direction}`}
                      alt="几何落位参考"
                      loading="lazy"
                      className="h-24 w-32 rounded-lg bg-gray-50 object-contain dark:bg-navy-900"
                    />
                  ) : (
                    <div className="flex h-24 w-32 items-center justify-center rounded-lg bg-gray-50 text-center text-[11px] text-gray-400 dark:bg-navy-900">
                      整宅参考
                      <br />
                      (未按房切片)
                    </div>
                  )}
                  <p className="mt-1 text-center text-[11px] text-gray-500 dark:text-gray-400">
                    几何落位参考
                  </p>
                </div>
                {/* 关键参数 */}
                <dl className="min-w-[12rem] flex-1 space-y-1 text-sm">
                  <div className="flex justify-between gap-2">
                    <dt className="text-gray-500 dark:text-gray-400">房间</dt>
                    <dd className="font-medium text-navy-700 dark:text-white">
                      {roomName(selectedObj.room_id) || '未标注'}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-gray-500 dark:text-gray-400">
                      拍摄视角
                    </dt>
                    <dd className="font-medium text-navy-700 dark:text-white">
                      {selectedObj.direction &&
                      (VIEWS as readonly string[]).includes(
                        selectedObj.direction,
                      )
                        ? selectedObj.direction
                        : '未选'}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-gray-500 dark:text-gray-400">
                      风格快照
                    </dt>
                    <dd className="max-w-[16rem] truncate text-right font-medium text-navy-700 dark:text-white">
                      {currentScheme?.style_prompt || '(默认风格)'}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-gray-500 dark:text-gray-400">
                      输出尺寸
                    </dt>
                    <dd className="font-medium text-navy-700 dark:text-white">
                      跟随照片比例
                    </dd>
                  </div>
                </dl>
              </div>

              {/* 低准确度模式: 未就绪时显式降级门 */}
              {!selReady && (
                <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-900/40">
                  <label className="flex cursor-pointer items-start gap-2 text-sm text-amber-800 dark:text-amber-200">
                    <input
                      type="checkbox"
                      checked={lowAccuracyConfirmed}
                      onChange={(e) =>
                        setLowAccuracyConfirmed(e.target.checked)
                      }
                      className="mt-0.5"
                    />
                    <span>
                      以<b>低准确度模式</b>继续 —— 所选照片未标注
                      {!selectedObj.room_id && '房间'}
                      {!selectedObj.room_id &&
                        !(
                          selectedObj.direction &&
                          (VIEWS as readonly string[]).includes(
                            selectedObj.direction,
                          )
                        ) &&
                        '与'}
                      {!(
                        selectedObj.direction &&
                        (VIEWS as readonly string[]).includes(
                          selectedObj.direction,
                        )
                      ) && '拍摄视角'}
                      ,轴测参考会退回整宅/不旋转,家具易串房间或贴错墙,出图匹配度较差。建议先标注后再生成。
                    </span>
                  </label>
                </div>
              )}
            </StudioCard>
          )}

          {/* 批2 布局门禁: 家具落位有设计问题, 生成被拦下 -> 列出问题 + 去修正/忽略并继续。 */}
          {layoutGate && (
            <StudioCard extra="flex flex-col gap-3 border-amber-300 dark:border-amber-500/40">
              <div className="flex items-center gap-2">
                <Badge tone="amber">家具布局有设计问题</Badge>
                <span className="text-sm text-gray-600 dark:text-gray-300">
                  出图会忠实照搬落位,建议先修正再生成。
                </span>
              </div>
              <ul className="space-y-1 text-sm text-amber-700 dark:text-amber-300">
                {layoutGate.issues.map((issue, i) => (
                  <li key={`${issue.code}-${issue.index ?? i}`}>
                    · {issue.message}
                  </li>
                ))}
              </ul>
              <div className="flex flex-wrap items-center gap-2">
                <LinkButton
                  href={`/studio/projects/${encodeURIComponent(
                    id,
                  )}/editor?scheme=${encodeURIComponent(
                    schemeId,
                  )}&tab=furniture`}
                  variant="primary"
                >
                  去编辑器调整家具
                </LinkButton>
                <Button
                  variant="soft-amber"
                  onClick={() => void onIgnoreLayoutAndGenerate()}
                  disabled={generating}
                >
                  {generating ? '生成中…' : '忽略并继续生成'}
                </Button>
                <Button
                  variant="neutral-outline"
                  onClick={() => {
                    setLayoutGate(null);
                    setPendingRender(null);
                  }}
                  disabled={generating}
                >
                  关闭
                </Button>
              </div>
            </StudioCard>
          )}

          {/* 最新结果 */}
          {latest ? (
            <StudioCard extra="flex flex-col">
              {/* P4 透出: 验收未过默认折叠 (失败原因+换后端重试); 展开后保留错误横幅提醒。
                  人工已验收 (accepted) 覆盖机器判定, 不折叠不弱化 (shouldCollapseFailed)。 */}
              {shouldCollapseFailed(latest) &&
              failedExpandedId !== latest.id ? (
                <AutoCheckFailedPanel
                  record={latest}
                  onExpand={() => setFailedExpandedId(latest.id)}
                  onRetry={() => void onRetryBackend(latest)}
                  retryDisabledReason={retryDisabledReason(latest)}
                  retrying={retryingId === latest.id}
                />
              ) : (
                <>
                  {shouldCollapseFailed(latest) && (
                    <div className="mb-3">
                      <NoticeBanner tone="error" title="自动验收未通过">
                        {(latest.auto_check?.fail_reasons ?? []).join('; ') ||
                          '该图未通过程序化验收,谨慎用作交付。'}
                      </NoticeBanner>
                    </div>
                  )}
                  <div className="mb-3 w-full overflow-hidden rounded-xl bg-gray-50 dark:bg-navy-900">
                    <RenderImage
                      src={latest.preview_url ?? latest.url}
                      alt={`${id} ${schemeId} 实拍效果图`}
                      className="h-[420px]"
                      imgClassName="h-[420px] w-full object-contain"
                      fallbackLabel="效果图加载失败"
                    />
                  </div>
                </>
              )}
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="flex items-center gap-2 text-sm font-medium text-gray-600 dark:text-gray-300">
                  最新实拍效果图 · {latest.model}
                  <RenderIdChip id={latest.id} onCopy={copyRenderId} />
                  {latest.low_accuracy && (
                    <Badge tone="amber" size="xs">
                      低准确度
                    </Badge>
                  )}
                  <RenderQualityBadges record={latest} />
                  {latest.status === 'accepted' && (
                    <Badge tone="green" size="xs">
                      ✓ 最终交付图
                    </Badge>
                  )}
                  {latest.status === 'rejected' && (
                    <Badge tone="gray" size="xs">
                      已驳回
                    </Badge>
                  )}
                </p>
                <div className="flex items-center gap-2">
                  {/* B2 验收: 通过验收=设为最终交付图; 驳回=标记不采用 (不删文件)。
                      验收失败且未展开时禁点 —— 没看过图不能设为交付图。 */}
                  {latest.status !== 'accepted' && (
                    <Button
                      variant="success-outline"
                      onClick={() => void onSetVerdict(latest, 'accepted')}
                      disabled={
                        settingVerdict === latest.id ||
                        (shouldCollapseFailed(latest) &&
                          failedExpandedId !== latest.id)
                      }
                      title={
                        shouldCollapseFailed(latest) &&
                        failedExpandedId !== latest.id
                          ? '自动验收未通过,请先展开查看图片再决定是否通过验收'
                          : undefined
                      }
                    >
                      {settingVerdict === latest.id ? '…' : '✅ 通过验收'}
                    </Button>
                  )}
                  {latest.status !== 'rejected' && (
                    <Button
                      variant="neutral-outline"
                      onClick={() =>
                        setRejectingId((prev) =>
                          prev === latest.id ? null : latest.id,
                        )
                      }
                      disabled={settingVerdict === latest.id}
                    >
                      {settingVerdict === latest.id ? '…' : '不满意 / 驳回'}
                    </Button>
                  )}
                  <Button
                    variant="danger-outline"
                    onClick={() => void onDelete(latest)}
                    disabled={deletingId === latest.id}
                  >
                    {deletingId === latest.id ? '删除中…' : '删除'}
                  </Button>
                  <LinkButton
                    href={latest.url}
                    download={`${id}-${schemeId}-real.png`}
                    variant="primary"
                  >
                    下载 PNG
                  </LinkButton>
                </div>
              </div>

              {/* B4 反馈闭环: 选不满意原因 -> 记录 rejected+reason, 并给出对应修正入口。 */}
              {rejectingId === latest.id && (
                <div className="mt-3 rounded-xl border border-gray-200 p-3 dark:border-white/10">
                  <p className="mb-2 text-xs font-medium text-gray-600 dark:text-gray-300">
                    哪里不满意?(选一项,便于定位到修正入口)
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {FEEDBACK_REASONS.map((reason) => (
                      <button
                        key={reason.key}
                        type="button"
                        disabled={settingVerdict === latest.id}
                        onClick={() =>
                          void onSetVerdict(latest, 'rejected', reason.key)
                        }
                        className="rounded-lg border border-gray-300 px-2.5 py-1 text-xs font-medium text-navy-700 hover:border-brand-500 disabled:opacity-50 dark:border-white/10 dark:text-gray-200"
                      >
                        {reason.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {latest.status === 'rejected' &&
                (() => {
                  const reason = FEEDBACK_REASONS.find(
                    (x) => x.key === latest.feedback_reason,
                  );
                  if (!reason) return null;
                  const basePath = `/studio/projects/${encodeURIComponent(id)}`;
                  const href =
                    reason.sub === 'baseline'
                      ? `${basePath}/baseline`
                      : reason.sub === 'scheme'
                      ? `${basePath}/scheme`
                      : reason.sub === 'editor'
                      ? `${basePath}/editor?scheme=${encodeURIComponent(
                          schemeId,
                        )}&tab=furniture`
                      : null;
                  return (
                    <div className="mt-3">
                      <NoticeBanner tone="warn">
                        已标记为不满意「{reason.label}」。下一步:
                        {reason.fixLabel}。
                        {href && (
                          <>
                            {' '}
                            <a
                              href={href}
                              className="font-medium text-brand-600 underline dark:text-brand-400"
                            >
                              前往 →
                            </a>
                          </>
                        )}
                      </NoticeBanner>
                    </div>
                  );
                })()}

              {/* render-note-b1: 单条可编辑备注 —— 用户对这张图的意见, 落生产 renders.json
                  供下一轮针对性优化。与验收 status 正交。 */}
              <div className="mt-4 border-t border-gray-100 pt-3 dark:border-white/10">
                <label
                  htmlFor={`render-note-${latest.id}`}
                  className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-gray-600 dark:text-gray-300"
                >
                  <MdEditNote className="h-4 w-4" />
                  备注（你对这张图的意见）
                </label>
                <textarea
                  id={`render-note-${latest.id}`}
                  value={commentDraft}
                  onChange={(e) => setCommentDraft(e.target.value)}
                  disabled={savingComment}
                  rows={2}
                  maxLength={2000}
                  placeholder="写下你对这张图的意见，方便下一轮针对性修改"
                  className={`${inputCls} resize-y`}
                />
                <div className="mt-2 flex items-center justify-end gap-2">
                  {latest.comment && (
                    <Button
                      variant="neutral-outline"
                      size="sm"
                      onClick={() => void onSaveComment(latest, '')}
                      disabled={savingComment}
                    >
                      清除
                    </Button>
                  )}
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => void onSaveComment(latest, commentDraft)}
                    disabled={
                      savingComment || commentDraft === (latest.comment ?? '')
                    }
                  >
                    {savingComment ? '保存中…' : '保存备注'}
                  </Button>
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
                      onClick={() => {
                        // 点缩略图 = 明确的查看意图: 验收未过的图直接展开大图, 不再折叠。
                        setLatest(r);
                        setFailedExpandedId(r.id);
                      }}
                      className="mb-2 w-full overflow-hidden rounded-lg bg-gray-50 dark:bg-navy-900"
                      title="设为大图查看"
                    >
                      <RenderImage
                        src={r.thumb_url ?? r.url}
                        alt={`${id} ${schemeId} 实拍效果图 ${r.id}`}
                        className="h-32"
                        imgClassName={`h-32 w-full object-cover${
                          shouldCollapseFailed(r) ? ' opacity-50 grayscale' : ''
                        }`}
                        fallbackLabel="加载失败"
                      />
                    </button>
                    {autoCheckFailed(r) && (
                      <div className="mb-1 flex justify-center">
                        <AutoCheckFailedBadge record={r} />
                      </div>
                    )}
                    {/* render-note-b1: 唯一标识 + 有备注标记 (只读; 编辑走「设为大图」) */}
                    <div className="mb-1 flex items-center justify-center gap-2">
                      <RenderIdChip id={r.id} onCopy={copyRenderId} />
                      {r.comment && (
                        <span
                          title={r.comment}
                          className="text-xs text-amber-600 dark:text-amber-400"
                        >
                          📝
                        </span>
                      )}
                    </div>
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

      {/* P2b 透视标定模态: 标定成功后更新本地照片 (含 calibration) 并关闭。 */}
      {(() => {
        const target = photos.find((p) => p.id === calibratingId) ?? null;
        if (!target) return null;
        return (
          <PerspectiveCalibrator
            projectId={id}
            baselineId={baselineId}
            photo={target}
            onClose={() => setCalibratingId(null)}
            onCalibrated={(updated) => {
              setPhotos((prev) =>
                prev.map((p) => (p.id === updated.id ? updated : p)),
              );
              setCalibratingId(null);
              showToast('透视标定已保存,生成将走几何锁定精准落位', 'success');
            }}
          />
        );
      })()}
    </PageShell>
  );
}
