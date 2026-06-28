'use client';

import React from 'react';
import type { Geometry, DeriveResult } from 'lib/floorplan/types';
import type { Furniture } from 'lib/floorplan/furniture';
import DerivedWallsLayer from '../DerivedWallsLayer';
import RoomsLayer from '../geometry/RoomsLayer';
import FurnitureLayer from './FurnitureLayer';
import StageSvg from '../../ui/StageSvg';

interface Props {
  svgRef: React.RefObject<SVGSVGElement>;
  viewBox: [number, number, number, number];
  origin: [number, number];
  geometry: Geometry;
  derived: DeriveResult | null;
  furniture: Furniture[];
  selectedIndex: number | null;
  onSvgPointerDown: (e: React.PointerEvent) => void;
  onSvgPointerMove: (e: React.PointerEvent) => void;
  onSvgPointerUp: (e: React.PointerEvent) => void;
  onItemPointerDown: (e: React.PointerEvent, index: number) => void;
}

const noopWall = () => undefined;

// 家具模式画布: 几何 (房间色块 + 派生墙) 作淡色背景参考, 家具层可交互拖拽。
export default function FurnitureStage({
  svgRef,
  viewBox,
  origin,
  geometry,
  derived,
  furniture,
  selectedIndex,
  onSvgPointerDown,
  onSvgPointerMove,
  onSvgPointerUp,
  onItemPointerDown,
}: Props) {
  return (
    <StageSvg
      svgRef={svgRef}
      viewBox={viewBox}
      onPointerDown={onSvgPointerDown}
      onPointerMove={onSvgPointerMove}
      onPointerUp={onSvgPointerUp}
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
        selectedIndex={selectedIndex}
        onItemPointerDown={onItemPointerDown}
      />
    </StageSvg>
  );
}
