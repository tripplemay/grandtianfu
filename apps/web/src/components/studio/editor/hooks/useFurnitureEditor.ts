'use client';

import React, { useCallback, useRef, useState } from 'react';
import { saveFurniture } from 'lib/studioApi';
import type { Geometry } from 'lib/floorplan/types';
import { readOrigin, FALLBACK_ORIGIN } from 'lib/floorplan/coords';
import {
  type Furniture,
  furnAbs,
  isCircle,
  reanchor,
  buildDefaultFurniture,
  duplicateFurniture,
  stripRuntimeFields,
  furnSnapGuides,
  roomAtGeo,
  computeFurnResize,
  computeRotation,
  clampToRoom,
  snapToWall,
  bringToFrontZ,
  sendToBackZ,
} from 'lib/floorplan/furniture';
import { roomById, type SnapGuide } from 'lib/floorplan/geometry';
import type { DragHud } from 'lib/floorplan/overlay';
import { type FurnSaveState } from '../furniture/FurnitureSidePanel';
import { isBackgroundTarget } from '../pointerUtils';

const EMPTY_FURN_SAVE: FurnSaveState = {
  saving: false,
  savedOk: false,
  error: null,
};

// 拖拽以稳定 id 为身份 (阶段 0): 删/重排中间件不会错位。
// 三种拖拽 (阶段 4a): 移动 / 缩放手柄 / 旋转柄。
type FurnDrag =
  | { kind: 'move'; id: string; ox: number; oy: number }
  | { kind: 'resize'; id: string; handle: string }
  | { kind: 'rotate'; id: string };

interface FurnitureEditorParams {
  projectId: string;
  gRef: React.MutableRefObject<Geometry | null>;
  furniture: Furniture[];
  setFurniture: React.Dispatch<React.SetStateAction<Furniture[]>>;
  furnRef: React.MutableRefObject<Furniture[]>;
  showToast: (msg: string) => void;
  // 历史栈落点入栈支撑 (阶段 2): 拖拽 down/up 信号 (中间帧不入栈, 结束落一帧)。
  beginDrag: () => void;
  endDrag: () => void;
}

// 家具编辑器 (B2): 指针拖拽 -> 反推 room_id + dx/dy; 侧栏增删改 + 保存。
export function useFurnitureEditor({
  projectId,
  gRef,
  furniture,
  setFurniture,
  furnRef,
  showToast,
  beginDrag,
  endDrag,
}: FurnitureEditorParams) {
  const [selId, setSelId] = useState<string | null>(null);
  const [furnSave, setFurnSave] = useState<FurnSaveState>(EMPTY_FURN_SAVE);
  // 防丢失 (P1-6): 写入口置脏; 保存成功清脏。
  const [dirty, setDirty] = useState(false);
  // 拖拽期可视反馈 (阶段 3 / P1-4): 对齐辅助线 + 实时尺寸 HUD。松手清空。
  const [snapGuides, setSnapGuides] = useState<SnapGuide[]>([]);
  const [dragHud, setDragHud] = useState<DragHud | null>(null);
  // 越界拖动被夹取的件 id (P2-5): FurnitureLayer 据此红描边提示。
  const [blockedId, setBlockedId] = useState<string | null>(null);
  const clipboardRef = useRef<Furniture | null>(null);

  const markDirty = useCallback(() => setDirty(true), []);

  const svgRef = useRef<SVGSVGElement>(null);
  // 视口变换层 <g> 的引用: getScreenCTM 取此 g (含 translate/scale), 使缩放/平移下
  // 命中坐标自动正确 (阶段 1)。
  const contentRef = useRef<SVGGElement>(null);
  const furnDragRef = useRef<FurnDrag | null>(null);

  // ---- 不可变 furniture 更新, 同步 furnRef ---- //
  const updateFurniture = useCallback(
    (updater: (f: Furniture[]) => Furniture[]) => {
      setFurniture((prev) => {
        const next = updater(prev);
        furnRef.current = next;
        return next;
      });
      setFurnSave((s) => (s.savedOk || s.error ? EMPTY_FURN_SAVE : s));
      setDirty(true);
    },
    [setFurniture, furnRef],
  );

  // ---- 几何坐标换算 (§①, 与几何模式同口径) ---- //
  // CTM 取自内层 transform <g> (contentRef): scale≠1 / 平移时仍正确反算。
  const getGeoPoint = useCallback(
    (e: React.PointerEvent): { gx: number; gy: number } | null => {
      const svg = svgRef.current;
      const g = contentRef.current;
      if (!svg || !g) return null;
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const ctm = g.getScreenCTM();
      if (!ctm) return null;
      const p = pt.matrixTransform(ctm.inverse());
      const origin = gRef.current ? readOrigin(gRef.current) : FALLBACK_ORIGIN;
      return { gx: p.x - origin[0], gy: p.y - origin[1] };
    },
    [gRef],
  );

  // 切换 Tab 时清空家具选中 / 拖拽态 (沿用原 onChange 逻辑)。
  const resetSelection = useCallback(() => {
    setSelId(null);
    furnDragRef.current = null;
  }, []);

  // ===== 家具交互 (B2): 指针拖拽 -> 反推 room_id + dx/dy ===== //
  // onFurnItemDown useCallback (阶段 3 / P2-1): 透传给 memo 化 FurnitureItem 后引用稳定。
  const onFurnItemDown = useCallback(
    (e: React.PointerEvent, id: string) => {
      e.stopPropagation();
      const pt = getGeoPoint(e);
      const g = gRef.current;
      if (!pt || !g) return;
      setSelId(id);
      const it = furnRef.current.find((f) => f.id === id);
      if (!it) return;
      const a = furnAbs(it, g);
      furnDragRef.current = {
        kind: 'move',
        id,
        ox: isCircle(it) ? pt.gx - a.cx : pt.gx - a.x,
        oy: isCircle(it) ? pt.gy - a.cy : pt.gy - a.y,
      };
      beginDrag();
      svgRef.current?.setPointerCapture(e.pointerId);
    },
    [getGeoPoint, gRef, furnRef, beginDrag],
  );

  // 缩放手柄按下 (P2-3): 复用 geometry ResizeHandles 模式。
  const onFurnResizeDown = useCallback(
    (e: React.PointerEvent, handle: string) => {
      e.stopPropagation();
      const id = selId;
      if (id === null) return;
      setSelId(id);
      furnDragRef.current = { kind: 'resize', id, handle };
      beginDrag();
      svgRef.current?.setPointerCapture(e.pointerId);
    },
    [selId, beginDrag],
  );

  // 旋转柄按下 (P2-2)。
  const onFurnRotateDown = useCallback(
    (e: React.PointerEvent) => {
      e.stopPropagation();
      const id = selId;
      if (id === null) return;
      furnDragRef.current = { kind: 'rotate', id };
      beginDrag();
      svgRef.current?.setPointerCapture(e.pointerId);
    },
    [selId, beginDrag],
  );

  const onFurnSvgDown = (e: React.PointerEvent) => {
    if (isBackgroundTarget(e)) setSelId(null);
  };

  const onFurnSvgMove = useCallback(
    (e: React.PointerEvent) => {
      const d = furnDragRef.current;
      const g = gRef.current;
      if (!d || !g) return;
      const pt = getGeoPoint(e);
      if (!pt) return;
      const it0 = furnRef.current.find((f) => f.id === d.id);
      if (!it0) return;
      const a0 = furnAbs(it0, g);
      const circle = isCircle(it0);

      // ---- 旋转柄拖拽 (P2-2): 指针角 -> rot, 15° 吸附 (Shift 自由) ---- //
      if (d.kind === 'rotate') {
        const rot = computeRotation(a0.cx, a0.cy, pt.gx, pt.gy, e.shiftKey);
        updateFurniture((f) =>
          f.map((it) => {
            if (it.id !== d.id) return it;
            if (rot === 0) {
              const n = { ...it };
              delete n.rot;
              return n;
            }
            return { ...it, rot };
          }),
        );
        setSnapGuides([]);
        setDragHud({ x: a0.cx, y: a0.y, text: `${Math.round(rot)}°` });
        return;
      }

      // ---- 缩放手柄拖拽 (P2-3): 件本地系内固定对边改 w/h (圆形改 r) ---- //
      if (d.kind === 'resize') {
        const rot = typeof it0.rot === 'number' ? it0.rot : 0;
        const rz = computeFurnResize(a0, circle, d.handle, pt.gx, pt.gy, rot);
        const patch = reanchor(
          it0,
          g,
          rz.anchorX,
          rz.anchorY,
          rz.centerX,
          rz.centerY,
        );
        const nit: Furniture = { ...it0, ...patch };
        if (rz.r != null) nit.r = rz.r;
        if (rz.w != null) nit.w = rz.w;
        if (rz.h != null) nit.h = rz.h;
        updateFurniture((f) => f.map((it) => (it.id === d.id ? nit : it)));
        const a = furnAbs(nit, g);
        setSnapGuides(furnSnapGuides(nit, g, a));
        setDragHud({
          x: a.cx,
          y: a.y,
          text: circle
            ? `R ${Math.round(a.r)}`
            : `${Math.round(a.w)} × ${Math.round(a.h)}`,
        });
        return;
      }

      // ---- 移动拖拽 (越界 clamp + 贴墙吸附, P2-5) ---- //
      let anchorX = pt.gx - d.ox;
      let anchorY = pt.gy - d.oy;
      let cX = circle ? anchorX : anchorX + a0.w / 2;
      let cY = circle ? anchorY : anchorY + a0.h / 2;
      // 落点中心命中房间 -> 允许跨房; 未命中任何房 -> 夹回当前房并红描边提示。
      const hit = roomAtGeo(g, cX, cY);
      const room = hit ?? roomById(g, it0.room_id ?? null);
      let blocked = false;
      if (room) {
        if (!hit) {
          const c = clampToRoom(
            room.rect,
            anchorX,
            anchorY,
            a0.w,
            a0.h,
            circle,
            a0.r,
          );
          anchorX = c.anchorX;
          anchorY = c.anchorY;
          blocked = c.clamped;
        }
        // 近墙贴墙吸附 (落在的房间内)。
        const s = snapToWall(
          room.rect,
          anchorX,
          anchorY,
          a0.w,
          a0.h,
          circle,
          a0.r,
        );
        anchorX = s.anchorX;
        anchorY = s.anchorY;
      }
      cX = circle ? anchorX : anchorX + a0.w / 2;
      cY = circle ? anchorY : anchorY + a0.h / 2;
      const patch = reanchor(it0, g, anchorX, anchorY, cX, cY);
      const nit: Furniture = { ...it0, ...patch };
      updateFurniture((f) => f.map((it) => (it.id === d.id ? nit : it)));
      setBlockedId(blocked ? d.id : null);
      const a = furnAbs(nit, g);
      setSnapGuides(furnSnapGuides(nit, g, a));
      setDragHud({
        x: a.cx,
        y: a.y,
        text: circle
          ? `R ${Math.round(a.r)}`
          : `${Math.round(a.w)} × ${Math.round(a.h)}`,
      });
    },
    [getGeoPoint, gRef, furnRef, updateFurniture],
  );

  const onFurnSvgUp = useCallback(() => {
    if (furnDragRef.current) furnDragRef.current = null;
    setSnapGuides([]); // 松手清除可视反馈 (P1-4)。
    setDragHud(null);
    setBlockedId(null); // 清除越界红描边提示 (P2-5)。
    endDrag(); // 落点入栈 (内部自守卫)。
  }, [endDrag]);

  // pointercancel: 复用 up 清理 (阶段 0)。
  const onFurnSvgCancel = onFurnSvgUp;

  // ===== 家具侧栏编辑 ===== //
  const onSetFurnField = (field: keyof Furniture, value: string | number) => {
    if (selId === null) return;
    updateFurniture((f) =>
      f.map((it) => {
        if (it.id !== selId) return it;
        // label/color 清空 -> 删键, 避免落盘空串。
        if ((field === 'label' || field === 'color') && value === '') {
          const next = { ...it };
          delete next[field];
          return next;
        }
        // rot=0 -> 删键, 保盘上格式干净 + 引擎 no-op (P2-2)。
        if (field === 'rot' && Number(value) === 0) {
          const next = { ...it };
          delete next.rot;
          return next;
        }
        return { ...it, [field]: value };
      }),
    );
  };

  // ===== z-order 置顶/置底 (P2-13) ===== //
  const bringToFront = useCallback(() => {
    if (selId === null) return;
    updateFurniture((f) => {
      const zorder = bringToFrontZ(f, selId);
      return f.map((it) => (it.id === selId ? { ...it, zorder } : it));
    });
  }, [selId, updateFurniture]);

  const sendToBack = useCallback(() => {
    if (selId === null) return;
    updateFurniture((f) => {
      const zorder = sendToBackZ(f, selId);
      return f.map((it) => (it.id === selId ? { ...it, zorder } : it));
    });
  }, [selId, updateFurniture]);

  const onAddFurn = (type: string) => {
    const g = gRef.current;
    if (!g || !g.rooms.length) {
      showToast('无房间可放置家具');
      return;
    }
    // 当前房 = 选中件所属房, 否则首个房间。
    let room = g.rooms[0];
    if (selId !== null) {
      const it = furnRef.current.find((f) => f.id === selId);
      const r = it?.room_id ? g.rooms.find((rr) => rr.id === it.room_id) : null;
      if (r) room = r;
    }
    const item = buildDefaultFurniture(type, room);
    updateFurniture((f) => [...f, item]);
    setSelId(item.id ?? null);
    showToast(`已添加 ${type} → ${room.id}`);
  };

  const onDelFurn = () => {
    if (selId === null) return;
    updateFurniture((f) => f.filter((it) => it.id !== selId));
    setSelId(null);
  };

  // ===== 键盘层操作 (P1-3 / P2-4) ===== //

  const clearSelection = useCallback(() => setSelId(null), []);

  // 方向键微移 1 单位 (Shift=10): 复用 furnAbs/reanchor (相对键不变 room_id 偏移)。
  const nudge = useCallback(
    (dx: number, dy: number) => {
      const g = gRef.current;
      if (!g || selId === null) return;
      updateFurniture((f) =>
        f.map((it) => {
          if (it.id !== selId) return it;
          const a = furnAbs(it, g);
          const anchorX = (isCircle(it) ? a.cx : a.x) + dx;
          const anchorY = (isCircle(it) ? a.cy : a.y) + dy;
          const centerX = isCircle(it) ? anchorX : anchorX + a.w / 2;
          const centerY = isCircle(it) ? anchorY : anchorY + a.h / 2;
          return {
            ...it,
            ...reanchor(it, g, anchorX, anchorY, centerX, centerY),
          };
        }),
      );
    },
    [gRef, selId, updateFurniture],
  );

  // 复制副本: 深拷贝 + 偏移 + 新 id + 选中新件 (P2-4)。
  const duplicateSelected = useCallback(() => {
    if (selId === null) return;
    const it = furnRef.current.find((f) => f.id === selId);
    if (!it) return;
    const copy = duplicateFurniture(it, 20, 20);
    updateFurniture((f) => [...f, copy]);
    setSelId(copy.id ?? null);
    showToast('已复制家具副本');
  }, [selId, furnRef, updateFurniture, showToast]);

  const copySelected = useCallback(() => {
    if (selId === null) return;
    const it = furnRef.current.find((f) => f.id === selId);
    if (it) clipboardRef.current = it;
  }, [selId, furnRef]);

  const paste = useCallback(() => {
    if (!clipboardRef.current) return;
    const copy = duplicateFurniture(clipboardRef.current, 20, 20);
    updateFurniture((f) => [...f, copy]);
    setSelId(copy.id ?? null);
  }, [updateFurniture]);

  const onSaveFurn = async () => {
    // 剥离运行时 id, 保证盘上数据格式 byte 不破。
    const f = stripRuntimeFields(furnRef.current);
    setFurnSave({ saving: true, savedOk: false, error: null });
    try {
      const res = await saveFurniture(
        projectId,
        f as unknown as Record<string, unknown>[],
      );
      if (res.ok) {
        setFurnSave({ saving: false, savedOk: true, error: null });
        setDirty(false); // 保存成功清脏 (P1-6)。
        showToast('家具已保存 ✓');
      } else {
        setFurnSave({ saving: false, savedOk: false, error: '保存失败' });
      }
    } catch (e) {
      setFurnSave({
        saving: false,
        savedOk: false,
        error: e instanceof Error ? e.message : String(e),
      });
      showToast('家具保存请求失败(后端未起?)');
    }
  };

  return {
    svgRef,
    contentRef,
    furniture,
    selId,
    setSelId,
    furnSave,
    dirty,
    markDirty,
    snapGuides,
    dragHud,
    blockedId,
    resetSelection,
    clearSelection,
    onFurnItemDown,
    onFurnResizeDown,
    onFurnRotateDown,
    onFurnSvgDown,
    onFurnSvgMove,
    onFurnSvgUp,
    onFurnSvgCancel,
    onSetFurnField,
    onAddFurn,
    onDelFurn,
    bringToFront,
    sendToBack,
    nudge,
    duplicateSelected,
    copySelected,
    paste,
    onSaveFurn,
  };
}

export type FurnitureEditor = ReturnType<typeof useFurnitureEditor>;
