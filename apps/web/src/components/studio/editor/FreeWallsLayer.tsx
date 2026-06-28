'use client';

import React from 'react';
import type { FreeWall } from 'lib/floorplan/types';
import { STROKE_SELECTED, FREEWALL_STROKE } from 'lib/floorplan/theme';

interface Props {
  freeWalls: FreeWall[];
  origin: [number, number];
  selectedId: string | null;
  onPointerDown: (e: React.PointerEvent, fw: FreeWall) => void;
}

// 自由墙 (独立可选, §⑥)。
export default function FreeWallsLayer({
  freeWalls,
  origin,
  selectedId,
  onPointerDown,
}: Props) {
  return (
    <g>
      {freeWalls.map((fw) => {
        const sel = selectedId === fw.id;
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
        return (
          <line
            key={fw.id}
            {...coords}
            stroke={sel ? STROKE_SELECTED : FREEWALL_STROKE}
            strokeWidth={sel ? 4 : 2}
            strokeLinecap="round"
            strokeDasharray={fw.style === 'dashed' ? '8 5' : undefined}
            style={{ cursor: 'pointer' }}
            onPointerDown={(e) => onPointerDown(e, fw)}
          />
        );
      })}
    </g>
  );
}
