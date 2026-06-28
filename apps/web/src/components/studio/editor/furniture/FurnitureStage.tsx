'use client';

import React from 'react';
import type { Geometry, DeriveResult } from 'lib/floorplan/types';
import type { Furniture } from 'lib/floorplan/furniture';
import type { SnapGuide } from 'lib/floorplan/geometry';
import type { DragHud } from 'lib/floorplan/overlay';
import DerivedWallsLayer from '../DerivedWallsLayer';
import RoomsLayer from '../geometry/RoomsLayer';
import FurnitureLayer from './FurnitureLayer';
import GuideLayer from '../overlay/GuideLayer';
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
  viewBox: [number, number, number, number];
  origin: [number, number];
  geometry: Geometry;
  derived: DeriveResult | null;
  furniture: Furniture[];
  selectedId: string | null;
  onSvgPointerDown: (e: React.PointerEvent) => void;
  onSvgPointerMove: (e: React.PointerEvent) => void;
  onSvgPointerUp: (e: React.PointerEvent) => void;
  onSvgPointerCancel?: (e: React.PointerEvent) => void;
  onItemPointerDown: (e: React.PointerEvent, id: string) => void;
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
  viewBox,
  origin,
  geometry,
  derived,
  furniture,
  selectedId,
  onSvgPointerDown,
  onSvgPointerMove,
  onSvgPointerUp,
  onSvgPointerCancel,
  onItemPointerDown,
}: Props) {
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
        selectedId={selectedId}
        onItemPointerDown={onItemPointerDown}
      />

      {/* 拖拽期可视反馈 (P1-4): 对齐线 + 实时尺寸 HUD */}
      <GuideLayer
        guides={snapGuides}
        hud={dragHud}
        origin={origin}
        scale={scale}
      />
    </StageSvg>
  );
}
