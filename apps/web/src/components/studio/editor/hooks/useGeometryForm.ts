'use client';

import React from 'react';
import type { Geometry, Rect, Room } from 'lib/floorplan/types';
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

  // 新增房间 (P1-7): 画布两点拉矩形落点 (类比 ＋自由墙) 或无 rect 时落默认位。
  // 赋全新 space (独立空间), 任何与他房的净矩形重叠都被视为跨 space 重叠 ->
  // 由实时校验 (findOverlapErrors/errorRoomIds) 标红 + 禁存, 沿用既有重叠拦截。
  // 纯数据 push, 可经 undo 还原一帧; derive 重算墙。
  const onAddRoom = (rect?: Rect) => {
    const g = gRef.current;
    if (!g) return;
    // 默认位: 落在所有房下方 (避免无谓初始重叠); 无房则原点起。
    let r = rect;
    if (!r) {
      const minX = g.rooms.length
        ? Math.min(...g.rooms.map((rm) => rm.rect[0]))
        : 0;
      const maxY = g.rooms.length
        ? Math.max(...g.rooms.map((rm) => rm.rect[1] + rm.rect[3]))
        : 0;
      r = [minX, maxY + 20, 200, 150];
    }
    const spaceId = nextId('sp');
    const roomId = nextId('r');
    const newRoom: Room = {
      id: roomId,
      space: spaceId,
      type: 'bedroom',
      rect: r,
      label: { zh: '新房间' },
    };
    updateG((gg) => ({
      ...gg,
      spaces: {
        ...gg.spaces,
        [spaceId]: { category: 'interior', label: '新房间', style: 'solid' },
      },
      rooms: [...gg.rooms, newRoom],
    }));
    setSelection({
      room: roomId,
      room2: null,
      opening: null,
      freeWall: null,
    });
    deriveSoon();
  };

  // 删除选中房间 (Delete 键复用, 阶段 2)。纯数据 filter, 可经 undo 还原; derive 重算墙。
  const onDelRoom = () => {
    if (!selection.room) return;
    updateG((g) => ({
      ...g,
      rooms: g.rooms.filter((r) => r.id !== selection.room),
    }));
    setSelection({ room: null, room2: null, opening: null, freeWall: null });
    deriveSoon();
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
    onAddRoom,
    onDelRoom,
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
