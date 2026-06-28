'use client';

import { useCallback, useRef, useState } from 'react';

// 拖拽提交信号 (阶段 2 / P1-2 的支撑件)。
// 历史栈采用"落点入栈": pointermove 期间不 push, 仅在拖拽结束 (pointerUp) push 一帧。
// 但拖拽期与拖拽结束都不直接改 G/items 的引用 (最后一帧 move 才改), 故需要一个显式
// 的"拖拽结束"信号让 useEditorHistory 的提交 effect 重新跑一次并落帧。
//   - draggingRef.current=true 期间: 提交 effect 看到 G/items 变化也跳过 (不落帧)。
//   - endDrag(): 清 dragging + bump tick → 触发提交 effect 跑一次 → 落最终帧。
// 几何 (useGeometryCanvas) 与家具 (useFurnitureEditor) 各自的拖拽 down/up 调用 begin/end。
export function useCommitSignal() {
  const draggingRef = useRef(false);
  const [tick, setTick] = useState(0);
  // 反应式拖拽态 (阶段 3 / P2-6): 供画布在拖拽期切 cursor=grabbing。仅 down/up 各变一次,
  // 不随 pointermove 变 (不影响拖拽期 memo)。
  const [dragging, setDragging] = useState(false);

  const beginDrag = useCallback(() => {
    draggingRef.current = true;
    setDragging(true);
  }, []);

  // 仅当确有拖拽时 bump (普通点击不产生多余 effect / 空帧)。
  const endDrag = useCallback(() => {
    setDragging(false);
    if (draggingRef.current) {
      draggingRef.current = false;
      setTick((t) => t + 1);
    }
  }, []);

  return { draggingRef, dragging, beginDrag, endDrag, tick };
}

export type CommitSignal = ReturnType<typeof useCommitSignal>;
