'use client';

import React from 'react';
import type { Geometry, DeriveResult } from 'lib/floorplan/types';
import type { Furniture } from 'lib/floorplan/furniture';
import { ROOM_COLORS } from 'lib/floorplan/geometry';
import DerivedWallsLayer from '../DerivedWallsLayer';
import FurnitureLayer from './FurnitureLayer';

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
      {/* 背景捕获层: 空白点击 = 清选 */}
      <rect
        data-bg="1"
        x={viewBox[0]}
        y={viewBox[1]}
        width={viewBox[2]}
        height={viewBox[3]}
        fill="transparent"
      />

      {/* 几何参考层 (淡色只读) */}
      <g opacity={0.35} style={{ pointerEvents: 'none' }}>
        {geometry.rooms.map((r) => {
          const [x, y, w, h] = r.rect;
          return (
            <g key={r.id}>
              <rect
                x={x + origin[0]}
                y={y + origin[1]}
                width={w}
                height={h}
                rx={2}
                fill={ROOM_COLORS[r.type] ?? '#eee'}
                fillOpacity={0.5}
                stroke="#b3a98f"
                strokeWidth={1}
              />
              <text
                x={x + origin[0] + w / 2}
                y={y + origin[1] + 16}
                fontSize={12}
                fontWeight={600}
                fill="#cdbfa0"
                textAnchor="middle"
                dominantBaseline="middle"
              >
                {r.label?.zh ?? r.id}
              </text>
            </g>
          );
        })}
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
    </svg>
  );
}
