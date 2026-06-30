'use client';

import React, { use, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import Card from 'components/card';
import PageShell from 'components/studio/ui/PageShell';
import EmptyState from 'components/studio/ui/EmptyState';
import LoadingState from 'components/studio/ui/LoadingState';
import RenderImage from 'components/studio/ui/RenderImage';
import { BackendErrorBanner } from 'components/studio/ui/status';
import { useToastContext } from 'components/studio/ui/ToastHost';
import { useConfirm } from 'components/studio/ui/ConfirmDialog';
import {
  adjustScheme,
  archiveScheme,
  confirmScheme,
  createScheme,
  deleteScheme,
  duplicateScheme,
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
} from 'lib/studioApi';
import {
  MdAutoAwesome,
  MdChair,
  MdCompare,
  MdContentCopy,
  MdDelete,
  MdEdit,
  MdImage,
  MdStar,
} from 'react-icons/md';

const SAFE_ID_RE = /^[A-Za-z0-9_-]+$/;
const POLL_MS = 1500;
const TIMEOUT_MS = 90 * 1000;

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
  return `/studio/projects/${encodeURIComponent(projectId)}/${sub}?${params.toString()}`;
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
  const { showToast } = useToastContext();
  const confirm = useConfirm();

  const [schemes, setSchemes] = useState<FurnitureSchemeSummary[]>([]);
  const [baselines, setBaselines] = useState<BaselineMeta[]>([]);
  const [historicalSchemes, setHistoricalSchemes] = useState<
    FurnitureSchemeSummary[]
  >([]);
  const [showHistory, setShowHistory] = useState(false);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [newId, setNewId] = useState('');
  const [newName, setNewName] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');
  const [stylePrompt, setStylePrompt] = useState(
    '现代轻奢,浅色石材,胡桃木,少量墨绿色点缀',
  );
  const [candidateCount, setCandidateCount] = useState(3);
  const [baseSchemeId, setBaseSchemeId] = useState('default');
  const [furnishWarnings, setFurnishWarnings] = useState<string[]>([]);
  const [compareIds, setCompareIds] = useState<string[]>([]);

  const reload = useCallback(async () => {
    try {
      setLoadState('loading');
      const baselineList = await listBaselines(id);
      const current = baselineList.find((b) => b.status === 'confirmed')?.id;
      const list = current ? await listSchemes(id, { baselineVersionId: current }) : [];
      const historicalLists = await Promise.all(
        baselineList
          .filter((b) => b.id !== current)
          .map((b) => listSchemes(id, { baselineVersionId: b.id, includeArchived: true })),
      );
      setBaselines(baselineList);
      setSchemes(list);
      setHistoricalSchemes(historicalLists.flat());
      setError(null);
      setLoadState('ready');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLoadState('error');
    }
  }, [id]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const defaultNewId = useMemo(() => `scheme_manual_${slugTime()}`, []);
  const generating = busy === 'furnish';
  const currentBaseline = baselines.find((b) => b.status === 'confirmed');
  const canCreateSchemes = !!currentBaseline;
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
    const sid = (newId || defaultNewId).trim();
    const name = (newName || '新方案').trim();
    if (!SAFE_ID_RE.test(sid)) {
      showToast('方案 ID 仅允许字母、数字、下划线和短横线', 'error');
      return;
    }
    setBusy('create');
    try {
      await createScheme(id, {
        id: sid,
        name,
        source: 'manual',
        base_scheme_id: 'default',
        furniture: [],
      });
      setNewId('');
      setNewName('');
      showToast('方案已创建', 'success');
      await reload();
    } catch (e) {
      showToast(`创建失败:${e instanceof Error ? e.message : String(e)}`, 'error');
    } finally {
      setBusy(null);
    }
  }, [id, newId, newName, defaultNewId, showToast, reload]);

  const onDuplicate = useCallback(
    async (scheme: FurnitureSchemeSummary) => {
      const sid = `${scheme.id}_copy_${slugTime()}`;
      setBusy(`copy:${scheme.id}`);
      try {
        await duplicateScheme(id, scheme.id, {
          id: sid,
          name: `${scheme.name} 副本`,
        });
        showToast('方案已复制', 'success');
        await reload();
      } catch (e) {
        showToast(`复制失败:${e instanceof Error ? e.message : String(e)}`, 'error');
      } finally {
        setBusy(null);
      }
    },
    [id, showToast, reload],
  );

  const onSaveName = useCallback(async () => {
    if (!editingId || !editingName.trim()) return;
    setBusy(`rename:${editingId}`);
    try {
      await patchScheme(id, editingId, { name: editingName.trim() });
      setEditingId(null);
      setEditingName('');
      showToast('方案已重命名', 'success');
      await reload();
    } catch (e) {
      showToast(`重命名失败:${e instanceof Error ? e.message : String(e)}`, 'error');
    } finally {
      setBusy(null);
    }
  }, [id, editingId, editingName, showToast, reload]);

  const onConfirmScheme = useCallback(
    async (scheme: FurnitureSchemeSummary) => {
      const ok = await confirm({
        title: `确认“${scheme.name}”？`,
        message:
          '确认后方案将锁定为只读。如需调整，系统会复制一套新的草稿方案，原方案不会改变。',
        confirmText: '确认方案',
      });
      if (!ok) return;
      setBusy(`confirm:${scheme.id}`);
      try {
        await confirmScheme(id, scheme.id);
        showToast('方案已确认', 'success');
        await reload();
      } catch (e) {
        showToast(`确认失败:${e instanceof Error ? e.message : String(e)}`, 'error');
      } finally {
        setBusy(null);
      }
    },
    [id, confirm, showToast, reload],
  );

  const onAdjustScheme = useCallback(
    async (scheme: FurnitureSchemeSummary) => {
      const ok = await confirm({
        title: `基于“${scheme.name}”创建调整副本？`,
        message: '系统将复制当前家具布置和风格设置，创建一套新的草稿方案。',
        confirmText: '创建调整副本',
      });
      if (!ok) return;
      setBusy(`adjust:${scheme.id}`);
      try {
        await adjustScheme(id, scheme.id, {
          id: nextSchemeId(`${scheme.id}_adjust`),
          name: `${scheme.name} - 调整版`,
        });
        showToast('调整副本已创建', 'success');
        await reload();
      } catch (e) {
        showToast(`创建失败:${e instanceof Error ? e.message : String(e)}`, 'error');
      } finally {
        setBusy(null);
      }
    },
    [id, confirm, showToast, reload],
  );

  const onSetPreferred = useCallback(
    async (scheme: FurnitureSchemeSummary) => {
      setBusy(`preferred:${scheme.id}`);
      try {
        await setPreferredScheme(id, scheme.id);
        showToast('首选方案已更新', 'success');
        await reload();
      } catch (e) {
        showToast(`设置失败:${e instanceof Error ? e.message : String(e)}`, 'error');
      } finally {
        setBusy(null);
      }
    },
    [id, showToast, reload],
  );

  const onArchiveScheme = useCallback(
    async (scheme: FurnitureSchemeSummary) => {
      const ok = await confirm({
        title: `归档“${scheme.name}”？`,
        message: '归档后默认列表不再显示该方案，已有成果文件不会删除。',
        confirmText: '归档',
        danger: true,
      });
      if (!ok) return;
      setBusy(`archive:${scheme.id}`);
      try {
        await archiveScheme(id, scheme.id);
        showToast('方案已归档', 'success');
        await reload();
      } catch (e) {
        showToast(`归档失败:${e instanceof Error ? e.message : String(e)}`, 'error');
      } finally {
        setBusy(null);
      }
    },
    [id, confirm, showToast, reload],
  );

  const onMigrateScheme = useCallback(
    async (scheme: FurnitureSchemeSummary) => {
      if (!currentBaseline) return;
      setBusy(`migrate:${scheme.id}`);
      try {
        await migrateScheme(id, scheme.id, {
          target_baseline_version_id: currentBaseline.id,
          id: nextSchemeId(`${scheme.id}_migrated`),
          name: `${scheme.name} - ${currentBaseline.id}`,
        });
        showToast('方案已迁移为当前户型草稿方案', 'success');
        await reload();
      } catch (e) {
        showToast(`迁移失败:${e instanceof Error ? e.message : String(e)}`, 'error');
      } finally {
        setBusy(null);
      }
    },
    [id, currentBaseline, showToast, reload],
  );

  const onDelete = useCallback(
    async (scheme: FurnitureSchemeSummary) => {
      if (scheme.id === 'default') return;
      const ok = await confirm({
        title: '删除候选方案',
        message: `将删除「${scheme.name}」。此操作会移入回收站,不会删除已生成图片文件。`,
        confirmText: '删除',
        danger: true,
      });
      if (!ok) return;
      setBusy(`delete:${scheme.id}`);
      try {
        await deleteScheme(id, scheme.id);
        showToast('方案已删除', 'success');
        await reload();
      } catch (e) {
        showToast(`删除失败:${e instanceof Error ? e.message : String(e)}`, 'error');
      } finally {
        setBusy(null);
      }
    },
    [id, confirm, showToast, reload],
  );

  const onGenerate = useCallback(async () => {
    if (!stylePrompt.trim()) {
      showToast('请输入风格意向', 'error');
      return;
    }
    setBusy('furnish');
    setFurnishWarnings([]);
    try {
      const { job_id } = await startFurnish(id, {
        style_prompt: stylePrompt.trim(),
        count: candidateCount,
        base_scheme_id: baseSchemeId || 'default',
      });
      const started = Date.now();
      // eslint-disable-next-line no-constant-condition
      while (true) {
        await sleep(POLL_MS);
        const job = await pollJob<FurnishResult>(job_id);
        if (job.status === 'done' && job.result) {
          setFurnishWarnings(job.result.warnings || []);
          showToast(`已生成 ${job.result.schemes.length} 套候选方案`, 'success');
          await reload();
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
      showToast(`生成失败:${e instanceof Error ? e.message : String(e)}`, 'error');
    } finally {
      setBusy(null);
    }
  }, [
    id,
    stylePrompt,
    candidateCount,
    baseSchemeId,
    showToast,
    reload,
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
      <button
        type="button"
        onClick={() => void reload()}
        className="rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white dark:hover:bg-navy-700"
      >
        刷新
      </button>
    </>
  );

  return (
    <PageShell
      title="方案中心"
      description={`默认展示户型 ${currentBaseline?.id ?? 'v1'} 下未归档方案。历史版本方案不混入当前列表。`}
      actions={actions}
      state={loadState === 'loading' ? <LoadingState rows={2} /> : undefined}
    >
      {error && <BackendErrorBanner message={error} />}

      <Card extra="mb-5 w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10">
        <div className="mb-3 flex items-center gap-2">
          <MdAutoAwesome className="h-5 w-5 text-brand-500" />
          <h2 className="text-base font-bold text-navy-700 dark:text-white">
            AI 生成候选方案
          </h2>
        </div>
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_160px_180px_auto]">
          <textarea
            value={stylePrompt}
            onChange={(e) => setStylePrompt(e.target.value)}
            rows={3}
            placeholder="描述风格、材质、色彩偏好"
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
              value={baseSchemeId}
              onChange={(e) => setBaseSchemeId(e.target.value)}
              disabled={!canCreateSchemes}
              className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-navy-700 outline-none focus:border-brand-500 dark:border-white/10 dark:bg-navy-900 dark:text-white"
            >
              {schemes.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={onGenerate}
            disabled={generating || loadState !== 'ready' || !canCreateSchemes}
            className="self-end rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {generating ? '生成中…' : '生成候选'}
          </button>
        </div>
        {furnishWarnings.length > 0 && (
          <div className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-700 dark:bg-amber-950 dark:text-amber-200">
            {furnishWarnings.map((w, i) => (
              <p key={`${w}-${i}`}>{w}</p>
            ))}
          </div>
        )}
      </Card>

      <Card extra="mb-5 w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10">
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
          <input
            value={newId}
            onChange={(e) => setNewId(e.target.value)}
            placeholder={defaultNewId}
            className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-navy-700 outline-none focus:border-brand-500 dark:border-white/10 dark:bg-navy-900 dark:text-white"
          />
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="方案名称"
            className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-navy-700 outline-none focus:border-brand-500 dark:border-white/10 dark:bg-navy-900 dark:text-white"
          />
          <button
            type="button"
            onClick={onCreate}
            disabled={busy === 'create' || !canCreateSchemes}
            className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {busy === 'create' ? '创建中…' : '创建空方案'}
          </button>
        </div>
      </Card>

      {loadState === 'ready' && !canCreateSchemes ? (
        <EmptyState
          icon={<MdChair className="h-6 w-6" />}
          title="请先确认户型"
          description="当前项目还没有已确认户型版本，确认户型后才能创建软装方案。"
          action={
            <Link
              href={`/studio/projects/${encodeURIComponent(id)}/baseline`}
              className="rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
            >
              去确认户型
            </Link>
          }
        />
      ) : loadState === 'ready' && schemes.length === 0 ? (
        <EmptyState
          icon={<MdChair className="h-6 w-6" />}
          title="暂无方案"
          description="创建一个空方案或等待 AI 摆家具生成候选方案。"
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {schemes.map((scheme) => {
            const isEditing = editingId === scheme.id;
            const isDefault = scheme.id === 'default';
            return (
              <Card
                key={scheme.id}
                extra="w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10"
              >
                <div className="flex flex-col gap-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        {isEditing ? (
                          <input
                            value={editingName}
                            onChange={(e) => setEditingName(e.target.value)}
                            className="min-w-[180px] rounded-lg border border-gray-200 px-3 py-1.5 text-sm font-bold text-navy-700 outline-none focus:border-brand-500 dark:border-white/10 dark:bg-navy-900 dark:text-white"
                          />
                        ) : (
                          <h2 className="break-words text-lg font-bold text-navy-700 dark:text-white">
                            {scheme.name}
                          </h2>
                        )}
                        {isDefault && (
                          <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                            初始方案
                          </span>
                        )}
                        {scheme.preferred && (
                          <span className="inline-flex items-center gap-1 rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                            <MdStar className="h-3 w-3" />
                            首选
                          </span>
                        )}
                      </div>
                      <p className="mt-1 break-all text-xs text-gray-500 dark:text-gray-400">
                        {isDefault ? '初始方案' : scheme.id} · 户型 {scheme.baseline_version_id ?? 'v1'}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {isEditing ? (
                        <>
                          <button
                            type="button"
                            onClick={onSaveName}
                            disabled={busy === `rename:${scheme.id}`}
                            className="rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-600 disabled:opacity-50"
                          >
                            保存
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingId(null)}
                            className="rounded-lg bg-gray-100 px-3 py-1.5 text-xs font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
                          >
                            取消
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          onClick={() => {
                            setEditingId(scheme.id);
                            setEditingName(scheme.name);
                          }}
                          disabled={scheme.status !== 'draft'}
                          className="rounded-lg bg-gray-100 px-3 py-1.5 text-xs font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
                        >
                          重命名
                        </button>
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
                      <p className="font-bold text-navy-700 dark:text-white">
                        {scheme.status}
                      </p>
                    </div>
                  </div>

                  <div className="rounded-xl bg-gray-50 p-3 dark:bg-navy-900">
                    {scheme.latest_render_url ? (
                      <RenderImage
                        src={scheme.latest_render_url}
                        alt={`${scheme.name} 最新成果`}
                        className="h-36"
                        imgClassName="h-36 w-full object-cover"
                        fallbackLabel="最新成果加载失败"
                      />
                    ) : (
                      <p className="text-sm text-gray-500">暂无最新成果缩略图</p>
                    )}
                    <p className="mt-2 text-xs text-gray-500">
                      风格意向：{scheme.style_prompt || '未填写'}
                    </p>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => toggleCompare(scheme.id)}
                      disabled={
                        !compareIds.includes(scheme.id) && compareIds.length >= 3
                      }
                      className={`inline-flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium disabled:opacity-50 ${
                        compareIds.includes(scheme.id)
                          ? 'bg-brand-500 text-white hover:bg-brand-600'
                          : 'bg-gray-100 text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white'
                      }`}
                    >
                      <MdCompare className="h-4 w-4" />
                      {compareIds.includes(scheme.id) ? '已选对比' : '对比勾选'}
                    </button>
                    <Link
                      href={schemeHref(id, 'editor', scheme.id)}
                      className={`inline-flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium ${
                        scheme.status === 'confirmed'
                          ? 'bg-gray-100 text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white'
                          : 'bg-brand-500 text-white hover:bg-brand-600'
                      }`}
                    >
                      <MdEdit className="h-4 w-4" />
                      {scheme.status === 'confirmed' ? '查看' : '编辑'}
                    </Link>
                    <Link
                      href={schemeHref(
                        id,
                        'gallery',
                        scheme.id,
                        scheme.baseline_version_id,
                      )}
                      className="inline-flex items-center gap-1 rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
                    >
                      <MdImage className="h-4 w-4" />
                      画廊
                    </Link>
                    <Link
                      href={schemeHref(id, 'render', scheme.id)}
                      className="inline-flex items-center gap-1 rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
                    >
                      <MdChair className="h-4 w-4" />
                      效果图
                    </Link>
                    {scheme.status === 'draft' && (
                      <button
                        type="button"
                        onClick={() => void onConfirmScheme(scheme)}
                        disabled={busy === `confirm:${scheme.id}`}
                        className="inline-flex items-center gap-1 rounded-lg bg-green-50 px-3 py-2 text-sm font-medium text-green-700 hover:bg-green-100 disabled:opacity-50"
                      >
                        确认
                      </button>
                    )}
                    {scheme.status === 'confirmed' && (
                      <button
                        type="button"
                        onClick={() => void onAdjustScheme(scheme)}
                        disabled={busy === `adjust:${scheme.id}`}
                        className="inline-flex items-center gap-1 rounded-lg bg-brand-50 px-3 py-2 text-sm font-medium text-brand-500 hover:bg-brand-100 disabled:opacity-50"
                      >
                        继续调整
                      </button>
                    )}
                    {!scheme.preferred && (
                      <button
                        type="button"
                        onClick={() => void onSetPreferred(scheme)}
                        disabled={busy === `preferred:${scheme.id}`}
                        className="inline-flex items-center gap-1 rounded-lg bg-amber-50 px-3 py-2 text-sm font-medium text-amber-700 hover:bg-amber-100 disabled:opacity-50"
                      >
                        <MdStar className="h-4 w-4" />
                        设为首选
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => void onDuplicate(scheme)}
                      disabled={busy === `copy:${scheme.id}` || scheme.status === 'archived'}
                      className="inline-flex items-center gap-1 rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 disabled:opacity-50 dark:bg-navy-900 dark:text-white"
                    >
                      <MdContentCopy className="h-4 w-4" />
                      复制
                    </button>
                    {!isDefault && (
                      <>
                        <button
                          type="button"
                          onClick={() => void onArchiveScheme(scheme)}
                          disabled={busy === `archive:${scheme.id}`}
                          className="inline-flex items-center gap-1 rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 disabled:opacity-50 dark:bg-navy-900 dark:text-white"
                        >
                          归档
                        </button>
                        <button
                          type="button"
                          onClick={() => void onDelete(scheme)}
                          disabled={busy === `delete:${scheme.id}`}
                          className="inline-flex items-center gap-1 rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50 dark:bg-red-950"
                        >
                          <MdDelete className="h-4 w-4" />
                          删除
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <Card extra="mt-5 w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-base font-bold text-navy-700 dark:text-white">
              历史版本方案
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              共 {historicalSchemes.length} 套。历史户型版本下只允许查看和迁移，不允许新增成果。
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowHistory((v) => !v)}
            className="rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
          >
            {showHistory ? '收起历史版本方案' : '查看历史版本方案'}
          </button>
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
                        {scheme.id} · 户型 {scheme.baseline_version_id} · {scheme.status}
                      </p>
                    </div>
                    <Link
                      href={schemeHref(id, 'gallery', scheme.id)}
                      className="rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
                    >
                      查看
                    </Link>
                    {currentBaseline && (
                      <button
                        type="button"
                        onClick={() => void onMigrateScheme(scheme)}
                        disabled={busy === `migrate:${scheme.id}`}
                        className="rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
                      >
                        迁移到当前版本
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </Card>
    </PageShell>
  );
}
