'use client';

import React, { useEffect, useState } from 'react';
import { useProjectData } from './hooks/useProjectData';
import { useToast } from './hooks/useToast';
import { useGeometryEditor } from './hooks/useGeometryEditor';
import { useFurnitureEditor } from './hooks/useFurnitureEditor';
import GeometryMode from './modes/GeometryMode';
import FurnitureMode from './modes/FurnitureMode';
import { SegmentedControl } from '../ui/buttons';
import { LoadStateBadge, BackendErrorBanner } from '../ui/status';

interface Props {
  projectId: string;
}

type EditorMode = 'geometry' | 'furniture';

// 薄壳: 项目数据 + toast + Tab(几何/家具) + 深链 ?tab + loading/错误 banner,
// 渲染 <GeometryMode>/<FurnitureMode>。全部编辑器 hook 在此恒定调用 (与原
// 单组件一致), 故 Tab 切换不丢各自模式的状态。
export default function FloorplanEditor({ projectId }: Props) {
  const data = useProjectData(projectId);
  const { toast, showToast } = useToast();
  const [mode, setMode] = useState<EditorMode>('geometry');

  const geo = useGeometryEditor({
    projectId,
    G: data.G,
    setG: data.setG,
    gRef: data.gRef,
    derived: data.derived,
    setDerived: data.setDerived,
    showToast,
  });
  const furn = useFurnitureEditor({
    projectId,
    gRef: data.gRef,
    furniture: data.furniture,
    setFurniture: data.setFurniture,
    furnRef: data.furnRef,
    showToast,
  });

  // 初始 Tab 可由 URL 深链指定 (?tab=furniture), 便于直达家具模式 / 自动化截图。
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const tab = new URLSearchParams(window.location.search).get('tab');
    if (tab === 'furniture') setMode('furniture');
  }, []);

  const { G, derived, furniture, loadState, loadError } = data;

  return (
    <div className="w-full">
      <div className="mb-3 flex flex-wrap items-center gap-3 text-sm text-gray-600 dark:text-white">
        <span className="font-semibold">户型 {projectId}</span>
        <LoadStateBadge state={loadState} />
        {mode === 'geometry' && geo.insertMode && (
          <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs text-brand-700">
            {geo.insertMode === 'door' ? '开门模式' : '自由墙模式'}
          </span>
        )}
      </div>

      {/* 模式切换 Tab: 几何 / 家具 */}
      <div className="mb-3">
        <SegmentedControl
          variant="tab"
          options={['geometry', 'furniture'] as const}
          value={mode}
          onChange={(m) => {
            setMode(m);
            furn.resetSelection();
          }}
          renderLabel={(m) => (m === 'geometry' ? '几何' : '家具')}
        />
      </div>

      {loadState === 'error' && <BackendErrorBanner message={loadError} />}

      <div className="flex flex-col gap-4 lg:flex-row">
        {!G ? (
          <div className="min-w-0 flex-1 overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-white/10 dark:bg-navy-800">
            <div className="p-8 text-sm text-gray-400">加载中…</div>
          </div>
        ) : mode === 'geometry' ? (
          <GeometryMode
            geometry={G}
            derived={derived}
            furniture={furniture}
            geo={geo}
          />
        ) : (
          <FurnitureMode geometry={G} derived={derived} furn={furn} />
        )}
      </div>

      {toast && (
        <div className="fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-navy-900 px-4 py-2 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}
