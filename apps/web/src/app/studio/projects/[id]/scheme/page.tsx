'use client';

import React, { use, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import Card from 'components/card';
import PageShell from 'components/studio/ui/PageShell';
import EmptyState from 'components/studio/ui/EmptyState';
import LoadingState from 'components/studio/ui/LoadingState';
import { BackendErrorBanner } from 'components/studio/ui/status';
import { useToastContext } from 'components/studio/ui/ToastHost';
import { useConfirm } from 'components/studio/ui/ConfirmDialog';
import {
  createScheme,
  deleteScheme,
  duplicateScheme,
  listSchemes,
  patchScheme,
  pollJob,
  startFurnish,
  type FurnishResult,
  type FurnitureSchemeSummary,
} from 'lib/studioApi';
import {
  MdAutoAwesome,
  MdChair,
  MdContentCopy,
  MdDelete,
  MdEdit,
  MdImage,
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

function schemeHref(projectId: string, sub: 'editor' | 'gallery' | 'render', schemeId: string) {
  return `/studio/projects/${encodeURIComponent(projectId)}/${sub}?scheme=${encodeURIComponent(
    schemeId,
  )}`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
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

  const reload = useCallback(async () => {
    try {
      setLoadState('loading');
      const list = await listSchemes(id);
      setSchemes(list);
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
    <button
      type="button"
      onClick={() => void reload()}
      className="rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white dark:hover:bg-navy-700"
    >
      刷新
    </button>
  );

  return (
    <PageShell
      title="软装方案"
      description={`户型 ${id} 的候选家具方案。选择任一方案继续编辑、画廊或 AI 效果图。`}
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
            disabled={generating || loadState !== 'ready'}
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
            disabled={busy === 'create'}
            className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {busy === 'create' ? '创建中…' : '创建空方案'}
          </button>
        </div>
      </Card>

      {loadState === 'ready' && schemes.length === 0 ? (
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
                            default
                          </span>
                        )}
                      </div>
                      <p className="mt-1 break-all text-xs text-gray-500 dark:text-gray-400">
                        {scheme.id}
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

                  <div className="flex flex-wrap gap-2">
                    <Link
                      href={schemeHref(id, 'editor', scheme.id)}
                      className="inline-flex items-center gap-1 rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
                    >
                      <MdEdit className="h-4 w-4" />
                      编辑
                    </Link>
                    <Link
                      href={schemeHref(id, 'gallery', scheme.id)}
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
                    <button
                      type="button"
                      onClick={() => void onDuplicate(scheme)}
                      disabled={busy === `copy:${scheme.id}`}
                      className="inline-flex items-center gap-1 rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 disabled:opacity-50 dark:bg-navy-900 dark:text-white"
                    >
                      <MdContentCopy className="h-4 w-4" />
                      复制
                    </button>
                    {!isDefault && (
                      <button
                        type="button"
                        onClick={() => void onDelete(scheme)}
                        disabled={busy === `delete:${scheme.id}`}
                        className="inline-flex items-center gap-1 rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50 dark:bg-red-950"
                      >
                        <MdDelete className="h-4 w-4" />
                        删除
                      </button>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </PageShell>
  );
}
