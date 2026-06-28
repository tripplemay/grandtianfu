'use client';

import React, { useCallback, useEffect, useRef } from 'react';
import type { Geometry } from 'lib/floorplan/types';
import { type Furniture } from 'lib/floorplan/furniture';
import { type EditorSelection } from '../EditorStage';

// 几何 G 与家具 items 共用一个历史栈 (P1-2)。快照式 past/present/future (G/items 不大)。
//
// 落点入栈策略 (非每帧):
//   - 提交 effect 监听 [G, furniture, tick]; 引用相等 = 无数据变化 → 不落帧。
//   - draggingRef 期间 (拖拽中) 即使 G/items 引用变了也跳过; 拖拽结束由 tick 触发落最终帧。
//   - 侧栏字段 commit / 加删 / 打通分隔 / 复制 等"一次操作"各产生一次新引用 → 落一帧。
//
// undo/redo: 先把目标快照写入 present.current (使提交 effect 看到引用相等而不重复落帧),
// 再 setG/setFurniture/setSelection 还原状态 + 镜像 ref; onAfterApply 触发重派生 + 置脏。
//
// 不破坏 byte 往返: 快照存的是运行时 G/Furniture 对象引用 (含运行时 id); 保存时各编辑器
// 仍走 stripRuntimeFields, undo/redo 不引入新字段, 故盘上格式不变。

const LIMIT = 100;

interface Snapshot {
  G: Geometry | null;
  furniture: Furniture[];
  geoSel: EditorSelection;
  furnSel: string | null;
}

interface Params {
  ready: boolean;
  G: Geometry | null;
  setG: React.Dispatch<React.SetStateAction<Geometry | null>>;
  gRef: React.MutableRefObject<Geometry | null>;
  furniture: Furniture[];
  setFurniture: React.Dispatch<React.SetStateAction<Furniture[]>>;
  furnRef: React.MutableRefObject<Furniture[]>;
  geoSel: EditorSelection;
  setGeoSel: React.Dispatch<React.SetStateAction<EditorSelection>>;
  furnSel: string | null;
  setFurnSel: React.Dispatch<React.SetStateAction<string | null>>;
  draggingRef: React.MutableRefObject<boolean>;
  tick: number;
  // 按域回调: 仅对实际变化的域重派生 / 置脏 (避免家具-only undo 误标几何脏)。
  onAfterApply: (gChanged: boolean, fChanged: boolean) => void;
}

export function useEditorHistory({
  ready,
  G,
  setG,
  gRef,
  furniture,
  setFurniture,
  furnRef,
  geoSel,
  setGeoSel,
  furnSel,
  setFurnSel,
  draggingRef,
  tick,
  onAfterApply,
}: Params) {
  const present = useRef<Snapshot | null>(null);
  const past = useRef<Snapshot[]>([]);
  const future = useRef<Snapshot[]>([]);
  const initialized = useRef(false);

  // 最新选中态 (effect 落帧时读, 避免闭包过期)。
  const selRef = useRef({ geoSel, furnSel });
  selRef.current = { geoSel, furnSel };

  // ---- 提交 effect: 数据引用变化 (且非拖拽中) → 落一帧 ---- //
  useEffect(() => {
    if (!ready) return;
    const cur: Snapshot = {
      G,
      furniture,
      geoSel: selRef.current.geoSel,
      furnSel: selRef.current.furnSel,
    };
    if (!initialized.current) {
      present.current = cur;
      initialized.current = true;
      return;
    }
    const p = present.current;
    if (!p) {
      present.current = cur;
      return;
    }
    // 无数据变化 (引用相等): undo/redo 还原 / 选中态变化 / 空拖拽 → 不落帧。
    if (p.G === G && p.furniture === furniture) return;
    // 拖拽中: 中间帧不入栈 (落点入栈由 tick 在拖拽结束时触发)。
    if (draggingRef.current) return;
    past.current.push(p);
    if (past.current.length > LIMIT) past.current.shift();
    present.current = cur;
    future.current = [];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [G, furniture, tick, ready]);

  const applySnapshot = useCallback(
    (s: Snapshot) => {
      // 比较去向前的 present (即将被覆盖) 与目标快照, 得出各域是否真变化。
      const cur = present.current;
      const gChanged = !cur || cur.G !== s.G;
      const fChanged = !cur || cur.furniture !== s.furniture;
      present.current = s; // 先写 present, 使提交 effect 看到引用相等而不重复落帧。
      gRef.current = s.G;
      setG(s.G);
      furnRef.current = s.furniture;
      setFurniture(s.furniture);
      setGeoSel(s.geoSel);
      setFurnSel(s.furnSel);
      onAfterApply(gChanged, fChanged);
    },
    [gRef, setG, furnRef, setFurniture, setGeoSel, setFurnSel, onAfterApply],
  );

  const undo = useCallback(() => {
    if (!past.current.length || !present.current) return;
    const cur = present.current;
    const prev = past.current.pop() as Snapshot;
    future.current.unshift(cur);
    applySnapshot(prev);
  }, [applySnapshot]);

  const redo = useCallback(() => {
    if (!future.current.length || !present.current) return;
    const cur = present.current;
    const nxt = future.current.shift() as Snapshot;
    past.current.push(cur);
    applySnapshot(nxt);
  }, [applySnapshot]);

  return { undo, redo };
}

export type EditorHistory = ReturnType<typeof useEditorHistory>;
