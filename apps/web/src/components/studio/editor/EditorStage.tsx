'use client';

import React from 'react';
import type {
  Geometry,
  DeriveResult,
  Room,
  Opening,
  FreeWall,
  WallRaw,
} from 'lib/floorplan/types';
import { roomById } from 'lib/floorplan/geometry';
import RoomRect from './geometry/RoomRect';
import ResizeHandles from './geometry/ResizeHandles';
import OpeningMarker from './geometry/OpeningMarker';
import DerivedWallsLayer from './DerivedWallsLayer';
import FreeWallsLayer from './FreeWallsLayer';

export interface EditorSelection {
  room: string | null;
  room2: string | null;
  opening: string | null;
  freeWall: string | null;
}

interface Props {
  svgRef: React.RefObject<SVGSVGElement>;
  viewBox: [number, number, number, number];
  origin: [number, number];
  geometry: Geometry;
  derived: DeriveResult | null;
  selection: EditorSelection;
  insertMode: 'door' | 'freewall' | null;
  fwPts: Array<[number, number]>;
  errorRoomIds: Set<string>;
  onSvgPointerDown: (e: React.PointerEvent) => void;
  onSvgPointerMove: (e: React.PointerEvent) => void;
  onSvgPointerUp: (e: React.PointerEvent) => void;
  onRoomPointerDown: (e: React.PointerEvent, room: Room) => void;
  onHandlePointerDown: (
    e: React.PointerEvent,
    room: Room,
    handle: string,
  ) => void;
  onOpeningPointerDown: (e: React.PointerEvent, op: Opening) => void;
  onWallPointerDown: (e: React.PointerEvent, wall: WallRaw) => void;
  onFreeWallPointerDown: (e: React.PointerEvent, fw: FreeWall) => void;
  furnitureOverlay?: React.ReactNode; // 家具淡色只读参考层 (B2, 几何模式叠加)。
}

// 受控 inline SVG (非 canvas, 红线)。viewBox=meta.canvas_viewbox。
export default function EditorStage({
  svgRef,
  viewBox,
  origin,
  geometry,
  derived,
  selection,
  insertMode,
  fwPts,
  errorRoomIds,
  onSvgPointerDown,
  onSvgPointerMove,
  onSvgPointerUp,
  onRoomPointerDown,
  onHandlePointerDown,
  onOpeningPointerDown,
  onWallPointerDown,
  onFreeWallPointerDown,
  furnitureOverlay,
}: Props) {
  const selectedRoom = roomById(geometry, selection.room);
  return (
    <svg
      ref={svgRef}
      viewBox={viewBox.join(' ')}
      xmlns="http://www.w3.org/2000/svg"
      className="block h-auto w-full touch-none select-none"
      style={{ background: '#0b1437' }}
      onPointerDown={onSvgPointerDown}
      onPointerMove={onSvgPointerMove}
      onPointerUp={onSvgPointerUp}
    >
      {/* 背景捕获层: 空白点击 = 清选 / 自由墙落点 */}
      <rect
        data-bg="1"
        x={viewBox[0]}
        y={viewBox[1]}
        width={viewBox[2]}
        height={viewBox[3]}
        fill="transparent"
      />

      {/* 1) 房间色块 */}
      {geometry.rooms.map((r) => (
        <RoomRect
          key={r.id}
          room={r}
          origin={origin}
          selected={selection.room === r.id || selection.room2 === r.id}
          error={errorRoomIds.has(r.id)}
          onPointerDown={onRoomPointerDown}
        />
      ))}

      {/* 2) 派生墙 / 窗 / 门 */}
      <DerivedWallsLayer
        derived={derived}
        origin={origin}
        doorInsertMode={insertMode === 'door'}
        onWallDown={onWallPointerDown}
      />

      {/* 3) 自由墙 */}
      <FreeWallsLayer
        freeWalls={geometry.free_walls ?? []}
        origin={origin}
        selectedId={selection.freeWall}
        onPointerDown={onFreeWallPointerDown}
      />

      {/* 4) 开洞滑块 */}
      {(geometry.openings ?? []).map((op) => (
        <OpeningMarker
          key={op.id}
          opening={op}
          origin={origin}
          selected={selection.opening === op.id}
          onPointerDown={onOpeningPointerDown}
        />
      ))}

      {/* 5) 选中房间把手 */}
      {selectedRoom && (
        <ResizeHandles
          room={selectedRoom}
          origin={origin}
          onHandleDown={onHandlePointerDown}
        />
      )}

      {/* 家具淡色只读参考层 (B2) */}
      {furnitureOverlay}

      {/* 6) 自由墙临时落点 */}
      {fwPts.map((p, i) => (
        <circle
          key={i}
          cx={p[0] + origin[0]}
          cy={p[1] + origin[1]}
          r={5}
          fill="#e0701a"
        />
      ))}
    </svg>
  );
}
