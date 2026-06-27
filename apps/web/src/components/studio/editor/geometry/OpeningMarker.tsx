'use client';

import React from 'react';
import type { Opening } from 'lib/floorplan/types';

interface Props {
  opening: Opening;
  origin: [number, number];
  selected: boolean;
  onPointerDown: (e: React.PointerEvent, op: Opening) => void;
}

// 开洞滑块 (沿墙拖动, §⑤)。粗半透明线; 选中加深。
export default function OpeningMarker({ opening, origin, selected, onPointerDown }: Props) {
  const { axis, at, span } = opening.wall;
  const [lo, hi] = span;
  let coords: { x1: number; y1: number; x2: number; y2: number };
  if (axis === 'v') {
    coords = { x1: at + origin[0], y1: lo + origin[1], x2: at + origin[0], y2: hi + origin[1] };
  } else {
    coords = { x1: lo + origin[0], y1: at + origin[1], x2: hi + origin[0], y2: at + origin[1] };
  }
  return (
    <line
      {...coords}
      stroke={selected ? '#e0701a' : 'rgba(224,112,26,0.35)'}
      strokeWidth={selected ? 6 : 10}
      strokeLinecap="round"
      style={{ cursor: 'grab' }}
      onPointerDown={(e) => onPointerDown(e, opening)}
    />
  );
}
