'use client';

import React, { useState } from 'react';
import type { FreeWall } from 'lib/floorplan/types';
import {
  STROKE_SELECTED,
  FREEWALL_STROKE,
  HOVER_STROKE,
} from 'lib/floorplan/theme';

interface Props {
  freeWalls: FreeWall[];
  origin: [number, number];
  selectedId: string | null;
  scale?: number; // 视口缩放 (阶段 1): 线宽随之反比, 保持恒定屏幕尺寸。
  onPointerDown: (e: React.PointerEvent, fw: FreeWall) => void;
}

// 单条自由墙: 透明宽命中线 (P2-6, 易点中细线) + 视觉细线 + hover 高亮。
function FreeWallLine({
  fw,
  origin,
  selected,
  scale,
  onPointerDown,
}: {
  fw: FreeWall;
  origin: [number, number];
  selected: boolean;
  scale: number;
  onPointerDown: (e: React.PointerEvent, fw: FreeWall) => void;
}) {
  const [hover, setHover] = useState(false);
  const [lo, hi] = fw.span;
  let coords: { x1: number; y1: number; x2: number; y2: number };
  if (fw.axis === 'v') {
    coords = {
      x1: fw.at + origin[0],
      y1: lo + origin[1],
      x2: fw.at + origin[0],
      y2: hi + origin[1],
    };
  } else {
    coords = {
      x1: lo + origin[0],
      y1: fw.at + origin[1],
      x2: hi + origin[0],
      y2: fw.at + origin[1],
    };
  }
  const visStroke = selected
    ? STROKE_SELECTED
    : hover
    ? HOVER_STROKE
    : FREEWALL_STROKE;
  return (
    <g>
      {/* 透明宽命中线: 恒定 14u/scale 屏幕宽; pointer-events:stroke 仅线命中 */}
      <line
        {...coords}
        data-testid={`fw-hit-${fw.id}`}
        stroke="transparent"
        strokeWidth={14 / scale}
        strokeLinecap="round"
        style={{ cursor: 'grab', pointerEvents: 'stroke' }}
        onPointerDown={(e) => onPointerDown(e, fw)}
        onPointerEnter={() => setHover(true)}
        onPointerLeave={() => setHover(false)}
      />
      {/* 可见细线: 不响应指针 */}
      <line
        {...coords}
        stroke={visStroke}
        strokeWidth={(selected ? 4 : hover ? 3 : 2) / scale}
        strokeLinecap="round"
        strokeDasharray={fw.style === 'dashed' ? '8 5' : undefined}
        style={{ pointerEvents: 'none' }}
      />
    </g>
  );
}

// 自由墙 (独立可选, §⑥)。
function FreeWallsLayer({
  freeWalls,
  origin,
  selectedId,
  scale = 1,
  onPointerDown,
}: Props) {
  return (
    <g>
      {freeWalls.map((fw) => (
        <FreeWallLine
          key={fw.id}
          fw={fw}
          origin={origin}
          selected={selectedId === fw.id}
          scale={scale}
          onPointerDown={onPointerDown}
        />
      ))}
    </g>
  );
}

// React.memo (阶段 3 / P2-1): freeWalls/origin/selectedId/scale/回调 稳定时跳过重渲。
export default React.memo(FreeWallsLayer);
