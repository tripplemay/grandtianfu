'use client';

import React from 'react';
import type { Geometry, DeriveResult } from 'lib/floorplan/types';
import type { Furniture } from 'lib/floorplan/furniture';
import type { SnapGuide } from 'lib/floorplan/geometry';
import type { DragHud } from 'lib/floorplan/overlay';
import type { Marquee } from '../hooks/useGeometryCanvas';
import DerivedWallsLayer from '../DerivedWallsLayer';
import RoomsLayer from '../geometry/RoomsLayer';
import FurnitureLayer from './FurnitureLayer';
import FurnitureHandles from './FurnitureHandles';
import GuideLayer from '../overlay/GuideLayer';
import MarqueeLayer from '../overlay/MarqueeLayer';
import StageSvg from '../../ui/StageSvg';

interface Props {
  svgRef: React.RefObject<SVGSVGElement>;
  contentRef?: React.Ref<SVGGElement>;
  contentTransform?: string;
  scale?: number;
  dragging?: boolean;
  snapGuides?: SnapGuide[];
  dragHud?: DragHud | null;
  onWheel?: (e: WheelEvent) => void;
  onPointerDownCapture?: (e: React.PointerEvent) => void;
  onPointerMoveCapture?: (e: React.PointerEvent) => void;
  onPointerUpCapture?: (e: React.PointerEvent) => void;
  onPointerCancelCapture?: (e: React.PointerEvent) => void;
  viewBox: [number, number, number, number];
  origin: [number, number];
  geometry: Geometry;
  derived: DeriveResult | null;
  furniture: Furniture[];
  // 多选集合 (阶段 5a / P2-7)。把手仅 N=1 时显示。
  selectedIds: string[];
  marquee?: Marquee | null;
  blockedId?: string | null;
  onSvgPointerDown: (e: React.PointerEvent) => void;
  onSvgPointerMove: (e: React.PointerEvent) => void;
  onSvgPointerUp: (e: React.PointerEvent) => void;
  onSvgPointerCancel?: (e: React.PointerEvent) => void;
  onItemPointerDown: (e: React.PointerEvent, id: string) => void;
  onResizeDown: (e: React.PointerEvent, handle: string) => void;
  onRotateDown: (e: React.PointerEvent) => void;
}

const noopWall = () => undefined;

// 家具模式画布: 几何 (房间色块 + 派生墙) 作淡色背景参考, 家具层可交互拖拽。
export default function FurnitureStage({
  svgRef,
  contentRef,
  contentTransform,
  scale = 1,
  dragging = false,
  snapGuides = [],
  dragHud = null,
  onWheel,
  onPointerDownCapture,
  onPointerMoveCapture,
  onPointerUpCapture,
  onPointerCancelCapture,
  viewBox,
  origin,
  geometry,
  derived,
  furniture,
  selectedIds,
  marquee,
  blockedId,
  onSvgPointerDown,
  onSvgPointerMove,
  onSvgPointerUp,
  onSvgPointerCancel,
  onItemPointerDown,
  onResizeDown,
  onRotateDown,
}: Props) {
  // 缩放/旋转把手仅在恰好选中 1 件时显示 (多选不出把手, N=1 行为不变)。
  const handleId = selectedIds.length === 1 ? selectedIds[0] : null;
  const selectedItem =
    handleId != null ? furniture.find((f) => f.id === handleId) ?? null : null;
  return (
    <StageSvg
      svgRef={svgRef}
      contentRef={contentRef}
      contentTransform={contentTransform}
      scale={scale}
      dragging={dragging}
      onWheel={onWheel}
      viewBox={viewBox}
      onPointerDown={onSvgPointerDown}
      onPointerMove={onSvgPointerMove}
      onPointerUp={onSvgPointerUp}
      onPointerCancel={onSvgPointerCancel}
      onPointerDownCapture={onPointerDownCapture}
      onPointerMoveCapture={onPointerMoveCapture}
      onPointerUpCapture={onPointerUpCapture}
      onPointerCancelCapture={onPointerCancelCapture}
    >
      {/* 几何参考层 (淡色只读) */}
      <g opacity={0.35} style={{ pointerEvents: 'none' }}>
        <RoomsLayer rooms={geometry.rooms} origin={origin} readOnly />
        <DerivedWallsLayer
          derived={derived}
          origin={origin}
          doorInsertMode={false}
          onWallDown={noopWall}
        />
      </g>

      {/* 家具层 (可交互) */}
      <FurnitureLayer
        furniture={furniture}
        geometry={geometry}
        origin={origin}
        scale={scale}
        selectedIds={selectedIds}
        blockedId={blockedId}
        onItemPointerDown={onItemPointerDown}
      />

      {/* 选中件: 缩放手柄 (P2-3) + 旋转柄 (P2-2) */}
      {selectedItem && (
        <FurnitureHandles
          item={selectedItem}
          geometry={geometry}
          origin={origin}
          scale={scale}
          onResizeDown={onResizeDown}
          onRotateDown={onRotateDown}
        />
      )}

      {/* 拖拽期可视反馈 (P1-4): 对齐线 + 实时尺寸 HUD */}
      <GuideLayer
        guides={snapGuides}
        hud={dragHud}
        origin={origin}
        scale={scale}
      />

      {/* 框选 marquee (阶段 5a / P2-7) */}
      <MarqueeLayer marquee={marquee ?? null} origin={origin} scale={scale} />
    </StageSvg>
  );
}
