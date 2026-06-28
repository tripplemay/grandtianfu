'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { postDerive, saveGeometry } from 'lib/studioApi';
import type { Geometry, DeriveResult } from 'lib/floorplan/types';
import {
  findOverlapErrors,
  overlapErrorMessage,
} from 'lib/floorplan/geometry';
import { type EditorSelection } from '../EditorStage';
import { type SaveState } from '../geometry/GeometrySidePanel';
import { useGeometryCanvas } from './useGeometryCanvas';
import { useGeometryForm } from './useGeometryForm';

const EMPTY_SELECTION: EditorSelection = {
  room: null,
  room2: null,
  opening: null,
  freeWall: null,
};
const EMPTY_SAVE: SaveState = {
  saving: false,
  errors: [],
  warns: [],
  savedOk: false,
};

interface GeometryEditorParams {
  projectId: string;
  G: Geometry | null;
  setG: React.Dispatch<React.SetStateAction<Geometry | null>>;
  gRef: React.MutableRefObject<Geometry | null>;
  derived: DeriveResult | null;
  setDerived: React.Dispatch<React.SetStateAction<DeriveResult | null>>;
  showToast: (msg: string) => void;
}

// 几何编辑器编排 (§①-⑨): 持有 selection/insertMode/fwPts/saveState + updateG/
// derive 节流; 组合画布交互 (useGeometryCanvas) 与侧栏表单 (useGeometryForm);
// 自身保留 onSave 校验保存、onToggleInsert、实时重叠冲突 memo。受控 inline SVG。
export function useGeometryEditor({
  projectId,
  G,
  setG,
  gRef,
  derived,
  setDerived,
  showToast,
}: GeometryEditorParams) {
  const [selection, setSelection] = useState<EditorSelection>(EMPTY_SELECTION);
  const [insertMode, setInsertMode] = useState<'door' | 'freewall' | null>(
    null,
  );
  const [fwPts, setFwPts] = useState<Array<[number, number]>>([]);
  const [saveState, setSaveState] = useState<SaveState>(EMPTY_SAVE);

  const deriveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---- 不可变 G 更新, 同步 gRef (供拖拽/debounce 读最新值) ---- //
  const updateG = useCallback(
    (updater: (g: Geometry) => Geometry) => {
      setG((prev) => {
        if (!prev) return prev;
        const next = updater(prev);
        gRef.current = next;
        return next;
      });
    },
    [setG, gRef],
  );

  // ---- 派生 (实时内存, §⑧⑨) ---- //
  const deriveNow = useCallback(
    async (g: Geometry) => {
      try {
        const d = await postDerive(g);
        setDerived(d as unknown as DeriveResult);
      } catch {
        /* 派生失败静默 (保存时会有显式校验) */
      }
    },
    [setDerived],
  );

  const deriveSoon = useCallback(() => {
    // 编辑后重置上次保存状态, 让状态栏回到实时派生视图。
    setSaveState((s) => (s.savedOk || s.errors.length ? EMPTY_SAVE : s));
    if (deriveTimer.current) clearTimeout(deriveTimer.current);
    deriveTimer.current = setTimeout(() => {
      if (gRef.current) void deriveNow(gRef.current);
    }, 200);
  }, [deriveNow, gRef]);

  useEffect(
    () => () => {
      if (deriveTimer.current) clearTimeout(deriveTimer.current);
    },
    [],
  );

  // ---- 画布交互 (拖拽/吸附/回弹/门窗/自由墙落点) ---- //
  const canvas = useGeometryCanvas({
    gRef,
    derived,
    insertMode,
    setInsertMode,
    setSelection,
    setFwPts,
    updateG,
    deriveSoon,
    showToast,
  });

  // ---- 侧栏表单编辑 (房间/门窗/自由墙/打通/分隔) ---- //
  const form = useGeometryForm({
    selection,
    setSelection,
    gRef,
    updateG,
    deriveSoon,
    showToast,
  });

  const onToggleInsert = (mode: 'door' | 'freewall') => {
    setInsertMode((prev) => (prev === mode ? null : mode));
    setFwPts([]);
    showToast(
      mode === 'door'
        ? '开门模式:点一段墙插入默认门'
        : '自由墙:依次点两点(自动正交)',
    );
  };

  // 校验并保存 (§⑨)
  const onSave = async () => {
    const g = gRef.current;
    if (!g) {
      showToast('几何未加载');
      return;
    }
    // 客户端先拦重叠冲突 (后端 /save-geometry 也会 400, 此处给即时反馈)。
    const overlaps = findOverlapErrors(g.rooms);
    if (overlaps.length) {
      const msgs = overlaps.map(overlapErrorMessage);
      setSaveState({ saving: false, errors: msgs, warns: [], savedOk: false });
      showToast('存在重叠冲突,先「打通」标记合并或拖开');
      return;
    }
    setSaveState((s) => ({ ...s, saving: true }));
    try {
      const res = await saveGeometry(projectId, g);
      if (res.ok) {
        setSaveState({
          saving: false,
          errors: [],
          warns: res.warns,
          savedOk: true,
        });
        if (res.derived) setDerived(res.derived as unknown as DeriveResult);
        showToast('几何已保存 ✓');
      } else {
        setSaveState({
          saving: false,
          errors: res.errors ?? ['校验失败'],
          warns: res.warns,
          savedOk: false,
        });
        showToast('校验失败(ERROR),未保存');
      }
    } catch (e) {
      setSaveState({
        saving: false,
        errors: [e instanceof Error ? e.message : String(e)],
        warns: [],
        savedOk: false,
      });
      showToast('保存请求失败(后端未起?)');
    }
  };

  // 客户端实时算重叠冲突 (§④, 与后端 geometry.validate 同口径): 净矩形重叠且未标
  // 记同一合并组 -> ERROR。用于面板红字列出 + 涉及房间红色描边 + 禁用 💾。
  const overlapPairs = useMemo(
    () => (G ? findOverlapErrors(G.rooms) : []),
    [G],
  );
  const overlapMsgs = useMemo(
    () => overlapPairs.map(overlapErrorMessage),
    [overlapPairs],
  );
  const errorRoomIds = useMemo(() => {
    const s = new Set<string>();
    overlapPairs.forEach((p) => {
      s.add(p.a);
      s.add(p.b);
    });
    return s;
  }, [overlapPairs]);

  return {
    svgRef: canvas.svgRef,
    selection,
    insertMode,
    fwPts,
    saveState,
    overlapMsgs,
    errorRoomIds,
    onSvgPointerDown: canvas.onSvgPointerDown,
    onSvgPointerMove: canvas.onSvgPointerMove,
    onSvgPointerUp: canvas.onSvgPointerUp,
    onRoomPointerDown: canvas.onRoomPointerDown,
    onHandlePointerDown: canvas.onHandlePointerDown,
    onOpeningPointerDown: canvas.onOpeningPointerDown,
    onWallPointerDown: canvas.onWallPointerDown,
    onFreeWallPointerDown: canvas.onFreeWallPointerDown,
    onSetRoom: form.onSetRoom,
    onSetLabel: form.onSetLabel,
    onSetRect: form.onSetRect,
    onSetOp: form.onSetOp,
    onSetOpWall: form.onSetOpWall,
    onSetSpan: form.onSetSpan,
    onDelOp: form.onDelOp,
    onSetFw: form.onSetFw,
    onSetFwSpan: form.onSetFwSpan,
    onDelFw: form.onDelFw,
    onMerge: form.onMerge,
    onSplit: form.onSplit,
    onToggleInsert,
    onSave,
  };
}

export type GeometryEditor = ReturnType<typeof useGeometryEditor>;
