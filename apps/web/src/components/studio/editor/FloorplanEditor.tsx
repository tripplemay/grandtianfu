'use client';

import React, { useEffect, useRef, useState } from 'react';
import { MdUndo, MdRedo, MdHelpOutline, MdImage } from 'react-icons/md';
import { useProjectData } from './hooks/useProjectData';
import { useToastContext } from '../ui/ToastHost';
import { useGeometryEditor } from './hooks/useGeometryEditor';
import { useFurnitureEditor } from './hooks/useFurnitureEditor';
import { useCommitSignal } from './hooks/useCommitSignal';
import { useEditorHistory } from './hooks/useEditorHistory';
import { useDraftAutosave } from './hooks/useDraftAutosave';
import GeometryMode from './modes/GeometryMode';
import PreviewDrawer from './PreviewDrawer';
import { computeFitVp, type ViewportState } from './hooks/useViewport';
import { readOrigin, readViewBox } from 'lib/floorplan/coords';
import { roomsContentBBox } from 'lib/floorplan/geometry';
import FurnitureMode from './modes/FurnitureMode';
import DraftRecoverBanner from './overlay/DraftRecoverBanner';
import {
  SegmentedControl,
  Button,
  LinkButton,
  IconButton,
} from '../ui/buttons';
import {
  LoadStateBadge,
  BackendErrorBanner,
  NoticeBanner,
  Badge,
} from '../ui/status';
import Modal from '../ui/Modal';

interface Props {
  projectId: string;
  schemeId?: string;
  baselineVersionId?: string;
  readOnly?: boolean;
  readOnlyReason?: string;
  // 仅几何页只读 (CP5v3): 版本管理项目的方案上下文 —— 家具可编辑, 几何只读+指引
  // (旧根几何写接口已被后端 409 封禁, 不再提供注定失败的编辑入口)。
  geometryReadOnly?: boolean;
  geometryReadOnlyReason?: string;
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
  geometryReadOnly = false,
  geometryReadOnlyReason,
}: Props) {
  const data = useProjectData(projectId, schemeId, baselineVersionId);
  const { showToast } = useToastContext();
  const [mode, setMode] = useState<EditorMode>('geometry');
  const [showHelp, setShowHelp] = useState(false);
  // 编辑器内预览 (P1): 抽屉 + 保存成功计数作为破缓存刷新 key。
  const [showPreview, setShowPreview] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);
  // 换件不挪位 (Phase B): 方案模式默认锁位 (布局继承自基线, 主操作=换件/调风格);
  // 户型基线草稿模式是布局作者本身, 默认解锁。工具条可切换。
  const [posLocked, setPosLocked] = useState(!baselineVersionId);

  // 几何页有效只读 (CP5v3): 页面级只读 或 仅几何只读; 家具页只看页面级。
  const geoReadOnly = readOnly || geometryReadOnly;
  const geoReadOnlyReason = readOnly ? readOnlyReason : geometryReadOnlyReason;

  // 拖拽提交信号 (历史栈落点入栈): 必须在两个编辑器之前创建, 供其拖拽 down/up 调用。
  const sig = useCommitSignal();

  const geo = useGeometryEditor({
    projectId,
    baselineVersionId,
    readOnly: geoReadOnly,
    readOnlyReason: geoReadOnlyReason,
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
    baselineVersionId,
    positionLocked: posLocked,
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
  // 几何只读时几何域整体关闭 (CP5v3): 不写几何草稿, 也不提示/恢复几何草稿。
  const draft = useDraftAutosave({
    projectId,
    schemeId,
    baselineVersionId,
    geoReadOnly,
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
  const kbdRef = useRef({ mode, geo, furn, history, geoReadOnly });
  kbdRef.current = { mode, geo, furn, history, geoReadOnly };

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onKeyDown = (e: KeyboardEvent) => {
      const {
        mode: m,
        geo: g,
        furn: f,
        history: h,
        geoReadOnly: gro,
      } = kbdRef.current;
      const inForm = isFormEl(document.activeElement);
      const ctrl = e.ctrlKey || e.metaKey;
      const key = e.key;
      // 几何只读 (CP5v3): 几何模式下所有改数据的键盘操作旁路 (保存/复制/粘贴/
      // 全选/删除/微移), 免产生保存不了的本地几何改动。
      const geoMutBlocked = m === 'geometry' && gro;

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
        if (geoMutBlocked) return;
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
        if (geoMutBlocked) return;
        if (m === 'geometry') g.paste();
        else f.paste();
        return;
      }

      // Ctrl+A 全选当前模式可选对象 (P2-7, 表单内放行给浏览器原生全选)。
      if (ctrl && (key === 'a' || key === 'A')) {
        if (inForm) return;
        e.preventDefault();
        if (geoMutBlocked) return;
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
        if (geoMutBlocked) return;
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
        if (geoMutBlocked) return;
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

  // 共享视口 (P1): 几何/家具两 Tab 共用一份缩放平移, 切 Tab 不再丢视口。
  const viewportState = React.useState<ViewportState>({
    scale: 1,
    tx: 0,
    ty: 0,
  });
  const [sharedVp, setSharedVp] = viewportState;
  const canvasHostRef = React.useRef<HTMLDivElement | null>(null);

  // 打开即 Fit (P1): 仅几何首次到达时跑一次 (审查: 否则 Ctrl+0 归 100% 后
  // 任何几何改动都会因 G 引用变化重触发 fit, 视口被夺回)。
  const autoFittedRef = React.useRef(false);
  React.useEffect(() => {
    if (!G || autoFittedRef.current) return;
    autoFittedRef.current = true;
    if (sharedVp.scale !== 1 || sharedVp.tx !== 0 || sharedVp.ty !== 0) return;
    const vb = readViewBox(G);
    const [ox, oy] = readOrigin(G);
    const fitted = computeFitVp(vb, roomsContentBBox(G, [ox, oy]));
    if (fitted.scale !== 1 || fitted.tx !== 0 || fitted.ty !== 0) {
      setSharedVp(fitted);
    }
    // 仅几何首达/变化时评估; sharedVp 变化不应重触发 (用户操作优先)。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [G]);

  // 视口快捷键 (P1, 画布悬停时生效): Ctrl/⌘± 步进缩放, Ctrl/⌘0 100%, Shift+1 Fit。
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!G) return;
      if (isFormEl(document.activeElement)) return;
      if (!canvasHostRef.current?.matches(':hover')) return;
      const vb = readViewBox(G);
      const step = (factor: number) => {
        const cx = vb[0] + vb[2] / 2;
        const cy = vb[1] + vb[3] / 2;
        setSharedVp((p) => {
          const s2 = Math.min(12, Math.max(0.2, p.scale * factor));
          const k = s2 / p.scale;
          return {
            scale: s2,
            tx: cx - (cx - p.tx) * k,
            ty: cy - (cy - p.ty) * k,
          };
        });
      };
      if ((e.ctrlKey || e.metaKey) && (e.key === '=' || e.key === '+')) {
        e.preventDefault();
        step(1.25);
      } else if ((e.ctrlKey || e.metaKey) && e.key === '-') {
        e.preventDefault();
        step(1 / 1.25);
      } else if ((e.ctrlKey || e.metaKey) && e.key === '0') {
        e.preventDefault();
        setSharedVp({ scale: 1, tx: 0, ty: 0 });
      } else if (e.shiftKey && e.code === 'Digit1') {
        e.preventDefault();
        const [ox, oy] = readOrigin(G);
        setSharedVp(computeFitVp(vb, roomsContentBBox(G, [ox, oy])));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [G, setSharedVp]);

  return (
    // P4 全屏: 撑满 canvas 变体 (fixed 满视口), 顶栏 shrink, 画布区 flex-1 吃满剩余高度。
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden p-3">
      {readOnly && (
        <NoticeBanner tone="warn">
          {readOnlyReason || '当前对象只读，不能保存修改。'}
        </NoticeBanner>
      )}
      {!readOnly && geometryReadOnly && mode === 'geometry' && (
        <NoticeBanner tone="warn">
          {geometryReadOnlyReason || '几何只读，家具可正常编辑。'}
        </NoticeBanner>
      )}
      <div className="mb-3 flex flex-wrap items-center gap-3 text-sm text-gray-600 dark:text-white">
        {/* P4 全屏: 侧栏/导航已隐, 顶栏留返回口 (回项目概览)。 */}
        <LinkButton
          variant="secondary"
          size="sm"
          href={`/studio/projects/${encodeURIComponent(projectId)}/overview`}
          title="退出全屏编辑器,返回项目概览"
        >
          ← 返回
        </LinkButton>
        <span className="font-semibold">户型 {projectId}</span>
        {baselineVersionId ? (
          <span className="font-semibold">户型版本 {baselineVersionId}</span>
        ) : (
          <span className="font-semibold">方案 {schemeId}</span>
        )}
        <LoadStateBadge state={loadState} />
        {!readOnly && (
          <div className="flex items-center gap-1">
            <IconButton
              onClick={() => history.undo()}
              disabled={!history.canUndo}
              title="撤销 (Ctrl+Z)"
              ariaLabel="撤销"
            >
              <MdUndo className="h-4 w-4" />
            </IconButton>
            <IconButton
              onClick={() => history.redo()}
              disabled={!history.canRedo}
              title="重做 (Ctrl+Y)"
              ariaLabel="重做"
            >
              <MdRedo className="h-4 w-4" />
            </IconButton>
          </div>
        )}
        <IconButton
          onClick={() => setShowHelp(true)}
          title="快捷键速查 (?)"
          ariaLabel="快捷键速查"
        >
          <MdHelpOutline className="h-4 w-4" />
        </IconButton>
        <IconButton
          onClick={() => {
            setPreviewKey((k) => k + 1);
            setShowPreview((v) => !v);
          }}
          title="方案预览 (轴测/平面)"
          ariaLabel="方案预览"
        >
          <MdImage className="h-4 w-4" />
        </IconButton>
        {mode === 'geometry' && geo.insertMode && (
          <Badge tone="brand" dataTestId="insert-mode-badge">
            {geo.insertMode === 'door'
              ? '开门模式'
              : geo.insertMode === 'window'
              ? '插窗模式'
              : geo.insertMode === 'freewall'
              ? '自由墙模式'
              : geo.insertMode === 'lshape'
              ? 'L形房模式'
              : '＋房间模式'}
          </Badge>
        )}
        {/* 承上启下前进 CTA(§7):方案模式→预览/出图;草稿户型→去确认户型 */}
        {!baselineVersionId ? (
          <div className="ml-auto flex items-center gap-2">
            <LinkButton
              variant="secondary"
              size="sm"
              href={`/studio/projects/${encodeURIComponent(
                projectId,
              )}/gallery?scheme=${encodeURIComponent(schemeId)}`}
            >
              方案预览
            </LinkButton>
            <LinkButton
              variant="primary"
              size="sm"
              href={`/studio/projects/${encodeURIComponent(
                projectId,
              )}/render?scheme=${encodeURIComponent(schemeId)}`}
            >
              生成效果图 →
            </LinkButton>
          </div>
        ) : !readOnly ? (
          <LinkButton
            variant="success-solid"
            size="sm"
            href={`/studio/projects/${encodeURIComponent(
              projectId,
            )}/baseline?version=${encodeURIComponent(baselineVersionId)}`}
            className="ml-auto"
          >
            完成编辑,去确认户型 →
          </LinkButton>
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

      {/* 悬挂件可见性 (审计契约项): room_id 指向已删/改名房间的家具在渲染中被跳过,
          此前用户只看到“家具凭空消失”。此处就地点名, 不阻断编辑。 */}
      {(() => {
        if (!G) return null;
        const ids = new Set(
          ((G as { rooms?: Array<{ id?: string }> }).rooms ?? []).map((r) =>
            String(r?.id),
          ),
        );
        const dangling = furniture.filter(
          (f) => f.room_id != null && !ids.has(String(f.room_id)),
        );
        if (!dangling.length) return null;
        return (
          <NoticeBanner tone="warn">
            {dangling.length} 件家具引用了不存在的房间(
            {Array.from(new Set(dangling.map((f) => String(f.t)))).join(', ')}
            ),渲染时会被跳过 —— 请删除或重新指定房间。
          </NoticeBanner>
        );
      })()}
      {draft.pending && (
        <DraftRecoverBanner
          pending={draft.pending}
          onRecover={draft.recover}
          onDiscard={draft.discard}
        />
      )}
      {/* P4 全屏: 画布区吃满剩余高度 (flex-1 + min-h-0), 不再用视口魔数。 */}
      <div
        ref={canvasHostRef}
        className="flex min-h-0 flex-1 flex-col gap-4 lg:flex-row"
      >
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
            readOnly={geoReadOnly}
            readOnlyReason={geoReadOnlyReason}
            viewportState={viewportState}
            projectId={projectId}
            baselineVersionId={baselineVersionId}
          />
        ) : data.furnitureLoadState === 'error' ? (
          <div className="min-w-0 flex-1 rounded-2xl border border-red-200 bg-white p-6 dark:border-red-500/30 dark:bg-navy-800">
            <BackendErrorBanner
              message={`家具加载失败：${
                data.furnitureLoadError || '未知错误'
              }。为避免覆盖远端数据，家具编辑和保存已禁用。`}
            />
            <Button
              variant="primary"
              onClick={() => void data.reloadFurniture()}
              className="mt-4"
            >
              重试加载家具
            </Button>
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
            posLocked={posLocked}
            onTogglePosLock={() => setPosLocked((v) => !v)}
            viewportState={viewportState}
          />
        )}
      </div>
      <PreviewDrawer
        projectId={projectId}
        schemeId={schemeId ?? 'default'}
        open={showPreview}
        onClose={() => setShowPreview(false)}
        dirty={dirty}
        refreshKey={previewKey}
      />
      <Modal
        open={showHelp}
        onClose={() => setShowHelp(false)}
        title="键盘快捷键"
      >
        <dl className="grid grid-cols-1 gap-1.5 text-sm sm:grid-cols-2">
          {[
            ['Ctrl/⌘ + S', '保存'],
            ['Ctrl/⌘ + Z', '撤销'],
            ['Ctrl/⌘ + Shift + Z / Y', '重做'],
            ['Ctrl/⌘ + D', '复制副本'],
            ['Ctrl/⌘ + C / V', '复制 / 粘贴'],
            ['Ctrl/⌘ + A', '全选'],
            ['空格 + 拖拽', '平移画布(悬停画布时)'],
            ['Ctrl/⌘ + / −', '缩放画布'],
            ['Ctrl/⌘ + 0', '缩放 100%'],
            ['Shift + 1', 'Fit 全户型'],
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
      </Modal>
    </div>
  );
}
