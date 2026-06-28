'use client';

import React from 'react';
import type { Geometry, Rect } from 'lib/floorplan/types';
import { roomById, crossSpaceOverlap } from 'lib/floorplan/geometry';
import { nextId } from 'lib/floorplan/ids';
import { type EditorSelection } from '../EditorStage';

interface GeometryFormParams {
  selection: EditorSelection;
  setSelection: React.Dispatch<React.SetStateAction<EditorSelection>>;
  gRef: React.MutableRefObject<Geometry | null>;
  updateG: (updater: (g: Geometry) => Geometry) => void;
  deriveSoon: () => void;
  showToast: (msg: string) => void;
}

// 几何侧栏表单编辑: 房间 (type/space/label/rect)、门窗 (op/wall/span/删)、自由墙
// (字段/span/删)、打通/分隔。纯派生自当前 selection, 写入走 updateG + deriveSoon。
export function useGeometryForm({
  selection,
  setSelection,
  gRef,
  updateG,
  deriveSoon,
  showToast,
}: GeometryFormParams) {
  const onSetRoom = (field: 'type' | 'space', value: string) => {
    if (!selection.room) return;
    updateG((g) => ({
      ...g,
      rooms: g.rooms.map((r) =>
        r.id === selection.room ? { ...r, [field]: value } : r,
      ),
    }));
    deriveSoon();
  };

  const onSetLabel = (value: string) => {
    if (!selection.room) return;
    updateG((g) => ({
      ...g,
      rooms: g.rooms.map((r) =>
        r.id === selection.room
          ? { ...r, label: { ...(r.label ?? {}), zh: value } }
          : r,
      ),
    }));
  };

  const onSetRect = (i: number, value: number) => {
    const g = gRef.current;
    if (!g || !selection.room) return;
    const room = roomById(g, selection.room);
    if (!room) return;
    const nr = [...room.rect] as Rect;
    nr[i] = value;
    if (!crossSpaceOverlap(g, room, nr)) {
      updateG((gg) => ({
        ...gg,
        rooms: gg.rooms.map((r) => (r.id === room.id ? { ...r, rect: nr } : r)),
      }));
      deriveSoon();
    } else {
      showToast('会跨 space 重叠,已拒绝');
    }
  };

  const onSetOp = (field: string, value: string | boolean) => {
    if (!selection.opening) return;
    updateG((g) => ({
      ...g,
      openings: g.openings.map((o) =>
        o.id === selection.opening ? { ...o, [field]: value } : o,
      ),
    }));
    deriveSoon();
  };

  const onSetOpWall = (field: 'axis' | 'at', value: string | number) => {
    if (!selection.opening) return;
    updateG((g) => ({
      ...g,
      openings: g.openings.map((o) =>
        o.id === selection.opening
          ? { ...o, wall: { ...o.wall, [field]: value } }
          : o,
      ),
    }));
    deriveSoon();
  };

  const onSetSpan = (i: number, value: number) => {
    if (!selection.opening) return;
    updateG((g) => ({
      ...g,
      openings: g.openings.map((o) => {
        if (o.id !== selection.opening) return o;
        const span: [number, number] = [...o.wall.span] as [number, number];
        span[i] = value;
        return { ...o, wall: { ...o.wall, span } };
      }),
    }));
    deriveSoon();
  };

  const onDelOp = () => {
    if (!selection.opening) return;
    updateG((g) => ({
      ...g,
      openings: g.openings.filter((o) => o.id !== selection.opening),
    }));
    setSelection((s) => ({ ...s, opening: null }));
    deriveSoon();
  };

  const onSetFw = (field: string, value: string | number) => {
    if (!selection.freeWall) return;
    updateG((g) => ({
      ...g,
      free_walls: (g.free_walls ?? []).map((f) =>
        f.id === selection.freeWall ? { ...f, [field]: value } : f,
      ),
    }));
    deriveSoon();
  };

  const onSetFwSpan = (i: number, value: number) => {
    if (!selection.freeWall) return;
    updateG((g) => ({
      ...g,
      free_walls: (g.free_walls ?? []).map((f) => {
        if (f.id !== selection.freeWall) return f;
        const span: [number, number] = [...f.span] as [number, number];
        span[i] = value;
        return { ...f, span };
      }),
    }));
    deriveSoon();
  };

  const onDelFw = () => {
    if (!selection.freeWall) return;
    updateG((g) => ({
      ...g,
      free_walls: (g.free_walls ?? []).filter(
        (f) => f.id !== selection.freeWall,
      ),
    }));
    setSelection((s) => ({ ...s, freeWall: null }));
    deriveSoon();
  };

  // 打通: 选中两房 -> 标记同一合并组 (intentional merge); 两房 space 也设为同一,
  // 沿用现合并语义 (同 space=开放无墙)。合并组 id 复用首房已有 merge, 否则新建。
  const onMerge = () => {
    if (!selection.room || !selection.room2) {
      showToast('需先选两个房间(Shift+点第二个)');
      return;
    }
    const g = gRef.current;
    if (!g) return;
    const a = roomById(g, selection.room);
    if (!a) return;
    const mid = a.merge || nextId('m');
    updateG((gg) => ({
      ...gg,
      rooms: gg.rooms.map((r) =>
        r.id === selection.room || r.id === selection.room2
          ? { ...r, space: a.space, merge: mid }
          : r,
      ),
    }));
    deriveSoon();
    showToast(`已打通 → 合并组 ${mid}`);
  };

  // 分隔: 清除选中房的 merge + 拆到新 space (§⑦)。拆后若仍重叠, 实时校验报 ERROR。
  const onSplit = () => {
    if (!selection.room) {
      showToast('需先选一个房间');
      return;
    }
    const g = gRef.current;
    if (!g) return;
    const r = roomById(g, selection.room);
    if (!r) return;
    const nid = nextId('sp');
    const old = g.spaces[r.space] ?? { category: 'interior', label: r.id };
    const newSpace = {
      category: old.category,
      label: r.label?.zh || r.id,
      style: (old.style as string) || 'solid',
    };
    updateG((gg) => ({
      ...gg,
      spaces: { ...gg.spaces, [nid]: newSpace },
      rooms: gg.rooms.map((rr) =>
        rr.id === r.id ? { ...rr, space: nid, merge: undefined } : rr,
      ),
    }));
    deriveSoon();
    showToast(`已分隔 → 新 space ${nid}`);
  };

  return {
    onSetRoom,
    onSetLabel,
    onSetRect,
    onSetOp,
    onSetOpWall,
    onSetSpan,
    onDelOp,
    onSetFw,
    onSetFwSpan,
    onDelFw,
    onMerge,
    onSplit,
  };
}
