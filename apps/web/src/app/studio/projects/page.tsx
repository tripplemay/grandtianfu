'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Card from 'components/card';
import { SaveButton, DangerButton } from 'components/studio/ui/buttons';
import { TextRow } from 'components/studio/ui/fields';
import { BackendErrorBanner } from 'components/studio/ui/status';
import {
  listProjects,
  createProject,
  deleteProject,
  API_BASE,
  type ProjectSummary,
} from 'lib/studioApi';

// 项目台 (Stage C): GET /api/projects -> Horizon Card 网格。
// 每卡: plan2d 缩略图 + 名 + 房间数 + 打开/删除; 顶部「＋ 新建项目」表单。
// 缩略图直接 <img src=/api/projects/{id}/render?mode=plan2d> (同源 /api, 不开 CORS)。
export default function ProjectsDashboard() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
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
      // 跳转新项目编辑器。
      router.push(`/studio/projects/${encodeURIComponent(created.id)}/editor`);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [newId, newName, router]);

  const onDelete = useCallback(
    async (id: string) => {
      if (!window.confirm(`确认删除项目「${id}」?此操作不可撤销。`)) return;
      try {
        await deleteProject(id);
        await reload();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [reload],
  );

  return (
    <div className="mx-auto w-full max-w-[1400px] px-4 py-6">
      <header className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-navy-700 dark:text-white">
            项目台
          </h1>
          <p className="text-sm text-gray-600 dark:text-gray-300">
            户型项目总览 · 缩略图为 2D 平面派生 · 打开进入几何编辑器。
          </p>
        </div>
        <SaveButton onClick={() => setShowForm((v) => !v)}>
          ＋ 新建项目
        </SaveButton>
      </header>

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
          {formError && (
            <p className="text-xs text-red-500">⛔ {formError}</p>
          )}
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

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {projects.map((p) => (
          <Card
            key={p.id}
            extra="flex flex-col w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10"
          >
            <div className="mb-3 w-full overflow-hidden rounded-xl bg-gray-50 dark:bg-navy-900">
              {/* 缩略图: plan2d 派生 SVG (同源 /api)。 */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`${API_BASE}/projects/${encodeURIComponent(
                  p.id,
                )}/render?mode=plan2d`}
                alt={`${p.name} 平面缩略图`}
                className="h-44 w-full object-contain"
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
              <DangerButton onClick={() => onDelete(p.id)}>删除</DangerButton>
            </div>
          </Card>
        ))}
      </div>

      {projects.length === 0 && !error && (
        <p className="mt-10 text-center text-sm text-gray-400">
          暂无项目,点击右上角「＋ 新建项目」创建。
        </p>
      )}
    </div>
  );
}
