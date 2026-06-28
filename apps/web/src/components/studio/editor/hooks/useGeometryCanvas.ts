'use client';

import React, { useCallback, useRef } from 'react';
import type {
  Geometry,
  DeriveResult,
  Room,
  Opening,
  FreeWall,
  WallRaw,
  Rect,
} from 'lib/floorplan/types';
import { readOrigin, readGrid, FALLBACK_ORIGIN } from 'lib/floorplan/coords';
import {
  roomById,
  computeMove,
  computeResize,
  computeOpeningSpan,
  hostExtent,
  buildDefaultDoor,
  buildFreeWall,
} from 'lib/floorplan/geometry';
import { type EditorSelection } from '../EditorStage';
import { isBackgroundTarget } from '../pointerUtils';

type Drag =
  | { type: 'move'; roomId: string; orig: Rect; sx: number; sy: number }
  | { type: 'resize'; roomId: string; orig: Rect; handle: string }
  | {
      type: 'op';
      opId: string;
      ospan: [number, number];
      s: number;
      host: [number, number] | null;
    };

const EMPTY_SELECTION: EditorSelection = {
  room: null,
  room2: null,
  opening: null,
  freeWall: null,
};

interface GeometryCanvasParams {
  gRef: React.MutableRefObject<Geometry | null>;
  derived: DeriveResult | null;
  insertMode: 'door' | 'freewall' | null;
  setInsertMode: React.Dispatch<
    React.SetStateAction<'door' | 'freewall' | null>
  >;
  setSelection: React.Dispatch<React.SetStateAction<EditorSelection>>;
  setFwPts: React.Dispatch<React.SetStateAction<Array<[number, number]>>>;
  updateG: (updater: (g: Geometry) => Geometry) => void;
  deriveSoon: () => void;
  showToast: (msg: string) => void;
  // 历史栈落点入栈支撑 (阶段 2): 拖拽开始/结束信号; 中间帧不入栈, 结束落一帧。
  beginDrag: () => void;
  endDrag: () => void;
}

// 几何画布交互 (§①-⑥): 坐标换算 + 指针拖拽 (拖房/8 把手缩放/门窗沿墙/点墙加门/
// 自由墙落点/背景清选)。dragRef/svgRef 内部持有, svgRef 上抛供 EditorStage 绑定。
export function useGeometryCanvas({
  gRef,
  derived,
  insertMode,
  setInsertMode,
  setSelection,
  setFwPts,
  updateG,
  deriveSoon,
  showToast,
  beginDrag,
  endDrag,
}: GeometryCanvasParams) {
  const svgRef = useRef<SVGSVGElement>(null);
  // 视口变换层 <g> 引用: getScreenCTM 取此 g (含 translate/scale), 缩放/平移下命中
  // 坐标自动正确 (阶段 1)。
  const contentRef = useRef<SVGGElement>(null);
  const dragRef = useRef<Drag | null>(null);

  // ---- 几何坐标换算 (§①) ---- //
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

  // ===== 指针交互 (§②③④⑤⑥) ===== //
  const onRoomPointerDown = (e: React.PointerEvent, room: Room) => {
    if (insertMode) return; // 插入模式下不拖房, 让事件冒泡到背景 (freewall 落点)
    e.stopPropagation();
    const pt = getGeoPoint(e);
    if (!pt) return;
    if (e.shiftKey) {
      setSelection((s) => ({ ...s, room2: room.id }));
    } else {
      setSelection({
        room: room.id,
        room2: null,
        opening: null,
        freeWall: null,
      });
    }
    dragRef.current = {
      type: 'move',
      roomId: room.id,
      orig: [...room.rect] as Rect,
      sx: pt.gx,
      sy: pt.gy,
    };
    beginDrag();
    svgRef.current?.setPointerCapture(e.pointerId);
  };

  const onHandlePointerDown = (
    e: React.PointerEvent,
    room: Room,
    handle: string,
  ) => {
    e.stopPropagation();
    setSelection({ room: room.id, room2: null, opening: null, freeWall: null });
    dragRef.current = {
      type: 'resize',
      roomId: room.id,
      orig: [...room.rect] as Rect,
      handle,
    };
    beginDrag();
    svgRef.current?.setPointerCapture(e.pointerId);
  };

  const onOpeningPointerDown = (e: React.PointerEvent, op: Opening) => {
    e.stopPropagation();
    setSelection({ room: null, room2: null, opening: op.id, freeWall: null });
    const pt = getGeoPoint(e);
    if (!pt) return;
    const s = op.wall.axis === 'v' ? pt.gy : pt.gx;
    const host = hostExtent(op, derived?._walls_raw);
    dragRef.current = {
      type: 'op',
      opId: op.id,
      ospan: [...op.wall.span] as [number, number],
      s,
      host,
    };
    beginDrag();
    svgRef.current?.setPointerCapture(e.pointerId);
  };

  // 开门模式: 点墙插默认门 (§⑤)
  const onWallPointerDown = (e: React.PointerEvent, wall: WallRaw) => {
    if (insertMode !== 'door') return;
    e.stopPropagation();
    const pt = getGeoPoint(e);
    if (!pt || !gRef.current) return;
    const coord = wall.axis === 'v' ? pt.gy : pt.gx;
    const door = buildDefaultDoor(gRef.current, wall, coord);
    updateG((g) => ({ ...g, openings: [...g.openings, door] }));
    setSelection({ room: null, room2: null, opening: door.id, freeWall: null });
    setInsertMode(null);
    deriveSoon();
  };

  const onFreeWallPointerDown = (e: React.PointerEvent, fw: FreeWall) => {
    e.stopPropagation();
    setSelection({ room: null, room2: null, opening: null, freeWall: fw.id });
  };

  // 背景: 自由墙落点 / 空白清选 (§⑥)
  const onSvgPointerDown = (e: React.PointerEvent) => {
    if (!isBackgroundTarget(e)) return;
    if (insertMode === 'freewall') {
      const pt = getGeoPoint(e);
      if (!pt) return;
      const grid = readGrid(gRef.current);
      const gx = Math.round(pt.gx / grid) * grid;
      const gy = Math.round(pt.gy / grid) * grid;
      setFwPts((prev) => {
        const next: Array<[number, number]> = [...prev, [gx, gy]];
        if (next.length === 2) {
          const fw = buildFreeWall(next[0], next[1]);
          if (fw) {
            updateG((g) => ({
              ...g,
              free_walls: [...(g.free_walls ?? []), fw],
            }));
            setSelection({
              room: null,
              room2: null,
              opening: null,
              freeWall: fw.id,
            });
            deriveSoon();
          } else {
            showToast('自由墙太短,已忽略');
          }
          setInsertMode(null);
          return [];
        }
        return next;
      });
      return;
    }
    setSelection(EMPTY_SELECTION);
  };

  const onSvgPointerMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const pt = getGeoPoint(e);
    if (!pt) return;
    const alt = e.altKey;
    if (d.type === 'move') {
      updateG((g) => {
        const room = roomById(g, d.roomId);
        if (!room) return g;
        const rect = computeMove(
          g,
          room,
          d.orig,
          pt.gx - d.sx,
          pt.gy - d.sy,
          alt,
        );
        return {
          ...g,
          rooms: g.rooms.map((r) => (r.id === d.roomId ? { ...r, rect } : r)),
        };
      });
    } else if (d.type === 'resize') {
      updateG((g) => {
        const room = roomById(g, d.roomId);
        if (!room) return g;
        const rect = computeResize(
          g,
          room,
          d.orig,
          d.handle,
          pt.gx,
          pt.gy,
          alt,
        );
        return {
          ...g,
          rooms: g.rooms.map((r) => (r.id === d.roomId ? { ...r, rect } : r)),
        };
      });
    } else {
      updateG((g) => {
        const op = g.openings.find((o) => o.id === d.opId);
        if (!op) return g;
        const cur = op.wall.axis === 'v' ? pt.gy : pt.gx;
        const span = computeOpeningSpan(op, d.ospan, d.s, cur, d.host);
        return {
          ...g,
          openings: g.openings.map((o) =>
            o.id === d.opId ? { ...o, wall: { ...o.wall, span } } : o,
          ),
        };
      });
    }
  };

  const onSvgPointerUp = () => {
    if (dragRef.current) {
      dragRef.current = null;
      deriveSoon();
    }
    endDrag(); // 落点入栈: 拖拽结束触发一帧 (内部自守卫, 无拖拽则空操作)。
  };

  // pointercancel: 复用 up 清理 (阶段 0), 防中断残留 dragRef。
  const onSvgPointerCancel = onSvgPointerUp;

  return {
    svgRef,
    contentRef,
    onSvgPointerDown,
    onSvgPointerCancel,
    onSvgPointerMove,
    onSvgPointerUp,
    onRoomPointerDown,
    onHandlePointerDown,
    onOpeningPointerDown,
    onWallPointerDown,
    onFreeWallPointerDown,
  };
}
