'use client';

import React, {
  use,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import Dropdown from 'components/dropdown';
import PageShell from 'components/studio/ui/PageShell';
import EmptyState from 'components/studio/ui/EmptyState';
import LoadingState from 'components/studio/ui/LoadingState';
import RenderImage from 'components/studio/ui/RenderImage';
import { Button, IconButton, LinkButton } from 'components/studio/ui/buttons';
import { Hairline, StudioCard, TimeAgo } from 'components/studio/ui/primitives';
import {
  BackendErrorBanner,
  Badge,
  type BadgeTone,
  NoticeBanner,
  PreferredBadge,
  StatusBadge,
  statusLabel,
} from 'components/studio/ui/status';
import { useToastContext } from 'components/studio/ui/ToastHost';
import { useConfirm } from 'components/studio/ui/ConfirmDialog';
import { useProjectWorkflow } from 'components/studio/workflow/ProjectWorkflowContext';
import {
  archiveScheme,
  restoreScheme,
  createScheme,
  deleteScheme,
  duplicateScheme,
  fetchProject,
  listBaselines,
  listSchemes,
  migrateScheme,
  patchScheme,
  pollJob,
  setPreferredScheme,
  startFurnish,
  type FurnishResult,
  type BaselineMeta,
  type FurnitureSchemeSummary,
  type SchemeSource,
} from 'lib/studioApi';
import {
  MdAutoAwesome,
  MdChair,
  MdCompare,
  MdContentCopy,
  MdDelete,
  MdEdit,
  MdImage,
  MdMoreVert,
  MdStarBorder,
  MdUnarchive,
} from 'react-icons/md';

// 方案来源徽标: 让 AI 候选 / 手动 / 副本 / 初始方案 一眼可辨(此前全靠有无风格意向隐性推断)。
const SOURCE_META: Record<
  SchemeSource,
  { label: string; tone: BadgeTone; ai?: boolean }
> = {
  ai: { label: 'AI 生成', tone: 'brand', ai: true },
  manual: { label: '手动', tone: 'gray' },
  duplicate: { label: '副本', tone: 'gray' },
  legacy: { label: '初始方案', tone: 'green' },
};

const POLL_MS = 1500;
const TIMEOUT_MS = 90 * 1000;

// 常用软装风格预设,点选即填入风格意向,便于快速试不同方向(可继续手动编辑)。
const STYLE_PRESETS = [
  '现代轻奢,浅色石材,胡桃木,少量墨绿点缀',
  '原木日式,浅色木饰面,棉麻,留白',
  '奶油风,米白暖调,弧形家具,原木点缀',
  '新中式,深色木作,水墨意境,黄铜细节',
  '侘寂风,微水泥,大地色,质朴陶艺',
  '法式复古,石膏线,人字拼地板,复古家具',
];

function slugTime(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(
    d.getHours(),
  )}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

function schemeHref(
  projectId: string,
  sub: 'editor' | 'gallery' | 'render',
  schemeId: string,
  baselineId?: string,
) {
  const params = new URLSearchParams({ scheme: schemeId });
  if (baselineId) params.set('baseline', baselineId);
  return `/studio/projects/${encodeURIComponent(
    projectId,
  )}/${sub}?${params.toString()}`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function nextSchemeId(prefix: string): string {
  return `${prefix}_${slugTime()}`;
}

export default function SchemePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { showToast } = useToastContext();
  const confirm = useConfirm();
  // 里程碑成功后跳转到新方案编辑器前, 先刷新工作流上下文, 让编辑器只读门(P0)看到新方案,
  // 否则新方案不在 context.availableSchemes 里会被判为只读。
  const workflow = useProjectWorkflow();

  const [schemes, setSchemes] = useState<FurnitureSchemeSummary[]>([]);
  // Phase D (D-5): 显示已归档开关 —— 归档=可逆暂存, 打开可见并恢复。
  const [showArchived, setShowArchived] = useState(false);
  const [baselines, setBaselines] = useState<BaselineMeta[]>([]);
  const [historicalSchemes, setHistoricalSchemes] = useState<
    FurnitureSchemeSummary[]
  >([]);
  const [showHistory, setShowHistory] = useState(false);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [refreshing, setRefreshing] = useState(false);
  // 当前户型版本 id (= project.current_baseline_version_id), 单一真源。
  const [currentVersionId, setCurrentVersionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');
  const [stylePrompt, setStylePrompt] = useState('');
  const [candidateCount, setCandidateCount] = useState(3);
  const [baseSchemeId, setBaseSchemeId] = useState('default');
  const [furnishWarnings, setFurnishWarnings] = useState<string[]>([]);
  const [compareIds, setCompareIds] = useState<string[]>([]);

  // 卡片列表按最近更新倒序(updated_at 为 ISO,字典序即时间序),便于快速回到刚改过的方案。
  const orderedSchemes = useMemo(
    () =>
      [...schemes].sort((a, b) =>
        (b.updated_at ?? '').localeCompare(a.updated_at ?? ''),
      ),
    [schemes],
  );

  // showArchived 从 ref 读, 使 reload 依赖仅 [id] 稳定: 切户型才非-silent 重载, 切'显示已归档'
  // 走 silent(见下方 effect), 不再闪骨架屏。
  const showArchivedRef = useRef(showArchived);
  showArchivedRef.current = showArchived;

  // silent=true 用于变更后的后台刷新: 不翻 loadState(否则 PageShell 用骨架屏整块替换主体,
  // 每次操作都闪一下、丢失滚动)。仅首屏用 loading 骨架。
  const reload = useCallback(
    async (opts?: { silent?: boolean }) => {
      const silent = opts?.silent ?? false;
      try {
        if (silent) setRefreshing(true);
        else setLoadState('loading');
        const [projectMeta, baselineList] = await Promise.all([
          fetchProject(id),
          listBaselines(id),
        ]);
        // 当前户型以 project.current_baseline_version_id 为准 (与工作流上下文/编辑器只读门同源),
        // 不再另按 status==='confirmed' 推算, 消除双真源导致的 409/只读错配。
        const current = projectMeta.current_baseline_version_id ?? undefined;
        setCurrentVersionId(current ?? null);
        const list = current
          ? await listSchemes(id, {
              baselineVersionId: current,
              includeArchived: showArchivedRef.current,
            })
          : [];
        // 历史列表容错: 单个坏/旧户型版本的 listSchemes 抛错不再拖垮全页 (allSettled)。
        const settled = await Promise.allSettled(
          baselineList
            .filter((b) => b.id !== current)
            .map((b) =>
              listSchemes(id, {
                baselineVersionId: b.id,
                includeArchived: true,
              }),
            ),
        );
        setBaselines(baselineList);
        setSchemes(list);
        setHistoricalSchemes(
          settled.flatMap((r) => (r.status === 'fulfilled' ? r.value : [])),
        );
        setError(null);
        setLoadState('ready');
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        if (!silent) setLoadState('error');
      } finally {
        if (silent) setRefreshing(false);
      }
    },
    [id],
  );

  useEffect(() => {
    void reload();
  }, [reload]);

  // '显示已归档' 切换: 静默重取 (不闪骨架)。跳过首帧 (首屏已由上面 mount effect 载过)。
  const firstArchivedRun = useRef(true);
  useEffect(() => {
    if (firstArchivedRun.current) {
      firstArchivedRun.current = false;
      return;
    }
    void reload({ silent: true });
  }, [showArchived, reload]);

  // 空态引导用: 聚焦新建输入 / 滚动到历史区。
  const newNameRef = useRef<HTMLInputElement>(null);
  const historyRef = useRef<HTMLDivElement>(null);
  const focusCreate = useCallback(() => {
    newNameRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    newNameRef.current?.focus();
  }, []);
  const revealHistory = useCallback(() => {
    setShowHistory(true);
    historyRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  // 卸载守卫: furnish 轮询循环在组件卸载后停止 setState / 停止轮询 (避免离开页面后仍打请求)。
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // furnish 的 base 必须是当前户型版本下真实存在的方案。baseSchemeId 初值 'default', 但初始
  // 方案(default)可能 pin 在旧户型版本而不在本列表 -> <select> 值不匹配(视觉显首项、状态仍
  // 'default')-> 生成时误发 'default' -> 后端 'default' 绑 v1 != 当前 -> 报"户型已进入历史"。
  // 加载后把 baseSchemeId 校正到列表内(首选优先, 否则首个), 保证发出的 base 真实可用。
  useEffect(() => {
    const cands = schemes.filter((s) => s.status !== 'archived');
    if (cands.length && !cands.some((s) => s.id === baseSchemeId)) {
      setBaseSchemeId((cands.find((s) => s.preferred) ?? cands[0]).id);
    }
  }, [schemes, baseSchemeId]);

  const generating = busy === 'furnish';
  // 候选生成期间每秒更新已用时(约 90s),给等待以进度反馈。
  const [genElapsed, setGenElapsed] = useState(0);
  useEffect(() => {
    if (!generating) return;
    const t0 = Date.now();
    setGenElapsed(0);
    const iv = setInterval(
      () => setGenElapsed(Math.floor((Date.now() - t0) / 1000)),
      1000,
    );
    return () => clearInterval(iv);
  }, [generating]);
  const currentBaseline = currentVersionId
    ? baselines.find((b) => b.id === currentVersionId)
    : undefined;
  const canCreateSchemes = !!currentBaseline;
  // furnish 的 base 候选: 当前列表内的非归档方案 (归档件不能作风格基底, 否则后端拒写)。
  const baseCandidates = useMemo(
    () => schemes.filter((s) => s.status !== 'archived'),
    [schemes],
  );
  // furnish 需要一个当前户型下真实存在(且非归档)的 base 方案。空列表时 baseSchemeId 停在初值
  // 'default'(pin 在旧版本)-> 误发 'default' 报"户型已进入历史"。无有效 base 时禁用生成。审计 B。
  const furnishBaseValid = baseCandidates.some((s) => s.id === baseSchemeId);
  const compareHref = `/studio/projects/${encodeURIComponent(
    id,
  )}/compare?schemes=${compareIds.map(encodeURIComponent).join(',')}`;

  const toggleCompare = useCallback((schemeId: string) => {
    setCompareIds((prev) => {
      if (prev.includes(schemeId)) return prev.filter((id) => id !== schemeId);
      if (prev.length >= 3) return prev;
      return [...prev, schemeId];
    });
  }, []);

  const onCreate = useCallback(async () => {
    // 方案 ID 自动生成(时间戳,路径安全),不再要求设计师手填机器 slug。
    const sid = nextSchemeId('scheme_manual');
    const name = newName.trim() || '新方案'; // 纯空格也回落"新方案"
    setBusy('create');
    try {
      await createScheme(id, {
        id: sid,
        name,
        source: 'manual',
        base_scheme_id: 'default',
        furniture: [],
      });
      setNewName('');
      showToast('方案已创建,进入布置家具', 'success');
      await workflow.reload();
      router.push(schemeHref(id, 'editor', sid));
    } catch (e) {
      showToast(
        `创建失败:${e instanceof Error ? e.message : String(e)}`,
        'error',
      );
    } finally {
      setBusy(null);
    }
  }, [id, newName, showToast, workflow, router]);

  const onDuplicate = useCallback(
    async (scheme: FurnitureSchemeSummary) => {
      const sid = `${scheme.id}_copy_${slugTime()}`;
      setBusy(`copy:${scheme.id}`);
      try {
        await duplicateScheme(id, scheme.id, {
          id: sid,
          name: `${scheme.name} 副本`,
        });
        showToast('方案已复制,进入布置家具', 'success');
        await workflow.reload();
        router.push(schemeHref(id, 'editor', sid));
      } catch (e) {
        showToast(
          `复制失败:${e instanceof Error ? e.message : String(e)}`,
          'error',
        );
      } finally {
        setBusy(null);
      }
    },
    [id, showToast, workflow, router],
  );

  const onSaveName = useCallback(async () => {
    if (!editingId || !editingName.trim()) return;
    setBusy(`rename:${editingId}`);
    try {
      await patchScheme(id, editingId, { name: editingName.trim() });
      setEditingId(null);
      setEditingName('');
      showToast('方案已重命名', 'success');
      await Promise.all([reload({ silent: true }), workflow.reload()]);
    } catch (e) {
      showToast(
        `重命名失败:${e instanceof Error ? e.message : String(e)}`,
        'error',
      );
    } finally {
      setBusy(null);
    }
  }, [id, editingId, editingName, showToast, reload, workflow]);

  // Phase D (D-5): 恢复已归档方案 (archived -> draft)。归档=可逆暂存, 非黑洞。
  const onRestoreScheme = useCallback(
    async (scheme: FurnitureSchemeSummary) => {
      setBusy(`restore:${scheme.id}`);
      try {
        await restoreScheme(id, scheme.id);
        showToast('方案已恢复为草稿', 'success');
        await Promise.all([reload({ silent: true }), workflow.reload()]);
      } catch (e) {
        showToast(
          `恢复失败:${e instanceof Error ? e.message : String(e)}`,
          'error',
        );
      } finally {
        setBusy(null);
      }
    },
    [id, showToast, reload, workflow],
  );

  const onSetPreferred = useCallback(
    async (scheme: FurnitureSchemeSummary) => {
      setBusy(`preferred:${scheme.id}`);
      try {
        await setPreferredScheme(id, scheme.id);
        showToast('首选方案已更新', 'success');
        await Promise.all([reload({ silent: true }), workflow.reload()]);
      } catch (e) {
        showToast(
          `设置失败:${e instanceof Error ? e.message : String(e)}`,
          'error',
        );
      } finally {
        setBusy(null);
      }
    },
    [id, showToast, reload, workflow],
  );

  const onArchiveScheme = useCallback(
    async (scheme: FurnitureSchemeSummary) => {
      const ok = await confirm({
        title: `归档“${scheme.name}”？`,
        message:
          '归档后默认列表不再显示该方案(可用“显示已归档”查看并随时恢复),已有成果文件不会删除。',
        confirmText: '归档',
        danger: true,
      });
      if (!ok) return;
      setBusy(`archive:${scheme.id}`);
      try {
        await archiveScheme(id, scheme.id);
        showToast('方案已归档', 'success');
        // 从对比勾选中移除已归档件 (否则顶栏计数陈旧、对比链带失效 id)。
        setCompareIds((prev) => prev.filter((x) => x !== scheme.id));
        await Promise.all([reload({ silent: true }), workflow.reload()]);
      } catch (e) {
        showToast(
          `归档失败:${e instanceof Error ? e.message : String(e)}`,
          'error',
        );
      } finally {
        setBusy(null);
      }
    },
    [id, confirm, showToast, reload, workflow],
  );

  const onMigrateScheme = useCallback(
    async (scheme: FurnitureSchemeSummary) => {
      if (!currentBaseline) return;
      setBusy(`migrate:${scheme.id}`);
      const newSid = nextSchemeId(`${scheme.id}_migrated`);
      try {
        await migrateScheme(id, scheme.id, {
          target_baseline_version_id: currentBaseline.id,
          id: newSid,
          name: `${scheme.name} - ${currentBaseline.id}`,
        });
        showToast('方案已迁移为当前户型草稿方案,进入编辑', 'success');
        await workflow.reload();
        router.push(schemeHref(id, 'editor', newSid));
      } catch (e) {
        showToast(
          `迁移失败:${e instanceof Error ? e.message : String(e)}`,
          'error',
        );
      } finally {
        setBusy(null);
      }
    },
    [id, currentBaseline, showToast, workflow, router],
  );

  const onDelete = useCallback(
    async (scheme: FurnitureSchemeSummary) => {
      if (scheme.id === 'default') return;
      const ok = await confirm({
        title: '删除方案',
        message: `将删除「${scheme.name}」。此操作会移入回收站,不会删除已生成图片文件。`,
        confirmText: '删除',
        danger: true,
      });
      if (!ok) return;
      setBusy(`delete:${scheme.id}`);
      try {
        await deleteScheme(id, scheme.id);
        showToast('方案已删除', 'success');
        setCompareIds((prev) => prev.filter((x) => x !== scheme.id));
        await Promise.all([reload({ silent: true }), workflow.reload()]);
      } catch (e) {
        showToast(
          `删除失败:${e instanceof Error ? e.message : String(e)}`,
          'error',
        );
      } finally {
        setBusy(null);
      }
    },
    [id, confirm, showToast, reload, workflow],
  );

  const onGenerate = useCallback(async () => {
    if (!stylePrompt.trim()) {
      showToast('请输入风格意向', 'error');
      return;
    }
    // 审计 B: base 必须是当前列表内真实方案, 否则会误发历史 default 触发 409。
    if (!furnishBaseValid) {
      showToast('请先在下方创建一套方案,作为 AI 风格的布局基础', 'error');
      return;
    }
    setBusy('furnish');
    setFurnishWarnings([]);
    try {
      const { job_id } = await startFurnish(id, {
        style_prompt: stylePrompt.trim(),
        count: candidateCount,
        base_scheme_id: baseSchemeId,
      });
      const started = Date.now();
      // eslint-disable-next-line no-constant-condition
      while (true) {
        await sleep(POLL_MS);
        if (!mountedRef.current) return; // 已离开本页: 停止轮询与后续 setState。
        const job = await pollJob<FurnishResult>(job_id);
        if (!mountedRef.current) return;
        if (job.status === 'done' && job.result) {
          setFurnishWarnings(job.result.warnings || []);
          showToast(
            `已生成 ${job.result.schemes.length} 套候选方案`,
            'success',
          );
          // 同时刷新共享工作流上下文 (方案预览/效果图页顶栏的方案选择器与 currentScheme 靠它),
          // 否则新生成的 AI 方案只进本页列表, 在那两页看不到 (与 onCreate 一致地一并刷新)。
          await Promise.all([reload({ silent: true }), workflow.reload()]);
          break;
        }
        if (job.status === 'error') {
          throw new Error(job.error || '生成失败');
        }
        if (Date.now() - started > TIMEOUT_MS) {
          throw new Error('生成超时,请稍后刷新查看结果');
        }
      }
    } catch (e) {
      showToast(
        `生成失败:${e instanceof Error ? e.message : String(e)}`,
        'error',
      );
    } finally {
      setBusy(null);
    }
  }, [
    id,
    stylePrompt,
    candidateCount,
    baseSchemeId,
    furnishBaseValid,
    showToast,
    reload,
    workflow,
  ]);

  const actions = (
    <>
      <Link
        href={compareHref}
        aria-disabled={compareIds.length < 2}
        className={`inline-flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium ${
          compareIds.length >= 2
            ? 'bg-brand-500 text-white hover:bg-brand-600'
            : 'pointer-events-none bg-gray-100 text-gray-400'
        }`}
      >
        <MdCompare className="h-4 w-4" />
        对比方案 ({compareIds.length}/3)
      </Link>
      <Button
        variant="secondary"
        onClick={() => void reload({ silent: true })}
        disabled={refreshing}
      >
        刷新
      </Button>
    </>
  );

  return (
    <PageShell
      title="方案中心"
      description={`默认展示户型 ${
        currentBaseline?.id ?? 'v1'
      } 下未归档方案。历史版本方案不混入当前列表。`}
      actions={actions}
      state={loadState === 'loading' ? <LoadingState rows={2} /> : undefined}
    >
      {error && <BackendErrorBanner message={error} />}

      <StudioCard extra="mb-5">
        <div className="mb-3 flex items-center gap-2">
          <MdAutoAwesome className="h-5 w-5 text-brand-500" />
          <h2 className="text-base font-bold text-navy-700 dark:text-white">
            AI 生成风格候选
          </h2>
        </div>
        <p className="mb-3 text-xs text-gray-400">
          在锁定的家具布局上生成 N 个风格方向(材质/色彩/软装),AI 不移动家具,
          仅按风格换件并生成渲染风格描述。
        </p>
        <div className="mb-3 flex flex-wrap gap-2">
          {STYLE_PRESETS.map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => setStylePrompt(preset)}
              className="rounded-full border border-gray-200 px-3 py-1 text-xs font-medium text-gray-600 hover:border-brand-500 hover:text-brand-500 dark:border-white/10 dark:text-gray-300"
            >
              {preset.split(',')[0]}
            </button>
          ))}
        </div>
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_160px_180px_auto]">
          <textarea
            value={stylePrompt}
            aria-label="风格意向"
            onChange={(e) => setStylePrompt(e.target.value)}
            rows={3}
            placeholder="点选上方风格预设,或描述风格、材质、色彩偏好，例如：现代轻奢,浅色石材,胡桃木,少量墨绿点缀"
            className="min-h-[88px] rounded-lg border border-gray-200 px-3 py-2 text-sm text-navy-700 outline-none focus:border-brand-500 dark:border-white/10 dark:bg-navy-900 dark:text-white"
          />
          <label className="flex flex-col gap-1 text-xs font-medium text-gray-600 dark:text-gray-300">
            候选数量
            <select
              value={candidateCount}
              onChange={(e) => setCandidateCount(Number(e.target.value))}
              className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-navy-700 outline-none focus:border-brand-500 dark:border-white/10 dark:bg-navy-900 dark:text-white"
            >
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {n} 套
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-gray-600 dark:text-gray-300">
            基于方案
            <select
              value={furnishBaseValid ? baseSchemeId : ''}
              onChange={(e) => setBaseSchemeId(e.target.value)}
              disabled={!canCreateSchemes || baseCandidates.length === 0}
              className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-navy-700 outline-none focus:border-brand-500 dark:border-white/10 dark:bg-navy-900 dark:text-white"
            >
              {baseCandidates.length === 0 && (
                <option value="">(请先创建一套方案)</option>
              )}
              {baseCandidates.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <span className="font-normal text-gray-400">
              选一套已布置好的方案作布局底,AI 只换材质/色彩/软装
            </span>
          </label>
          <Button
            variant="primary"
            onClick={onGenerate}
            disabled={
              generating ||
              loadState !== 'ready' ||
              !canCreateSchemes ||
              !furnishBaseValid
            }
            className="self-end px-4"
          >
            {generating ? `生成中…(已 ${genElapsed}s)` : '生成候选'}
          </Button>
        </div>
        {/* 无有效布局底时"生成候选"禁用, 禁用按钮吞掉点击(toast 触发不了), 故给一行内联提示引导。 */}
        {canCreateSchemes &&
          !furnishBaseValid &&
          baseCandidates.length === 0 && (
            <p className="mt-3 text-xs text-gray-400">
              先在下方「新建方案」创建一套作为布局底,AI 才能在其上生成风格候选。
            </p>
          )}
        {furnishWarnings.length > 0 && (
          <NoticeBanner tone="warn" className="mt-3">
            {furnishWarnings.map((w, i) => (
              <p key={`${w}-${i}`}>{w}</p>
            ))}
          </NoticeBanner>
        )}
      </StudioCard>

      <StudioCard extra="mb-5">
        <div className="grid gap-3 md:grid-cols-[1fr_auto]">
          <input
            ref={newNameRef}
            value={newName}
            aria-label="新方案名称"
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && canCreateSchemes && busy !== 'create') {
                e.preventDefault();
                void onCreate();
              }
            }}
            placeholder="新方案名称(ID 自动生成),回车即可以当前户型为底新建"
            className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-navy-700 outline-none focus:border-brand-500 dark:border-white/10 dark:bg-navy-900 dark:text-white"
          />
          <Button
            variant="primary"
            onClick={onCreate}
            disabled={busy === 'create' || !canCreateSchemes}
            className="px-4"
          >
            {busy === 'create' ? '创建中…' : '新建方案'}
          </Button>
        </div>
      </StudioCard>

      {loadState === 'ready' && !canCreateSchemes ? (
        <EmptyState
          icon={<MdChair className="h-6 w-6" />}
          title="请先确认户型"
          description="当前项目还没有已确认户型版本，确认户型后才能创建软装方案。"
          action={
            <LinkButton
              href={`/studio/projects/${encodeURIComponent(id)}/baseline`}
              variant="primary"
            >
              去确认户型
            </LinkButton>
          }
        />
      ) : loadState === 'ready' && schemes.length === 0 ? (
        <EmptyState
          icon={<MdChair className="h-6 w-6" />}
          title="暂无方案"
          description={
            historicalSchemes.length > 0
              ? `当前户型还没有方案。你在旧户型版本有 ${historicalSchemes.length} 套方案,可迁移到当前户型;或以当前户型为底新建一套。`
              : '以当前户型为底新建一套方案(继承墙体/房间,暂无家具),之后即可布置家具、或用 AI 在其上生成风格候选。'
          }
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button variant="primary" onClick={focusCreate}>
                新建方案
              </Button>
              {historicalSchemes.length > 0 && (
                <Button variant="secondary" onClick={revealHistory}>
                  从历史迁移 →
                </Button>
              )}
            </div>
          }
        />
      ) : (
        <>
          <div className="mb-3 flex justify-end">
            <label className="flex cursor-pointer items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
                className="h-3.5 w-3.5 rounded border-gray-300"
              />
              显示已归档方案
            </label>
          </div>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {orderedSchemes.map((scheme) => {
              const isEditing = editingId === scheme.id;
              const isDefault = scheme.id === 'default';
              return (
                <StudioCard key={scheme.id} extra="h-full">
                  <div className="flex h-full flex-col gap-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          {isEditing ? (
                            <input
                              value={editingName}
                              onChange={(e) => setEditingName(e.target.value)}
                              autoFocus
                              onFocus={(e) => e.currentTarget.select()}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                  e.preventDefault();
                                  void onSaveName();
                                } else if (e.key === 'Escape') {
                                  e.preventDefault();
                                  setEditingId(null);
                                }
                              }}
                              className="min-w-[180px] rounded-lg border border-gray-200 px-3 py-1.5 text-sm font-bold text-navy-700 outline-none focus:border-brand-500 dark:border-white/10 dark:bg-navy-900 dark:text-white"
                            />
                          ) : (
                            <h2 className="break-words text-lg font-bold text-navy-700 dark:text-white">
                              {scheme.name}
                            </h2>
                          )}
                          {SOURCE_META[scheme.source] ? (
                            <Badge
                              tone={SOURCE_META[scheme.source].tone}
                              icon={
                                SOURCE_META[scheme.source].ai ? (
                                  <MdAutoAwesome className="h-3 w-3" />
                                ) : undefined
                              }
                            >
                              {SOURCE_META[scheme.source].label}
                            </Badge>
                          ) : null}
                          {scheme.preferred && <PreferredBadge />}
                        </div>
                        <p className="mt-1 break-all text-xs text-gray-500 dark:text-gray-400">
                          {isDefault ? '初始方案' : scheme.id} · 户型{' '}
                          {scheme.baseline_version_id ?? 'v1'}
                          {scheme.updated_at ? (
                            <TimeAgo
                              at={scheme.updated_at}
                              prefix=" · 更新"
                              className=""
                            />
                          ) : null}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {isEditing ? (
                          <>
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={onSaveName}
                              disabled={busy === `rename:${scheme.id}`}
                            >
                              保存
                            </Button>
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => setEditingId(null)}
                            >
                              取消
                            </Button>
                          </>
                        ) : (
                          <>
                            {/* 首选是工作流第 5 步的里程碑, 提到卡面做可点星标(对齐 overview/出图页),
                                不再只埋在 ⋮ 菜单。已首选则由上方 PreferredBadge 指示。 */}
                            {!scheme.preferred &&
                              scheme.status !== 'archived' && (
                                <IconButton
                                  title="设为首选"
                                  ariaLabel="设为首选"
                                  onClick={() => void onSetPreferred(scheme)}
                                  disabled={busy === `preferred:${scheme.id}`}
                                >
                                  <MdStarBorder className="h-5 w-5" />
                                </IconButton>
                              )}
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => {
                                setEditingId(scheme.id);
                                setEditingName(scheme.name);
                              }}
                              disabled={scheme.status !== 'draft'}
                            >
                              重命名
                            </Button>
                          </>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-sm">
                      <div>
                        <p className="text-xs text-gray-500">家具</p>
                        <p className="font-bold text-navy-700 dark:text-white">
                          {scheme.items}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500">效果图</p>
                        <p className="font-bold text-navy-700 dark:text-white">
                          {scheme.renders}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500">状态</p>
                        <div className="mt-0.5">
                          <StatusBadge kind="scheme" status={scheme.status} />
                        </div>
                      </div>
                    </div>

                    <div className="rounded-xl bg-gray-50 p-3 dark:bg-navy-900">
                      {scheme.latest_render_url ? (
                        <RenderImage
                          src={
                            scheme.latest_render_thumb_url ??
                            scheme.latest_render_url
                          }
                          alt={`${scheme.name} 最新成果`}
                          className="h-36"
                          imgClassName="h-36 w-full object-cover"
                          fallbackLabel="最新成果加载失败"
                        />
                      ) : (
                        <div className="flex h-36 items-center justify-center">
                          <p className="text-sm text-gray-500 dark:text-gray-400">
                            暂无最新成果缩略图
                          </p>
                        </div>
                      )}
                      {scheme.style_prompt ? (
                        <p
                          className="mt-2 line-clamp-2 text-xs text-gray-500 dark:text-gray-400"
                          title={scheme.style_prompt}
                        >
                          风格意向：{scheme.style_prompt}
                        </p>
                      ) : null}
                    </div>

                    <div className="mt-auto flex flex-wrap items-center gap-2">
                      {/* Phase D: 无 confirm 锁, 主操作恒为「编辑」; 已归档件主操作为「恢复」。 */}
                      {scheme.status === 'archived' ? (
                        <>
                          <Button
                            variant="primary"
                            onClick={() => void onRestoreScheme(scheme)}
                            disabled={busy === `restore:${scheme.id}`}
                          >
                            <MdUnarchive className="h-4 w-4" />
                            恢复
                          </Button>
                          <span className="text-xs text-gray-400">已归档</span>
                        </>
                      ) : (
                        <>
                          <LinkButton
                            href={schemeHref(id, 'editor', scheme.id)}
                            variant="primary"
                          >
                            <MdEdit className="h-4 w-4" />
                            编辑
                          </LinkButton>
                          <LinkButton
                            href={schemeHref(id, 'render', scheme.id)}
                            variant="secondary"
                          >
                            <MdAutoAwesome className="h-4 w-4" />
                            效果图
                          </LinkButton>
                          <Button
                            variant={
                              compareIds.includes(scheme.id)
                                ? 'primary'
                                : 'secondary'
                            }
                            onClick={() => toggleCompare(scheme.id)}
                            disabled={
                              !compareIds.includes(scheme.id) &&
                              compareIds.length >= 3
                            }
                          >
                            <MdCompare className="h-4 w-4" />
                            {compareIds.includes(scheme.id)
                              ? '已选对比'
                              : '对比勾选'}
                          </Button>
                        </>
                      )}
                      <Dropdown
                        button={
                          <IconButton ariaLabel="更多操作" title="更多操作">
                            <MdMoreVert className="h-4 w-4" />
                          </IconButton>
                        }
                        classNames="top-11 right-0 w-44"
                      >
                        <div className="flex flex-col rounded-xl border border-gray-200 bg-white py-1 shadow-lg dark:border-white/10 dark:bg-navy-700">
                          <Link
                            href={schemeHref(
                              id,
                              'gallery',
                              scheme.id,
                              scheme.baseline_version_id,
                            )}
                            className="flex items-center gap-2 px-3 py-2 text-sm text-navy-700 hover:bg-gray-50 dark:text-white dark:hover:bg-navy-800"
                          >
                            <MdImage className="h-4 w-4" />
                            方案预览
                          </Link>
                          {/* 设为首选已移至卡头星标(见上), ⋮ 菜单不再重复。 */}
                          <button
                            type="button"
                            onClick={() => void onDuplicate(scheme)}
                            disabled={
                              busy === `copy:${scheme.id}` ||
                              scheme.status === 'archived'
                            }
                            className="flex items-center gap-2 px-3 py-2 text-left text-sm text-navy-700 hover:bg-gray-50 disabled:opacity-50 dark:text-white dark:hover:bg-navy-800"
                          >
                            <MdContentCopy className="h-4 w-4" />
                            复制
                          </button>
                          {!isDefault && (
                            <>
                              <Hairline className="my-1" />
                              {scheme.status !== 'archived' && (
                                <button
                                  type="button"
                                  onClick={() => void onArchiveScheme(scheme)}
                                  disabled={busy === `archive:${scheme.id}`}
                                  className="flex items-center gap-2 px-3 py-2 text-left text-sm text-navy-700 hover:bg-gray-50 disabled:opacity-50 dark:text-white dark:hover:bg-navy-800"
                                >
                                  归档
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => void onDelete(scheme)}
                                disabled={busy === `delete:${scheme.id}`}
                                className="flex items-center gap-2 px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50 disabled:opacity-50 dark:hover:bg-red-900"
                              >
                                <MdDelete className="h-4 w-4" />
                                删除
                              </button>
                            </>
                          )}
                        </div>
                      </Dropdown>
                    </div>
                  </div>
                </StudioCard>
              );
            })}
          </div>
        </>
      )}

      <StudioCard extra="mt-5">
        <div
          ref={historyRef}
          className="flex scroll-mt-24 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
        >
          <div>
            <h2 className="text-base font-bold text-navy-700 dark:text-white">
              历史版本方案
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              共 {historicalSchemes.length}{' '}
              套。历史户型版本下只允许查看和迁移，不允许新增成果。
            </p>
          </div>
          <Button variant="secondary" onClick={() => setShowHistory((v) => !v)}>
            {showHistory ? '收起历史版本方案' : '查看历史版本方案'}
          </Button>
        </div>
        {showHistory && (
          <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
            {historicalSchemes.length === 0 ? (
              <p className="text-sm text-gray-500">暂无历史版本方案。</p>
            ) : (
              historicalSchemes.map((scheme) => (
                <div
                  key={`${scheme.baseline_version_id}-${scheme.id}`}
                  className="rounded-xl border border-gray-200 p-3 dark:border-white/10"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-bold text-navy-700 dark:text-white">
                        {scheme.name}
                      </p>
                      <p className="mt-1 text-xs text-gray-500">
                        {scheme.id} · 户型 {scheme.baseline_version_id} ·{' '}
                        {statusLabel('scheme', scheme.status)}
                      </p>
                    </div>
                    <LinkButton
                      href={schemeHref(id, 'gallery', scheme.id)}
                      variant="secondary"
                    >
                      查看
                    </LinkButton>
                    {currentBaseline && (
                      <Button
                        variant="primary"
                        onClick={() => void onMigrateScheme(scheme)}
                        disabled={busy === `migrate:${scheme.id}`}
                      >
                        迁移到当前版本
                      </Button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </StudioCard>
    </PageShell>
  );
}
