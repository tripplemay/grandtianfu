'use client';

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { postDerive, saveGeometry } from 'lib/studioApi';
import type { Geometry, Rect, Room, DeriveResult } from 'lib/floorplan/types';
import {
  findOverlapErrors,
  overlapErrorMessage,
  roomById,
  computeMove,
  alignBoxes,
  distributeBoxes,
  type SnapGuide,
  type AlignBox,
  type AlignMode,
  type DistributeMode,
} from 'lib/floorplan/geometry';
import type { DragHud } from 'lib/floorplan/overlay';
import { nextId } from 'lib/floorplan/ids';
import { type EditorSelection } from '../EditorStage';
import { type SaveState } from '../geometry/GeometrySidePanel';
import { useGeometryCanvas, type Marquee } from './useGeometryCanvas';
import { useGeometryForm } from './useGeometryForm';

const EMPTY_SELECTION: EditorSelection = {
  room: null,
  rooms: [],
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
  // 历史栈落点入栈支撑 (阶段 2): 透传到 useGeometryCanvas 的拖拽 down/up。
  beginDrag: () => void;
  endDrag: () => void;
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
  beginDrag,
  endDrag,
}: GeometryEditorParams) {
  const [selection, setSelection] = useState<EditorSelection>(EMPTY_SELECTION);
  // 选中态真值 ref (阶段 5a): 供画布群组拖拽判断主房是否在多选集合内, 闭包不过期。
  const selectionRef = useRef<EditorSelection>(selection);
  selectionRef.current = selection;
  // 框选 marquee 矩形 (阶段 5a / P2-7): 画布拖拽期镜像, 松手清空。
  const [marquee, setMarquee] = useState<Marquee | null>(null);
  const [insertMode, setInsertMode] = useState<
    'door' | 'freewall' | 'room' | null
  >(null);
  const [fwPts, setFwPts] = useState<Array<[number, number]>>([]);
  // 落点真值 ref (StrictMode 安全): 与 fwPts 状态镜像; 落点副作用按此执行一次。
  const fwPtsRef = useRef<Array<[number, number]>>([]);
  // 拖拽期可视反馈 (阶段 3 / P1-4): 吸附对齐线 + 实时尺寸 HUD。松手清空。
  const [snapGuides, setSnapGuides] = useState<SnapGuide[]>([]);
  const [dragHud, setDragHud] = useState<DragHud | null>(null);
  const [saveState, setSaveState] = useState<SaveState>(EMPTY_SAVE);
  // 防丢失 (P1-6): 任一写入口置脏; 保存成功清脏; beforeunload 在脏时拦截 (FloorplanEditor)。
  const [dirty, setDirty] = useState(false);

  const deriveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clipboardRef = useRef<Room | null>(null);

  const markDirty = useCallback(() => setDirty(true), []);

  // ---- 不可变 G 更新, 同步 gRef (供拖拽/debounce 读最新值) ---- //
  const updateG = useCallback(
    (updater: (g: Geometry) => Geometry) => {
      setG((prev) => {
        if (!prev) return prev;
        const next = updater(prev);
        gRef.current = next;
        return next;
      });
      setDirty(true);
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

  // ---- 侧栏表单编辑 (房间/门窗/自由墙/打通/分隔) ---- //
  // 先建 form: 画布两点落新房复用 form.onAddRoom (默认 space/type + 校验)。
  const form = useGeometryForm({
    selection,
    setSelection,
    gRef,
    updateG,
    deriveSoon,
    showToast,
  });

  // ---- 画布交互 (拖拽/吸附/回弹/门窗/自由墙落点/新房落点) ---- //
  const canvas = useGeometryCanvas({
    gRef,
    derived,
    insertMode,
    setInsertMode,
    setSelection,
    selectionRef,
    setMarquee,
    setFwPts,
    fwPtsRef,
    updateG,
    deriveSoon,
    showToast,
    addRoom: form.onAddRoom,
    beginDrag,
    endDrag,
    setSnapGuides,
    setDragHud,
  });

  const onToggleInsert = (mode: 'door' | 'freewall' | 'room') => {
    setInsertMode((prev) => (prev === mode ? null : mode));
    setFwPts([]);
    fwPtsRef.current = [];
    showToast(
      mode === 'door'
        ? '开门模式:点一段墙插入默认门'
        : mode === 'freewall'
        ? '自由墙:依次点两点(自动正交)'
        : '＋房间:依次点两点拉出矩形(自动吸附网格)',
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
        setDirty(false); // 保存成功清脏 (P1-6)。
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

  // ===== 键盘层操作 (P1-3 / P2-4), 由 FloorplanEditor 顶层 keydown 按 mode 分发 ===== //

  // Delete: 删选中 (开洞/自由墙/房间)。多选房 (N>1) -> 批量删一帧 (P2-7); 否则复用 form。
  const deleteSelected = useCallback(() => {
    if (selection.opening) {
      form.onDelOp();
      return;
    }
    if (selection.freeWall) {
      form.onDelFw();
      return;
    }
    if (selection.rooms.length > 1) {
      const ids = new Set(selection.rooms);
      updateG((g) => ({
        ...g,
        rooms: g.rooms.filter((r) => !ids.has(r.id)),
      }));
      setSelection(EMPTY_SELECTION);
      deriveSoon();
      return;
    }
    if (selection.room) form.onDelRoom();
  }, [selection, form, updateG, deriveSoon]);

  // 全选当前模式可选对象 (Ctrl+A, P2-7): 几何=全部房间多选。
  const selectAll = useCallback(() => {
    const g = gRef.current;
    if (!g || !g.rooms.length) return;
    const ids = g.rooms.map((r) => r.id);
    setSelection({
      room: ids[ids.length - 1],
      rooms: ids,
      room2: null,
      opening: null,
      freeWall: null,
    });
  }, [gRef]);

  // 选中房包围盒 (对齐/分布用)。
  const selRoomBoxes = useCallback((): AlignBox[] => {
    const g = gRef.current;
    if (!g) return [];
    return selection.rooms
      .map((id) => {
        const r = roomById(g, id);
        return r
          ? { id, x: r.rect[0], y: r.rect[1], w: r.rect[2], h: r.rect[3] }
          : null;
      })
      .filter((b): b is AlignBox => b != null);
  }, [gRef, selection.rooms]);

  // 据 id->新左上 应用到房 rect (一帧)。对齐/分布共用。
  const applyRoomPos = useCallback(
    (pos: Map<string, { x: number; y: number }>) => {
      updateG((gg) => ({
        ...gg,
        rooms: gg.rooms.map((r) => {
          const p = pos.get(r.id);
          return p
            ? { ...r, rect: [p.x, p.y, r.rect[2], r.rect[3]] as Rect }
            : r;
        }),
      }));
      deriveSoon();
    },
    [updateG, deriveSoon],
  );

  // 对齐选中房 (P2-7): 纯函数 alignBoxes -> 应用一帧。少于 2 个 no-op。
  const alignRooms = useCallback(
    (mode: AlignMode) => {
      const boxes = selRoomBoxes();
      if (boxes.length < 2) return;
      applyRoomPos(alignBoxes(boxes, mode));
    },
    [selRoomBoxes, applyRoomPos],
  );

  // 分布选中房 (P2-7): 水平/垂直等距, 少于 3 个 no-op。
  const distributeRooms = useCallback(
    (mode: DistributeMode) => {
      const boxes = selRoomBoxes();
      if (boxes.length < 3) return;
      applyRoomPos(distributeBoxes(boxes, mode));
    },
    [selRoomBoxes, applyRoomPos],
  );

  // Esc: 退出插入模式 (＋门/＋自由墙) 或清选。
  const onEscape = useCallback(() => {
    if (insertMode) {
      setInsertMode(null);
      setFwPts([]);
      fwPtsRef.current = [];
    } else {
      setSelection(EMPTY_SELECTION);
    }
  }, [insertMode]);

  // 方向键微移 1 单位 (Shift=10)。N=1: 复用 computeMove (alt=true 关吸附 + 跨space回弹,
  // 与阶段2 单选一致零回归)。N>1: 群组同 delta 平移一帧 (P2-7)。
  const nudge = useCallback(
    (dx: number, dy: number) => {
      const g = gRef.current;
      if (!g) return;
      if (selection.rooms.length > 1) {
        const ids = new Set(selection.rooms);
        updateG((gg) => ({
          ...gg,
          rooms: gg.rooms.map((r) =>
            ids.has(r.id)
              ? {
                  ...r,
                  rect: [
                    r.rect[0] + dx,
                    r.rect[1] + dy,
                    r.rect[2],
                    r.rect[3],
                  ] as Rect,
                }
              : r,
          ),
        }));
        deriveSoon();
        return;
      }
      if (!selection.room) return;
      const room = roomById(g, selection.room);
      if (!room) return;
      const rect = computeMove(g, room, [...room.rect] as Rect, dx, dy, true);
      updateG((gg) => ({
        ...gg,
        rooms: gg.rooms.map((r) => (r.id === room.id ? { ...r, rect } : r)),
      }));
      deriveSoon();
    },
    [gRef, selection.room, selection.rooms, updateG, deriveSoon],
  );

  // 复制副本: rect 偏移 + 新 id + 选中新件 (P2-4)。
  const cloneRoom = (room: Room): Room => {
    const off = 20;
    return {
      ...room,
      id: nextId('r'),
      rect: [
        room.rect[0] + off,
        room.rect[1] + off,
        room.rect[2],
        room.rect[3],
      ] as Rect,
    };
  };

  const insertRoom = useCallback(
    (room: Room) => {
      updateG((gg) => ({ ...gg, rooms: [...gg.rooms, room] }));
      setSelection({
        room: room.id,
        rooms: [room.id],
        room2: null,
        opening: null,
        freeWall: null,
      });
      deriveSoon();
    },
    [updateG, deriveSoon],
  );

  const duplicateSelected = useCallback(() => {
    const g = gRef.current;
    if (!g) return;
    // N>1: 批量复制全部选中房 (各自偏移 + 新 id) 一帧, 选中新副本 (P2-7)。
    if (selection.rooms.length > 1) {
      const copies = selection.rooms
        .map((id) => {
          const r = roomById(g, id);
          return r ? cloneRoom(r) : null;
        })
        .filter((r): r is Room => r != null);
      if (!copies.length) return;
      const ids = copies.map((r) => r.id);
      updateG((gg) => ({ ...gg, rooms: [...gg.rooms, ...copies] }));
      setSelection({
        room: ids[ids.length - 1],
        rooms: ids,
        room2: null,
        opening: null,
        freeWall: null,
      });
      deriveSoon();
      showToast(`已复制 ${copies.length} 个房间副本`);
      return;
    }
    if (!selection.room) return;
    const room = roomById(g, selection.room);
    if (!room) return;
    insertRoom(cloneRoom(room));
    showToast('已复制房间副本');
  }, [
    gRef,
    selection.room,
    selection.rooms,
    insertRoom,
    updateG,
    deriveSoon,
    showToast,
  ]);

  const copySelected = useCallback(() => {
    const g = gRef.current;
    if (!g || !selection.room) return;
    const room = roomById(g, selection.room);
    if (room) clipboardRef.current = room;
  }, [gRef, selection.room]);

  const paste = useCallback(() => {
    if (!clipboardRef.current) return;
    insertRoom(cloneRoom(clipboardRef.current));
  }, [insertRoom]);

  // undo/redo 还原 G 后重派生 (供历史栈 onAfterApply 调用)。
  const reDerive = useCallback(() => {
    deriveSoon();
  }, [deriveSoon]);

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
    contentRef: canvas.contentRef,
    selection,
    setSelection,
    marquee,
    insertMode,
    fwPts,
    snapGuides,
    dragHud,
    saveState,
    dirty,
    markDirty,
    overlapMsgs,
    errorRoomIds,
    deleteSelected,
    onEscape,
    nudge,
    duplicateSelected,
    copySelected,
    paste,
    selectAll,
    alignRooms,
    distributeRooms,
    reDerive,
    onSvgPointerDown: canvas.onSvgPointerDown,
    onSvgPointerMove: canvas.onSvgPointerMove,
    onSvgPointerUp: canvas.onSvgPointerUp,
    onSvgPointerCancel: canvas.onSvgPointerCancel,
    onRoomPointerDown: canvas.onRoomPointerDown,
    onHandlePointerDown: canvas.onHandlePointerDown,
    onOpeningPointerDown: canvas.onOpeningPointerDown,
    onOpeningHandlePointerDown: canvas.onOpeningHandlePointerDown,
    onOpeningFlip: canvas.onOpeningFlip,
    onWallPointerDown: canvas.onWallPointerDown,
    onFreeWallPointerDown: canvas.onFreeWallPointerDown,
    onSetRoom: form.onSetRoom,
    onSetLabel: form.onSetLabel,
    onSetRect: form.onSetRect,
    onAddRoom: form.onAddRoom,
    onDelRoom: form.onDelRoom,
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
