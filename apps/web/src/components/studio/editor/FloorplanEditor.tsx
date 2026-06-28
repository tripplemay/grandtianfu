'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useProjectData } from './hooks/useProjectData';
import { useToastContext } from '../ui/ToastHost';
import { useGeometryEditor } from './hooks/useGeometryEditor';
import { useFurnitureEditor } from './hooks/useFurnitureEditor';
import { useCommitSignal } from './hooks/useCommitSignal';
import { useEditorHistory } from './hooks/useEditorHistory';
import GeometryMode from './modes/GeometryMode';
import FurnitureMode from './modes/FurnitureMode';
import { SegmentedControl } from '../ui/buttons';
import { LoadStateBadge, BackendErrorBanner } from '../ui/status';

interface Props {
  projectId: string;
}

type EditorMode = 'geometry' | 'furniture';

// 聚焦于表单元素时不拦截 Delete/方向键 (让输入正常); Ctrl+Z/Y 在表单内也放行给浏览器
// (输入框原生 undo)。Ctrl+S 始终拦截 (阻止浏览器保存)。
function isFormEl(el: EventTarget | null): boolean {
  const t = el as HTMLElement | null;
  if (!t) return false;
  const tag = t.tagName;
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    t.isContentEditable
  );
}

// 薄壳: 项目数据 + toast + Tab(几何/家具) + 深链 ?tab + loading/错误 banner +
// 阶段 2 安全网 (undo/redo 共栈 / 全局键盘层 / 防丢失 dirty+beforeunload)。
// 全部编辑器 hook 在此恒定调用 (与原单组件一致), 故 Tab 切换不丢各自模式的状态。
export default function FloorplanEditor({ projectId }: Props) {
  const data = useProjectData(projectId);
  const { showToast } = useToastContext();
  const [mode, setMode] = useState<EditorMode>('geometry');

  // 拖拽提交信号 (历史栈落点入栈): 必须在两个编辑器之前创建, 供其拖拽 down/up 调用。
  const sig = useCommitSignal();

  const geo = useGeometryEditor({
    projectId,
    G: data.G,
    setG: data.setG,
    gRef: data.gRef,
    derived: data.derived,
    setDerived: data.setDerived,
    showToast,
    beginDrag: sig.beginDrag,
    endDrag: sig.endDrag,
  });
  const furn = useFurnitureEditor({
    projectId,
    gRef: data.gRef,
    furniture: data.furniture,
    setFurniture: data.setFurniture,
    furnRef: data.furnRef,
    showToast,
    beginDrag: sig.beginDrag,
    endDrag: sig.endDrag,
  });

  // undo/redo 共栈 (几何 G + 家具 items 同一历史)。还原后重派生 + 置脏。
  const history = useEditorHistory({
    ready: data.loadState === 'ready',
    G: data.G,
    setG: data.setG,
    gRef: data.gRef,
    furniture: data.furniture,
    setFurniture: data.setFurniture,
    furnRef: data.furnRef,
    geoSel: geo.selection,
    setGeoSel: geo.setSelection,
    furnSel: furn.selectedIds,
    setFurnSel: furn.setSelectedIds,
    draggingRef: sig.draggingRef,
    tick: sig.tick,
    onAfterApply: (gChanged, fChanged) => {
      // 仅对实际变化的域重派生 / 置脏: 家具-only undo 不触碰几何 (避免误标几何脏,
      // 且省去无意义的 /derive); GEOM_READONLY 下几何脏无法清除, 故尤需精确。
      if (gChanged) {
        geo.reDerive();
        geo.markDirty();
      }
      if (fChanged) furn.markDirty();
    },
  });

  // 初始 Tab 可由 URL 深链指定 (?tab=furniture)。
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const tab = new URLSearchParams(window.location.search).get('tab');
    if (tab === 'furniture') setMode('furniture');
  }, []);

  // ---- 全局键盘层 (P1-3 / P2-4): refs 持最新态, 监听器稳定不重绑 ---- //
  const kbdRef = useRef({ mode, geo, furn, history });
  kbdRef.current = { mode, geo, furn, history };

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onKeyDown = (e: KeyboardEvent) => {
      const { mode: m, geo: g, furn: f, history: h } = kbdRef.current;
      const inForm = isFormEl(document.activeElement);
      const ctrl = e.ctrlKey || e.metaKey;
      const key = e.key;

      // Ctrl+S: 始终拦截 (阻止浏览器保存); 按当前 mode 保存。
      if (ctrl && (key === 's' || key === 'S')) {
        e.preventDefault();
        if (m === 'geometry') g.onSave();
        else f.onSaveFurn();
        return;
      }

      // Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y: undo/redo (表单内放行给浏览器原生 undo)。
      if (ctrl && (key === 'z' || key === 'Z')) {
        if (inForm) return;
        e.preventDefault();
        if (e.shiftKey) h.redo();
        else h.undo();
        return;
      }
      if (ctrl && (key === 'y' || key === 'Y')) {
        if (inForm) return;
        e.preventDefault();
        h.redo();
        return;
      }

      // Ctrl+D 复制副本 / Ctrl+C 复制 / Ctrl+V 粘贴 (表单内放行)。
      if (ctrl && (key === 'd' || key === 'D')) {
        if (inForm) return;
        e.preventDefault();
        if (m === 'geometry') g.duplicateSelected();
        else f.duplicateSelected();
        return;
      }
      if (ctrl && (key === 'c' || key === 'C')) {
        if (inForm) return;
        if (m === 'geometry') g.copySelected();
        else f.copySelected();
        return;
      }
      if (ctrl && (key === 'v' || key === 'V')) {
        if (inForm) return;
        if (m === 'geometry') g.paste();
        else f.paste();
        return;
      }

      // Ctrl+A 全选当前模式可选对象 (P2-7, 表单内放行给浏览器原生全选)。
      if (ctrl && (key === 'a' || key === 'A')) {
        if (inForm) return;
        e.preventDefault();
        if (m === 'geometry') g.selectAll();
        else f.selectAll();
        return;
      }

      // 家具 z-order 快捷 (P2-13): ] 置顶 / [ 置底 (表单内放行)。
      if ((key === ']' || key === '[') && m === 'furniture') {
        if (inForm) return;
        e.preventDefault();
        if (key === ']') f.bringToFront();
        else f.sendToBack();
        return;
      }

      // Esc: 退出插入模式 / 清选 (表单内让其失焦, 不额外处理)。
      if (key === 'Escape') {
        if (inForm) return;
        if (m === 'geometry') g.onEscape();
        else f.clearSelection();
        return;
      }

      // 以下涉及 Delete/方向键: 表单聚焦时一律放行 (守卫)。
      if (inForm) return;

      if (key === 'Delete' || key === 'Backspace') {
        e.preventDefault();
        if (m === 'geometry') g.deleteSelected();
        else f.onDelFurn();
        return;
      }

      if (
        key === 'ArrowUp' ||
        key === 'ArrowDown' ||
        key === 'ArrowLeft' ||
        key === 'ArrowRight'
      ) {
        const step = e.shiftKey ? 10 : 1;
        let dx = 0;
        let dy = 0;
        if (key === 'ArrowUp') dy = -step;
        else if (key === 'ArrowDown') dy = step;
        else if (key === 'ArrowLeft') dx = -step;
        else dx = step;
        e.preventDefault();
        if (m === 'geometry') g.nudge(dx, dy);
        else f.nudge(dx, dy);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  // ---- 防丢失 (P1-6): 脏时拦截卸载 ---- //
  const dirty = geo.dirty || furn.dirty;
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [dirty]);

  const { G, derived, furniture, loadState, loadError } = data;

  return (
    <div className="w-full">
      <div className="mb-3 flex flex-wrap items-center gap-3 text-sm text-gray-600 dark:text-white">
        <span className="font-semibold">户型 {projectId}</span>
        <LoadStateBadge state={loadState} />
        {mode === 'geometry' && geo.insertMode && (
          <span
            data-testid="insert-mode-badge"
            className="rounded-full bg-brand-100 px-2 py-0.5 text-xs text-brand-700"
          >
            {geo.insertMode === 'door'
              ? '开门模式'
              : geo.insertMode === 'freewall'
              ? '自由墙模式'
              : '＋房间模式'}
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
            dragging={sig.dragging}
          />
        ) : (
          <FurnitureMode
            geometry={G}
            derived={derived}
            furn={furn}
            dragging={sig.dragging}
          />
        )}
      </div>
    </div>
  );
}
