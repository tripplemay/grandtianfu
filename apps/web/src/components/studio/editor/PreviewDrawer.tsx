'use client';

import React, { useMemo, useState } from 'react';
import { HiX } from 'react-icons/hi';
import { API_BASE } from 'lib/studioApi';
import { SegmentedControl } from '../ui/buttons';
import RenderImage from '../ui/RenderImage';

// 编辑器内预览抽屉 (升级计划 P1): 不跳页直接看 平面/轴测 渲染。
// 预览 = 已保存状态 (走 GET render 端点); 时间戳破缓存, 打开/保存后刷新。

export default function PreviewDrawer({
  projectId,
  schemeId,
  open,
  onClose,
  dirty,
  refreshKey,
}: {
  projectId: string;
  schemeId: string;
  open: boolean;
  onClose: () => void;
  dirty?: boolean;
  refreshKey?: number; // 保存成功后由父组件递增, 触发重取
}) {
  const [mode, setMode] = useState<'photo' | 'plan2d'>('photo');
  const src = useMemo(() => {
    const base =
      schemeId && schemeId !== 'default'
        ? `${API_BASE}/projects/${encodeURIComponent(
            projectId,
          )}/schemes/${encodeURIComponent(schemeId)}/render`
        : `${API_BASE}/projects/${encodeURIComponent(projectId)}/render`;
    return `${base}?mode=${mode}&t=${refreshKey ?? 0}`;
  }, [projectId, schemeId, mode, refreshKey]);

  if (!open) return null;
  return (
    <div className="fixed inset-y-0 right-0 z-[60] flex w-full max-w-xl flex-col border-l border-gray-200 bg-white shadow-2xl dark:border-white/10 dark:bg-navy-800">
      <div className="flex items-center justify-between gap-2 border-b border-gray-100 p-3 dark:border-white/5">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-bold text-navy-700 dark:text-white">
            方案预览
          </h3>
          <SegmentedControl
            variant="tab"
            value={mode}
            onChange={(v) => setMode(v)}
            options={['photo', 'plan2d'] as const}
            renderLabel={(v) => (v === 'photo' ? '轴测' : '平面')}
          />
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-navy-700"
          aria-label="关闭预览"
        >
          <HiX className="h-5 w-5" />
        </button>
      </div>
      <div className="min-h-0 flex-1 bg-gray-50 p-3 dark:bg-navy-900">
        <RenderImage
          src={src}
          alt={`${projectId} ${schemeId} ${mode} 预览`}
          className="h-full"
          imgClassName="h-full w-full object-contain"
          fallbackLabel="预览加载失败"
        />
      </div>
      <p className="border-t border-gray-100 p-2 text-center text-xs text-gray-400 dark:border-white/5">
        {dirty
          ? '⚠ 有未保存修改:预览显示的是已保存状态,保存后自动刷新。'
          : '预览 = 已保存状态,保存后自动刷新。'}
      </p>
    </div>
  );
}
