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
import { STROKE_SELECTED } from 'lib/floorplan/theme';
import RoomsLayer from './geometry/RoomsLayer';
import ResizeHandles from './geometry/ResizeHandles';
import OpeningMarker from './geometry/OpeningMarker';
import DerivedWallsLayer from './DerivedWallsLayer';
import FreeWallsLayer from './FreeWallsLayer';
import StageSvg from '../ui/StageSvg';

export interface EditorSelection {
  room: string | null;
  room2: string | null;
  opening: string | null;
  freeWall: string | null;
}

interface Props {
  svgRef: React.RefObject<SVGSVGElement>;
  contentRef?: React.Ref<SVGGElement>;
  contentTransform?: string;
  scale?: number;
  onWheel?: (e: WheelEvent) => void;
  onPointerDownCapture?: (e: React.PointerEvent) => void;
  onPointerMoveCapture?: (e: React.PointerEvent) => void;
  onPointerUpCapture?: (e: React.PointerEvent) => void;
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
  onSvgPointerCancel?: (e: React.PointerEvent) => void;
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
  contentRef,
  contentTransform,
  scale = 1,
  onWheel,
  onPointerDownCapture,
  onPointerMoveCapture,
  onPointerUpCapture,
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
  onSvgPointerCancel,
  onRoomPointerDown,
  onHandlePointerDown,
  onOpeningPointerDown,
  onWallPointerDown,
  onFreeWallPointerDown,
  furnitureOverlay,
}: Props) {
  const selectedRoom = roomById(geometry, selection.room);
  return (
    <StageSvg
      svgRef={svgRef}
      contentRef={contentRef}
      contentTransform={contentTransform}
      onWheel={onWheel}
      viewBox={viewBox}
      onPointerDown={onSvgPointerDown}
      onPointerMove={onSvgPointerMove}
      onPointerUp={onSvgPointerUp}
      onPointerCancel={onSvgPointerCancel}
      onPointerDownCapture={onPointerDownCapture}
      onPointerMoveCapture={onPointerMoveCapture}
      onPointerUpCapture={onPointerUpCapture}
    >
      {/* 1) 房间色块 */}
      <RoomsLayer
        rooms={geometry.rooms}
        origin={origin}
        scale={scale}
        selection={selection}
        errorRoomIds={errorRoomIds}
        onPointerDown={onRoomPointerDown}
      />

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
        scale={scale}
        selectedId={selection.freeWall}
        onPointerDown={onFreeWallPointerDown}
      />

      {/* 4) 开洞滑块 */}
      {(geometry.openings ?? []).map((op) => (
        <OpeningMarker
          key={op.id}
          opening={op}
          origin={origin}
          scale={scale}
          selected={selection.opening === op.id}
          onPointerDown={onOpeningPointerDown}
        />
      ))}

      {/* 5) 选中房间把手 */}
      {selectedRoom && (
        <ResizeHandles
          room={selectedRoom}
          origin={origin}
          scale={scale}
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
          fill={STROKE_SELECTED}
        />
      ))}
    </StageSvg>
  );
}
