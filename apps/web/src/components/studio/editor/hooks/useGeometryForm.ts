'use client';

import React from 'react';
import type { Geometry, Rect, Room, UnderlayMeta } from 'lib/floorplan/types';
import {
  roomById,
  crossSpaceOverlap,
  adjacentMergeCandidates,
} from 'lib/floorplan/geometry';
import {
  largestRoomId,
  mergeIntoTarget,
  pruneOrphanSpaces,
  roomDisplayName,
  seamOpenings,
  type MergePick,
  type MergeResult,
} from 'lib/floorplan/merge';
import { nextId } from 'lib/floorplan/ids';
import { type EditorSelection } from '../EditorStage';

interface GeometryFormParams {
  selection: EditorSelection;
  setSelection: React.Dispatch<React.SetStateAction<EditorSelection>>;
  gRef: React.MutableRefObject<Geometry | null>;
  updateG: (updater: (g: Geometry) => Geometry) => void;
  deriveSoon: () => void;
  showToast: (msg: string) => void;
  // 贴合并房点选目标 (CP5v2): 状态由 useGeometryEditor 持有, 此处只读 ref + 写入。
  mergePickRef: React.MutableRefObject<MergePick | null>;
  setMergePick: (v: MergePick | null) => void;
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
  mergePickRef,
  setMergePick,
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

  // 墙面材质标注 (P1 材质A): rooms[].walls[side].material; 清空值删键, 全空删 walls。
  const onSetWallFinish = (side: 'N' | 'S' | 'E' | 'W', material: string) => {
    if (!selection.room) return;
    updateG((g) => ({
      ...g,
      rooms: g.rooms.map((r) => {
        if (r.id !== selection.room) return r;
        const walls = { ...((r.walls as Record<string, unknown>) ?? {}) };
        if (material) walls[side] = { ...(walls[side] as object), material };
        else {
          // 清空材质但保留已贴实拍参考图 (photo_id): 只删 material 键。
          const cur = { ...((walls[side] as Record<string, unknown>) ?? {}) };
          delete cur.material;
          if (Object.keys(cur).length) walls[side] = cur;
          else delete walls[side];
        }
        const next = { ...r } as typeof r;
        if (Object.keys(walls).length)
          (next as Record<string, unknown>).walls = walls;
        else delete (next as Record<string, unknown>).walls;
        return next;
      }),
    }));
  };

  // 墙面实拍材质 (P2 材质C): rooms[].walls[side].photo_id; 空值删键, 保留 material。
  const onSetWallPhoto = (side: 'N' | 'S' | 'E' | 'W', photoId: string) => {
    if (!selection.room) return;
    updateG((g) => ({
      ...g,
      rooms: g.rooms.map((r) => {
        if (r.id !== selection.room) return r;
        const walls = { ...((r.walls as Record<string, unknown>) ?? {}) };
        const cur = { ...((walls[side] as Record<string, unknown>) ?? {}) };
        if (photoId) cur.photo_id = photoId;
        else delete cur.photo_id;
        if (Object.keys(cur).length) walls[side] = cur;
        else delete walls[side];
        const next = { ...r } as typeof r;
        if (Object.keys(walls).length)
          (next as Record<string, unknown>).walls = walls;
        else delete (next as Record<string, unknown>).walls;
        return next;
      }),
    }));
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
      rooms: [roomId],
      room2: null,
      opening: null,
      freeWall: null,
    });
    deriveSoon();
  };

  // L形房落点 (P4 CP6): 两矩形拼一个 L, 共享【同一 space + 同一 merge 组】-> 内缝自动消隐,
  // 下游按逻辑房聚合 (P3)。仅首块给 label (单标签); type 默认 living (L 形多为开放起居)。
  const onAddLShape = (rectA: Rect, rectB: Rect) => {
    if (!gRef.current) return;
    const spaceId = nextId('sp');
    const mergeId = nextId('m');
    const idA = nextId('r');
    const idB = nextId('r');
    const roomA: Room = {
      id: idA,
      space: spaceId,
      type: 'living',
      rect: rectA,
      label: { zh: 'L形房' },
      merge: mergeId,
    };
    const roomB: Room = {
      id: idB,
      space: spaceId,
      type: 'living',
      rect: rectB,
      merge: mergeId,
    };
    updateG((gg) => ({
      ...gg,
      spaces: {
        ...gg.spaces,
        [spaceId]: { category: 'interior', label: 'L形房', style: 'solid' },
      },
      rooms: [...gg.rooms, roomA, roomB],
    }));
    setSelection({
      room: idA,
      rooms: [idA, idB],
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
    setSelection({
      room: null,
      rooms: [],
      room2: null,
      opening: null,
      freeWall: null,
    });
    deriveSoon();
  };

  const onSetOp = (field: string, value: string | boolean) => {
    if (!selection.opening) return;
    updateG((g) => ({
      ...g,
      openings: g.openings.map((o) => {
        if (o.id !== selection.opening) return o;
        // 空串 = 清除该可选键 (P5: 门材质=wood 默认时不写 material 键, 保盘上字节不变)。
        if (value === '') {
          const next = { ...o } as Record<string, unknown>;
          delete next[field];
          return next as typeof o;
        }
        return { ...o, [field]: value };
      }),
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

  // 合并边界洞提醒: 该边并房后消隐, cut 洞悬空会被引擎校验 ERROR 拒存 (D12)。
  const seamWarn = (g: Geometry, res: MergeResult): string => {
    const seams = seamOpenings(g, res.moved, res.groupIds);
    if (!seams.length) return '';
    return `；⚠ ${seams
      .map((o) => o.id)
      .join('、')} 位于合并边界，保存前请处理`;
  };

  // 并房落地 (CP5v2): source 整组并入 target 的 space + merge 组 (space 归目标房),
  // 记 prev_space 快照 + 清孤儿 space。完成后主选被并房 —— 紧接「分隔」即走
  // prev_space 还原回路。
  const applyMergeInto = (sourceId: string, targetId: string) => {
    const g = gRef.current;
    if (!g) return;
    const res = mergeIntoTarget(g, [sourceId], targetId);
    if (!res) {
      showToast('无可并入的房间(可能已同组)');
      return;
    }
    const warn = seamWarn(g, res);
    updateG(() => res.g);
    setSelection({
      room: res.moved.includes(sourceId) ? sourceId : res.moved[0],
      rooms: res.groupIds,
      room2: null,
      opening: null,
      freeWall: null,
    });
    deriveSoon();
    showToast(
      `已并入 ${roomDisplayName(res.g, roomById(res.g, targetId))}（组 ${
        res.groupId
      }）${warn}`,
    );
  };

  // 被并房名单文案: 取并房前几何 (名称还未随组改变), 过长截断保持一行可读。
  const movedNames = (g: Geometry, ids: string[]): string => {
    const names = ids.map((id) => roomDisplayName(g, roomById(g, id)));
    if (names.length <= 3) return names.join('、');
    return `${names.slice(0, 2).join('、')} 等 ${names.length} 房`;
  };

  // 打通 (CP5v2 语义对齐): 其余选中房整组并入目标房 —— 目标 = Shift+点的第二房
  // (room2); 无 room2 (框选/全选) 取面积最大者 (平局最小 id, 与代表房规则一致)。
  // space 归目标房, toast 明示谁并入谁。完成后主选被并房 (分隔还原回路)。
  const onMerge = () => {
    const ids =
      selection.rooms.length >= 2
        ? selection.rooms
        : selection.room && selection.room2
        ? [selection.room, selection.room2]
        : [];
    if (ids.length < 2) {
      showToast('需先选两个房间(Shift+点第二个)');
      return;
    }
    const g = gRef.current;
    if (!g) return;
    const targetId =
      selection.room2 && ids.includes(selection.room2)
        ? selection.room2
        : largestRoomId(g, ids);
    if (!targetId) return;
    const sources = ids.filter((id) => id !== targetId);
    const res = mergeIntoTarget(g, sources, targetId);
    if (!res) {
      showToast('无可并入的房间(可能已同组)');
      return;
    }
    const warn = seamWarn(g, res);
    const moved = movedNames(g, res.moved);
    updateG(() => res.g);
    setSelection({
      room: res.moved[0],
      rooms: res.groupIds,
      room2: null,
      opening: null,
      freeWall: null,
    });
    deriveSoon();
    showToast(
      `已打通: ${moved} 并入 ${roomDisplayName(
        res.g,
        roomById(res.g, targetId),
      )}（组 ${res.groupId}）${warn}`,
    );
  };

  // 贴合并房 (CP5v2 重做): 选一房 -> 相邻候选 (共一条边、未同组); 唯一候选直接并入
  // 该邻居; 多候选进入画布点选模式 (候选高亮, 点击指定目标, Esc/点空白取消)。
  // 按钮再点一次 = 退出点选。
  const onSuggestMerge = () => {
    if (mergePickRef.current) {
      setMergePick(null);
      showToast('已退出贴合并房点选');
      return;
    }
    if (!selection.room) {
      showToast('需先选一个房间');
      return;
    }
    const g = gRef.current;
    if (!g) return;
    const r = roomById(g, selection.room);
    if (!r) return;
    const cands = adjacentMergeCandidates(g, r);
    if (!cands.length) {
      showToast('该房无相邻可并房间');
      return;
    }
    if (cands.length === 1) {
      applyMergeInto(r.id, cands[0].id);
      return;
    }
    setMergePick({ source: r.id, candidates: cands.map((c) => c.id) });
    showToast(`${cands.length} 个相邻房间已高亮，点击要并入的目标（Esc 取消）`);
  };

  // 分隔 (CP5v2): 优先按 prev_space 快照还原并房前的名称/类别, 且复用原 space id
  // (开洞 between 引用随之保持一致); 无快照按现 space 拷贝到全新 space。
  // 拆出后清孤儿 space。拆后若仍重叠, 实时校验报 ERROR。
  const onSplit = () => {
    if (!selection.room) {
      showToast('需先选一个房间');
      return;
    }
    const g = gRef.current;
    if (!g) return;
    const r = roomById(g, selection.room);
    if (!r) return;
    const prev = r.prev_space;
    const nid = prev?.id || nextId('sp');
    const old = g.spaces[r.space] ?? { category: 'interior', label: r.id };
    // 原 space 条目若因开洞 between 引用被保留, 直接复用其定义 (即原始真值)。
    const newSpace =
      g.spaces[nid] ??
      (prev
        ? {
            category: prev.category,
            label: prev.label,
            style: prev.style ?? 'solid',
          }
        : {
            category: old.category,
            label: r.label?.zh || r.id,
            style: (old.style as string) || 'solid',
          });
    updateG((gg) =>
      pruneOrphanSpaces({
        ...gg,
        spaces: { ...gg.spaces, [nid]: newSpace },
        rooms: gg.rooms.map((rr) => {
          if (rr.id !== r.id) return rr;
          const next = { ...rr, space: nid } as Room;
          delete next.merge;
          delete next.prev_space;
          return next;
        }),
      }),
    );
    deriveSoon();
    showToast(
      prev
        ? `已分隔 → 还原为「${prev.label}」(space ${nid})`
        : `已分隔 → 新 space ${nid}`,
    );
  };

  // 底图描摹 (P6): 写/清 meta.underlay。引擎不读该键 -> 不影响出图字节, 随几何保存持久化。
  const onSetUnderlay = (patch: Partial<UnderlayMeta>) => {
    updateG((g) => {
      const cur: UnderlayMeta = g.meta.underlay ?? {
        opacity: 0.5,
        scale: 1,
        dx: 0,
        dy: 0,
      };
      const next: UnderlayMeta = { ...cur, ...patch };
      return { ...g, meta: { ...g.meta, underlay: next } };
    });
  };

  const onClearUnderlay = () => {
    updateG((g) => {
      const meta = { ...g.meta };
      delete meta.underlay;
      return { ...g, meta };
    });
  };

  return {
    onSetRoom,
    onSetWallFinish,
    onSetWallPhoto,
    onSetUnderlay,
    onClearUnderlay,
    onSetLabel,
    onSetRect,
    onAddRoom,
    onAddLShape,
    onDelRoom,
    onSetOp,
    onSetOpWall,
    onSetSpan,
    onDelOp,
    onSetFw,
    onSetFwSpan,
    onDelFw,
    onMerge,
    onSuggestMerge,
    onSplit,
    applyMergeInto,
  };
}
