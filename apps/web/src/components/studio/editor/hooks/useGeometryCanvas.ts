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
  computeOpeningResize,
  computeFreeWallMove,
  hostExtent,
  buildDefaultDoor,
  buildFreeWall,
  buildRoomRect,
  rectSnapGuides,
  type SnapGuide,
} from 'lib/floorplan/geometry';
import type { DragHud } from 'lib/floorplan/overlay';
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
    }
  // 门窗端点拖宽 (P2-8): end 指定被拖端, 另一端固定; host 夹取寄主墙。
  | {
      type: 'opresize';
      opId: string;
      ospan: [number, number];
      end: 'lo' | 'hi';
      host: [number, number] | null;
    }
  // 自由墙整体平移 (P2-9): orig at/span + 起点几何坐标 (sx,sy)。
  | {
      type: 'fwmove';
      fwId: string;
      axis: 'h' | 'v';
      origAt: number;
      origSpan: [number, number];
      sx: number;
      sy: number;
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
  insertMode: 'door' | 'freewall' | 'room' | null;
  setInsertMode: React.Dispatch<
    React.SetStateAction<'door' | 'freewall' | 'room' | null>
  >;
  setSelection: React.Dispatch<React.SetStateAction<EditorSelection>>;
  setFwPts: React.Dispatch<React.SetStateAction<Array<[number, number]>>>;
  // 落点真值 (StrictMode 安全): 副作用在 updater 外按此 ref 执行一次。
  fwPtsRef: React.MutableRefObject<Array<[number, number]>>;
  updateG: (updater: (g: Geometry) => Geometry) => void;
  deriveSoon: () => void;
  showToast: (msg: string) => void;
  // 画布两点拉矩形落新房 (P1-7): 复用 form.onAddRoom (赋默认 space/type + 校验)。
  addRoom: (rect: Rect) => void;
  // 历史栈落点入栈支撑 (阶段 2): 拖拽开始/结束信号; 中间帧不入栈, 结束落一帧。
  beginDrag: () => void;
  endDrag: () => void;
  // 拖拽期可视反馈 (阶段 3 / P1-4): 吸附对齐线 + 实时尺寸 HUD; 松手清空。
  setSnapGuides: React.Dispatch<React.SetStateAction<SnapGuide[]>>;
  setDragHud: React.Dispatch<React.SetStateAction<DragHud | null>>;
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
  fwPtsRef,
  updateG,
  deriveSoon,
  showToast,
  addRoom,
  beginDrag,
  endDrag,
  setSnapGuides,
  setDragHud,
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
  // 注: 交互句柄一律 useCallback (阶段 3 / P2-1): 透传给 React.memo 化的图元后引用
  // 稳定 (拖拽期依赖项不变), 使非拖拽元素跳过重渲。
  const onRoomPointerDown = useCallback(
    (e: React.PointerEvent, room: Room) => {
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
    },
    [insertMode, getGeoPoint, setSelection, beginDrag],
  );

  const onHandlePointerDown = useCallback(
    (e: React.PointerEvent, room: Room, handle: string) => {
      e.stopPropagation();
      setSelection({
        room: room.id,
        room2: null,
        opening: null,
        freeWall: null,
      });
      dragRef.current = {
        type: 'resize',
        roomId: room.id,
        orig: [...room.rect] as Rect,
        handle,
      };
      beginDrag();
      svgRef.current?.setPointerCapture(e.pointerId);
    },
    [setSelection, beginDrag],
  );

  const onOpeningPointerDown = useCallback(
    (e: React.PointerEvent, op: Opening) => {
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
    },
    [getGeoPoint, setSelection, derived, beginDrag],
  );

  // 门窗端点把手拖宽 (P2-8): end='lo'|'hi'; 夹取寄主墙 hostExtent + 保最小宽。
  const onOpeningHandlePointerDown = useCallback(
    (e: React.PointerEvent, op: Opening, end: 'lo' | 'hi') => {
      e.stopPropagation();
      setSelection({ room: null, room2: null, opening: op.id, freeWall: null });
      const host = hostExtent(op, derived?._walls_raw);
      dragRef.current = {
        type: 'opresize',
        opId: op.id,
        ospan: [...op.wall.span] as [number, number],
        end,
        host,
      };
      beginDrag();
      svgRef.current?.setPointerCapture(e.pointerId);
    },
    [setSelection, derived, beginDrag],
  );

  // 门窗画布翻转 (P2-8): 平开门翻 hinge (lo<->hi), 推拉/窗翻 swing (+/-)。入历史一帧。
  const onOpeningFlip = useCallback(
    (op: Opening) => {
      updateG((g) => ({
        ...g,
        openings: g.openings.map((o) => {
          if (o.id !== op.id) return o;
          if (o.kind === 'door' && (o.door_type ?? 'swing') !== 'sliding') {
            return { ...o, hinge: o.hinge === 'hi' ? 'lo' : 'hi' };
          }
          return { ...o, swing: o.swing === '-' ? '+' : '-' };
        }),
      }));
      deriveSoon();
    },
    [updateG, deriveSoon],
  );

  // 开门模式: 点墙插默认门 (§⑤)
  const onWallPointerDown = useCallback(
    (e: React.PointerEvent, wall: WallRaw) => {
      if (insertMode !== 'door') return;
      e.stopPropagation();
      const pt = getGeoPoint(e);
      if (!pt || !gRef.current) return;
      const coord = wall.axis === 'v' ? pt.gy : pt.gx;
      const door = buildDefaultDoor(gRef.current, wall, coord);
      updateG((g) => ({ ...g, openings: [...g.openings, door] }));
      setSelection({
        room: null,
        room2: null,
        opening: door.id,
        freeWall: null,
      });
      setInsertMode(null);
      deriveSoon();
    },
    [
      insertMode,
      getGeoPoint,
      gRef,
      updateG,
      setSelection,
      setInsertMode,
      deriveSoon,
    ],
  );

  // 自由墙: 选中 + 整体拖动平移 (P2-9)。插入模式下仅选不拖 (留给落点流程)。
  const onFreeWallPointerDown = useCallback(
    (e: React.PointerEvent, fw: FreeWall) => {
      e.stopPropagation();
      setSelection({ room: null, room2: null, opening: null, freeWall: fw.id });
      if (insertMode) return;
      const pt = getGeoPoint(e);
      if (!pt) return;
      dragRef.current = {
        type: 'fwmove',
        fwId: fw.id,
        axis: fw.axis,
        origAt: fw.at,
        origSpan: [...fw.span] as [number, number],
        sx: pt.gx,
        sy: pt.gy,
      };
      beginDrag();
      svgRef.current?.setPointerCapture(e.pointerId);
    },
    [insertMode, getGeoPoint, setSelection, beginDrag],
  );

  // 背景 / 落点 (§⑥ + P1-7): 自由墙 / 新房两点落点 / 空白清选。
  // 插入模式 (freewall/room) 下放宽命中: 房块在插入模式不 stopPropagation, 事件冒泡
  // 至此; 故第二点可落在已有房之上 (用于拉出跨 space 重叠房验证拦截)。
  // 落点逻辑走 fwPtsRef (而非 setFwPts 的函数式 updater): React18 StrictMode 会对
  // updater 双调用, 若把 buildFreeWall/addRoom 等副作用置于 updater 内会重复落两次。
  // 此处副作用在 updater 外执行一次, setFwPts 仅传纯值 (镜像给画布画落点圆)。
  const onSvgPointerDown = (e: React.PointerEvent) => {
    if (insertMode === 'freewall' || insertMode === 'room') {
      const pt = getGeoPoint(e);
      if (!pt) return;
      const grid = readGrid(gRef.current);
      const gx = Math.round(pt.gx / grid) * grid;
      const gy = Math.round(pt.gy / grid) * grid;
      const next: Array<[number, number]> = [...fwPtsRef.current, [gx, gy]];
      if (next.length < 2) {
        fwPtsRef.current = next;
        setFwPts(next);
        return;
      }
      // 第二点: 落元素 (一次性副作用)。
      if (insertMode === 'freewall') {
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
      } else {
        const rect = buildRoomRect(next[0], next[1]);
        if (rect) addRoom(rect);
        else showToast('房间太小,已忽略');
      }
      fwPtsRef.current = [];
      setFwPts([]);
      setInsertMode(null);
      return;
    }
    if (!isBackgroundTarget(e)) return;
    setSelection(EMPTY_SELECTION);
  };

  // 拖拽移动 (阶段 3): 先据当前 gRef 算出新值 (吸附结果与之前完全一致), 再 updateG +
  // 产出辅助线/尺寸 HUD。计算与提交分离, 不改吸附数值。
  const onSvgPointerMove = useCallback(
    (e: React.PointerEvent) => {
      const d = dragRef.current;
      if (!d) return;
      const pt = getGeoPoint(e);
      const g = gRef.current;
      if (!pt || !g) return;
      const alt = e.altKey;
      if (d.type === 'move') {
        const room = roomById(g, d.roomId);
        if (!room) return;
        const rect = computeMove(
          g,
          room,
          d.orig,
          pt.gx - d.sx,
          pt.gy - d.sy,
          alt,
        );
        updateG((gg) => ({
          ...gg,
          rooms: gg.rooms.map((r) => (r.id === d.roomId ? { ...r, rect } : r)),
        }));
        setSnapGuides(alt ? [] : rectSnapGuides(g, room, rect));
        setDragHud({
          x: rect[0] + rect[2] / 2,
          y: rect[1],
          text: `${Math.round(rect[2])} × ${Math.round(rect[3])}`,
        });
      } else if (d.type === 'resize') {
        const room = roomById(g, d.roomId);
        if (!room) return;
        const rect = computeResize(
          g,
          room,
          d.orig,
          d.handle,
          pt.gx,
          pt.gy,
          alt,
        );
        updateG((gg) => ({
          ...gg,
          rooms: gg.rooms.map((r) => (r.id === d.roomId ? { ...r, rect } : r)),
        }));
        setSnapGuides(alt ? [] : rectSnapGuides(g, room, rect));
        setDragHud({
          x: rect[0] + rect[2] / 2,
          y: rect[1],
          text: `${Math.round(rect[2])} × ${Math.round(rect[3])}`,
        });
      } else if (d.type === 'op') {
        const op = g.openings.find((o) => o.id === d.opId);
        if (!op) return;
        const cur = op.wall.axis === 'v' ? pt.gy : pt.gx;
        const span = computeOpeningSpan(op, d.ospan, d.s, cur, d.host);
        updateG((gg) => ({
          ...gg,
          openings: gg.openings.map((o) =>
            o.id === d.opId ? { ...o, wall: { ...o.wall, span } } : o,
          ),
        }));
        const mid = (span[0] + span[1]) / 2;
        setDragHud(
          op.wall.axis === 'v'
            ? {
                x: op.wall.at,
                y: mid,
                text: `${Math.round(span[1] - span[0])}`,
              }
            : {
                x: mid,
                y: op.wall.at,
                text: `${Math.round(span[1] - span[0])}`,
              },
        );
      } else if (d.type === 'opresize') {
        // 端点拖宽 (P2-8): 改 span, 夹取寄主墙 + 最小宽; HUD 显宽度。
        const op = g.openings.find((o) => o.id === d.opId);
        if (!op) return;
        const cur = op.wall.axis === 'v' ? pt.gy : pt.gx;
        const span = computeOpeningResize(d.ospan, d.end, cur, d.host);
        updateG((gg) => ({
          ...gg,
          openings: gg.openings.map((o) =>
            o.id === d.opId ? { ...o, wall: { ...o.wall, span } } : o,
          ),
        }));
        const mid = (span[0] + span[1]) / 2;
        setDragHud(
          op.wall.axis === 'v'
            ? {
                x: op.wall.at,
                y: mid,
                text: `${Math.round(span[1] - span[0])}`,
              }
            : {
                x: mid,
                y: op.wall.at,
                text: `${Math.round(span[1] - span[0])}`,
              },
        );
      } else {
        // 自由墙整体平移 (P2-9): 改 at/span, 网格吸附; HUD 显 at。
        const fw = (g.free_walls ?? []).find((f) => f.id === d.fwId);
        if (!fw) return;
        const { at, span } = computeFreeWallMove(
          d.axis,
          d.origAt,
          d.origSpan,
          pt.gx - d.sx,
          pt.gy - d.sy,
        );
        updateG((gg) => ({
          ...gg,
          free_walls: (gg.free_walls ?? []).map((f) =>
            f.id === d.fwId ? { ...f, at, span } : f,
          ),
        }));
        const mid = (span[0] + span[1]) / 2;
        setDragHud(
          d.axis === 'v'
            ? { x: at, y: mid, text: `at ${Math.round(at)}` }
            : { x: mid, y: at, text: `at ${Math.round(at)}` },
        );
      }
    },
    [getGeoPoint, gRef, updateG, setSnapGuides, setDragHud],
  );

  const onSvgPointerUp = useCallback(() => {
    if (dragRef.current) {
      dragRef.current = null;
      deriveSoon();
    }
    setSnapGuides([]); // 松手清除可视反馈 (P1-4)。
    setDragHud(null);
    endDrag(); // 落点入栈: 拖拽结束触发一帧 (内部自守卫, 无拖拽则空操作)。
  }, [deriveSoon, endDrag, setSnapGuides, setDragHud]);

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
    onOpeningHandlePointerDown,
    onOpeningFlip,
    onWallPointerDown,
    onFreeWallPointerDown,
  };
}
