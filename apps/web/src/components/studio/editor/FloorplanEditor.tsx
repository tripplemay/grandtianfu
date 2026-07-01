'use client';

import React, { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { MdUndo, MdRedo } from 'react-icons/md';
import { useProjectData } from './hooks/useProjectData';
import { useToastContext } from '../ui/ToastHost';
import { useGeometryEditor } from './hooks/useGeometryEditor';
import { useFurnitureEditor } from './hooks/useFurnitureEditor';
import { useCommitSignal } from './hooks/useCommitSignal';
import { useEditorHistory } from './hooks/useEditorHistory';
import { useDraftAutosave } from './hooks/useDraftAutosave';
import GeometryMode from './modes/GeometryMode';
import FurnitureMode from './modes/FurnitureMode';
import DraftRecoverBanner from './overlay/DraftRecoverBanner';
import { SegmentedControl } from '../ui/buttons';
import { LoadStateBadge, BackendErrorBanner } from '../ui/status';

interface Props {
  projectId: string;
  schemeId?: string;
  baselineVersionId?: string;
  readOnly?: boolean;
  readOnlyReason?: string;
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
export default function FloorplanEditor({
  projectId,
  schemeId = 'default',
  baselineVersionId,
  readOnly = false,
  readOnlyReason,
}: Props) {
  const data = useProjectData(projectId, schemeId, baselineVersionId);
  const { showToast } = useToastContext();
  const [mode, setMode] = useState<EditorMode>('geometry');
  const [showHelp, setShowHelp] = useState(false);

  // 拖拽提交信号 (历史栈落点入栈): 必须在两个编辑器之前创建, 供其拖拽 down/up 调用。
  const sig = useCommitSignal();

  const geo = useGeometryEditor({
    projectId,
    baselineVersionId,
    readOnly,
    readOnlyReason,
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
    schemeId,
    canSave: data.furnitureLoadState === 'ready' && !readOnly,
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

  // 自动草稿 (阶段 5b / P3): 编辑 debounce 写 localStorage; 载入提示恢复; 保存清草稿。
  const draft = useDraftAutosave({
    projectId,
    schemeId,
    baselineVersionId,
    ready: data.loadState === 'ready',
    G: data.G,
    geoDirty: geo.dirty,
    setG: data.setG,
    gRef: data.gRef,
    furniture: data.furniture,
    furnDirty: furn.dirty,
    setFurniture: data.setFurniture,
    furnRef: data.furnRef,
    onRecoverGeo: () => {
      geo.reDerive();
      geo.markDirty();
    },
    onRecoverFurn: () => furn.markDirty(),
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

      // ? (Shift+/): 打开/关闭快捷键速查 (表单内放行)。
      if (key === '?' && !inForm) {
        e.preventDefault();
        setShowHelp((v) => !v);
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
      {readOnly && (
        <div className="dark:bg-amber-950 mb-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700 dark:border-amber-800 dark:text-amber-200">
          {readOnlyReason || '当前对象只读，不能保存修改。'}
        </div>
      )}
      <div className="mb-3 flex flex-wrap items-center gap-3 text-sm text-gray-600 dark:text-white">
        <span className="font-semibold">户型 {projectId}</span>
        {baselineVersionId ? (
          <span className="font-semibold">户型版本 {baselineVersionId}</span>
        ) : (
          <span className="font-semibold">方案 {schemeId}</span>
        )}
        <LoadStateBadge state={loadState} />
        {!readOnly && (
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => history.undo()}
              disabled={!history.canUndo}
              title="撤销 (Ctrl+Z)"
              aria-label="撤销"
              className="rounded-lg bg-gray-100 p-1.5 text-gray-600 hover:bg-gray-200 disabled:opacity-40 dark:bg-navy-900 dark:text-white"
            >
              <MdUndo className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => history.redo()}
              disabled={!history.canRedo}
              title="重做 (Ctrl+Y)"
              aria-label="重做"
              className="rounded-lg bg-gray-100 p-1.5 text-gray-600 hover:bg-gray-200 disabled:opacity-40 dark:bg-navy-900 dark:text-white"
            >
              <MdRedo className="h-4 w-4" />
            </button>
          </div>
        )}
        <button
          type="button"
          onClick={() => setShowHelp(true)}
          title="快捷键速查 (?)"
          aria-label="快捷键速查"
          className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-bold text-gray-600 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
        >
          ?
        </button>
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
        {/* 承上启下前进 CTA(§7):方案模式→预览/出图;草稿户型→去确认户型 */}
        {!baselineVersionId ? (
          <div className="ml-auto flex items-center gap-2">
            <Link
              href={`/studio/projects/${encodeURIComponent(
                projectId,
              )}/gallery?scheme=${encodeURIComponent(schemeId)}`}
              className="rounded-lg bg-gray-100 px-3 py-1.5 text-xs font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
            >
              方案预览
            </Link>
            <Link
              href={`/studio/projects/${encodeURIComponent(
                projectId,
              )}/render?scheme=${encodeURIComponent(schemeId)}`}
              className="rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-600"
            >
              生成效果图 →
            </Link>
          </div>
        ) : !readOnly ? (
          <Link
            href={`/studio/projects/${encodeURIComponent(
              projectId,
            )}/baseline?version=${encodeURIComponent(baselineVersionId)}`}
            className="ml-auto rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
          >
            完成编辑,去确认户型 →
          </Link>
        ) : null}
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

      {draft.pending && (
        <DraftRecoverBanner
          pending={draft.pending}
          onRecover={draft.recover}
          onDiscard={draft.discard}
        />
      )}

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
            readOnly={readOnly}
          />
        ) : data.furnitureLoadState === 'error' ? (
          <div className="min-w-0 flex-1 rounded-2xl border border-red-200 bg-white p-6 dark:border-red-500/30 dark:bg-navy-800">
            <BackendErrorBanner
              message={`家具加载失败：${
                data.furnitureLoadError || '未知错误'
              }。为避免覆盖远端数据，家具编辑和保存已禁用。`}
            />
            <button
              type="button"
              onClick={() => void data.reloadFurniture()}
              className="mt-4 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600"
            >
              重试加载家具
            </button>
          </div>
        ) : data.furnitureLoadState !== 'ready' ? (
          <div className="min-w-0 flex-1 overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-white/10 dark:bg-navy-800">
            <div className="p-8 text-sm text-gray-400">家具加载中…</div>
          </div>
        ) : (
          <FurnitureMode
            geometry={G}
            derived={derived}
            furn={furn}
            dragging={sig.dragging}
            readOnly={readOnly}
          />
        )}
      </div>

      {showHelp && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="快捷键速查"
          onClick={() => setShowHelp(false)}
          className="bg-black/50 fixed inset-0 z-50 flex items-center justify-center p-6"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl dark:bg-navy-800"
          >
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-base font-bold text-navy-700 dark:text-white">
                键盘快捷键
              </h3>
              <button
                type="button"
                onClick={() => setShowHelp(false)}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                关闭 ✕
              </button>
            </div>
            <dl className="grid grid-cols-1 gap-1.5 text-sm sm:grid-cols-2">
              {[
                ['Ctrl/⌘ + S', '保存'],
                ['Ctrl/⌘ + Z', '撤销'],
                ['Ctrl/⌘ + Shift + Z / Y', '重做'],
                ['Ctrl/⌘ + D', '复制副本'],
                ['Ctrl/⌘ + C / V', '复制 / 粘贴'],
                ['Ctrl/⌘ + A', '全选'],
                ['[ / ]', '家具置底 / 置顶'],
                ['方向键', '微移 1px（Shift 10px）'],
                ['Delete / Backspace', '删除选中'],
                ['Esc', '退出插入 / 清除选择'],
                ['空格 + 拖动', '平移画布'],
                ['Ctrl/⌘ + 滚轮', '缩放画布'],
                ['?', '打开本速查'],
              ].map(([k, v]) => (
                <div
                  key={k}
                  className="flex items-center justify-between gap-3 rounded-lg bg-gray-50 px-3 py-1.5 dark:bg-navy-900"
                >
                  <span className="text-gray-600 dark:text-gray-300">{v}</span>
                  <kbd className="rounded bg-white px-1.5 py-0.5 text-xs font-medium text-navy-700 shadow dark:bg-navy-700 dark:text-white">
                    {k}
                  </kbd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      )}
    </div>
  );
}
