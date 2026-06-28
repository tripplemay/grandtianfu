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
} from 'lib/floorplan/furniture';
import { type FurnSaveState } from '../furniture/FurnitureSidePanel';
import { isBackgroundTarget } from '../pointerUtils';

const EMPTY_FURN_SAVE: FurnSaveState = {
  saving: false,
  savedOk: false,
  error: null,
};

type FurnDrag = { index: number; ox: number; oy: number };

interface FurnitureEditorParams {
  projectId: string;
  gRef: React.MutableRefObject<Geometry | null>;
  furniture: Furniture[];
  setFurniture: React.Dispatch<React.SetStateAction<Furniture[]>>;
  furnRef: React.MutableRefObject<Furniture[]>;
  showToast: (msg: string) => void;
}

// 家具编辑器 (B2): 指针拖拽 -> 反推 room_id + dx/dy; 侧栏增删改 + 保存。
export function useFurnitureEditor({
  projectId,
  gRef,
  furniture,
  setFurniture,
  furnRef,
  showToast,
}: FurnitureEditorParams) {
  const [selFurn, setSelFurn] = useState<number | null>(null);
  const [furnSave, setFurnSave] = useState<FurnSaveState>(EMPTY_FURN_SAVE);

  const svgRef = useRef<SVGSVGElement>(null);
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
    },
    [setFurniture, furnRef],
  );

  // ---- 几何坐标换算 (§①, 与几何模式同口径) ---- //
  const getGeoPoint = useCallback(
    (e: React.PointerEvent): { gx: number; gy: number } | null => {
      const svg = svgRef.current;
      if (!svg) return null;
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const ctm = svg.getScreenCTM();
      if (!ctm) return null;
      const p = pt.matrixTransform(ctm.inverse());
      const origin = gRef.current ? readOrigin(gRef.current) : FALLBACK_ORIGIN;
      return { gx: p.x - origin[0], gy: p.y - origin[1] };
    },
    [gRef],
  );

  // 切换 Tab 时清空家具选中 / 拖拽态 (沿用原 onChange 逻辑)。
  const resetSelection = useCallback(() => {
    setSelFurn(null);
    furnDragRef.current = null;
  }, []);

  // ===== 家具交互 (B2): 指针拖拽 -> 反推 room_id + dx/dy ===== //
  const onFurnItemDown = (e: React.PointerEvent, index: number) => {
    e.stopPropagation();
    const pt = getGeoPoint(e);
    const g = gRef.current;
    if (!pt || !g) return;
    setSelFurn(index);
    const it = furnRef.current[index];
    if (!it) return;
    const a = furnAbs(it, g);
    furnDragRef.current = {
      index,
      ox: isCircle(it) ? pt.gx - a.cx : pt.gx - a.x,
      oy: isCircle(it) ? pt.gy - a.cy : pt.gy - a.y,
    };
    svgRef.current?.setPointerCapture(e.pointerId);
  };

  const onFurnSvgDown = (e: React.PointerEvent) => {
    if (isBackgroundTarget(e)) setSelFurn(null);
  };

  const onFurnSvgMove = (e: React.PointerEvent) => {
    const d = furnDragRef.current;
    const g = gRef.current;
    if (!d || !g) return;
    const pt = getGeoPoint(e);
    if (!pt) return;
    updateFurniture((f) =>
      f.map((it, i) => {
        if (i !== d.index) return it;
        const a = furnAbs(it, g);
        const anchorX = pt.gx - d.ox;
        const anchorY = pt.gy - d.oy;
        const centerX = isCircle(it) ? anchorX : anchorX + a.w / 2;
        const centerY = isCircle(it) ? anchorY : anchorY + a.h / 2;
        return {
          ...it,
          ...reanchor(it, g, anchorX, anchorY, centerX, centerY),
        };
      }),
    );
  };

  const onFurnSvgUp = () => {
    if (furnDragRef.current) furnDragRef.current = null;
  };

  // ===== 家具侧栏编辑 ===== //
  const onSetFurnField = (field: keyof Furniture, value: string | number) => {
    if (selFurn === null) return;
    updateFurniture((f) =>
      f.map((it, i) => {
        if (i !== selFurn) return it;
        // label/color 清空 -> 删键, 避免落盘空串。
        if ((field === 'label' || field === 'color') && value === '') {
          const next = { ...it };
          delete next[field];
          return next;
        }
        return { ...it, [field]: value };
      }),
    );
  };

  const onAddFurn = (type: string) => {
    const g = gRef.current;
    if (!g || !g.rooms.length) {
      showToast('无房间可放置家具');
      return;
    }
    // 当前房 = 选中件所属房, 否则首个房间。
    let room = g.rooms[0];
    if (selFurn !== null) {
      const it = furnRef.current[selFurn];
      const r = it?.room_id ? g.rooms.find((rr) => rr.id === it.room_id) : null;
      if (r) room = r;
    }
    const item = buildDefaultFurniture(type, room);
    const newIndex = furnRef.current.length;
    updateFurniture((f) => [...f, item]);
    setSelFurn(newIndex);
    showToast(`已添加 ${type} → ${room.id}`);
  };

  const onDelFurn = () => {
    if (selFurn === null) return;
    updateFurniture((f) => f.filter((_, i) => i !== selFurn));
    setSelFurn(null);
  };

  const onSaveFurn = async () => {
    const f = furnRef.current;
    setFurnSave({ saving: true, savedOk: false, error: null });
    try {
      const res = await saveFurniture(
        projectId,
        f as unknown as Record<string, unknown>[],
      );
      if (res.ok) {
        setFurnSave({ saving: false, savedOk: true, error: null });
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
    furniture,
    selFurn,
    furnSave,
    resetSelection,
    onFurnItemDown,
    onFurnSvgDown,
    onFurnSvgMove,
    onFurnSvgUp,
    onSetFurnField,
    onAddFurn,
    onDelFurn,
    onSaveFurn,
  };
}

export type FurnitureEditor = ReturnType<typeof useFurnitureEditor>;
