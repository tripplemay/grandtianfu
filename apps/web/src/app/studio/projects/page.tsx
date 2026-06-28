'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Card from 'components/card';
import { SaveButton } from 'components/studio/ui/buttons';
import { TextRow } from 'components/studio/ui/fields';
import { BackendErrorBanner } from 'components/studio/ui/status';
import PageShell from 'components/studio/ui/PageShell';
import LoadingState from 'components/studio/ui/LoadingState';
import EmptyState from 'components/studio/ui/EmptyState';
import RenderImage from 'components/studio/ui/RenderImage';
import { useConfirm } from 'components/studio/ui/ConfirmDialog';
import { useToastContext } from 'components/studio/ui/ToastHost';
import {
  listProjects,
  createProject,
  deleteProject,
  API_BASE,
  type ProjectSummary,
} from 'lib/studioApi';

// 项目台 (Stage C): GET /api/projects -> Horizon Card 网格。
// 每卡: plan2d 缩略图 (RenderImage 骨架+兜底) + 名 + 房间数 + 打开/删除; 顶部「＋ 新建项目」表单。
// Phase 3: 删除走 ConfirmDialog、操作走壳级 toast、缩略图走 RenderImage、空/载用 EmptyState/LoadingState。
export default function ProjectsDashboard() {
  const router = useRouter();
  const confirm = useConfirm();
  const { showToast } = useToastContext();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [newId, setNewId] = useState('');
  const [newName, setNewName] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      const list = await listProjects();
      setProjects(list);
      setError(null);
      setLoadState('ready');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLoadState('error');
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const onCreate = useCallback(async () => {
    const id = newId.trim();
    const name = newName.trim();
    if (!/^[A-Za-z0-9_-]+$/.test(id)) {
      setFormError('id 仅允许字母 / 数字 / - / _,且不能为空');
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      const created = await createProject(id, name || id);
      setShowForm(false);
      setNewId('');
      setNewName('');
      showToast(`已创建项目「${created.name}」`, 'success');
      router.push(`/studio/projects/${encodeURIComponent(created.id)}/editor`);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [newId, newName, router, showToast]);

  const onDelete = useCallback(
    async (id: string) => {
      const ok = await confirm({
        title: `删除项目「${id}」?`,
        message: '此操作不可撤销,项目几何与家具数据将一并移除。',
        confirmText: '删除',
        cancelText: '取消',
        danger: true,
      });
      if (!ok) return;
      try {
        await deleteProject(id);
        showToast(`已删除项目「${id}」`, 'success');
        await reload();
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        showToast(`删除失败:${msg}`, 'error');
      }
    },
    [confirm, reload, showToast],
  );

  const actions = (
    <SaveButton onClick={() => setShowForm((v) => !v)}>＋ 新建项目</SaveButton>
  );

  return (
    <PageShell
      title="项目台"
      description="户型项目总览 · 缩略图为 2D 平面派生 · 打开进入几何编辑器。"
      actions={actions}
      state={loadState === 'loading' ? <LoadingState rows={2} /> : undefined}
    >
      {error && <BackendErrorBanner message={error} />}

      {showForm && (
        <Card extra="mb-6 max-w-[520px] gap-3 border border-gray-200 p-4 !shadow-none dark:border-white/10">
          <h2 className="text-base font-bold text-navy-700 dark:text-white">
            新建项目
          </h2>
          <TextRow
            label="项目 id(字母/数字/-/_)"
            value={newId}
            onChange={setNewId}
            placeholder="例如 E 或 demo_1"
          />
          <TextRow
            label="项目名(可选,默认同 id)"
            value={newName}
            onChange={setNewName}
            placeholder="例如 阅天府E户型"
          />
          {formError && <p className="text-xs text-red-500">⛔ {formError}</p>}
          <div className="flex gap-2">
            <SaveButton onClick={onCreate} disabled={busy}>
              {busy ? '创建中…' : '创建并进入编辑器'}
            </SaveButton>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
            >
              取消
            </button>
          </div>
        </Card>
      )}

      {projects.length > 0 ? (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {projects.map((p) => (
            <Card
              key={p.id}
              extra="flex flex-col w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10"
            >
              <div className="mb-3 w-full overflow-hidden rounded-xl bg-gray-50 dark:bg-navy-900">
                <RenderImage
                  src={`${API_BASE}/projects/${encodeURIComponent(
                    p.id,
                  )}/render?mode=plan2d`}
                  alt={`${p.name} 平面缩略图`}
                  className="h-44"
                  imgClassName="h-44 w-full object-contain"
                  fallbackLabel="平面图加载失败"
                />
              </div>
              <div className="mb-3">
                <p className="text-lg font-bold text-navy-700 dark:text-white">
                  {p.name}
                </p>
                <p className="mt-1 text-sm font-medium text-gray-600 dark:text-gray-300">
                  房间数 {p.rooms} · id: {p.id}
                </p>
              </div>
              <div className="mt-auto flex items-center justify-between">
                <SaveButton
                  onClick={() =>
                    router.push(
                      `/studio/projects/${encodeURIComponent(p.id)}/editor`,
                    )
                  }
                >
                  打开
                </SaveButton>
                <button
                  type="button"
                  onClick={() => onDelete(p.id)}
                  title="删除项目"
                  className="rounded-lg px-2 py-1.5 text-sm font-medium text-gray-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-500/10"
                >
                  删除
                </button>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        loadState === 'ready' &&
        !error && (
          <EmptyState
            icon={<span>🏠</span>}
            title="暂无项目"
            description="点击右上角「＋ 新建项目」,从一个户型 id 开始创建你的第一个工作区。"
            action={
              <SaveButton onClick={() => setShowForm(true)}>
                ＋ 新建项目
              </SaveButton>
            }
          />
        )
      )}
    </PageShell>
  );
}
