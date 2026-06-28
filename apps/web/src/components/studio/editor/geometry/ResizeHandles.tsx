'use client';

import React from 'react';
import type { Room } from 'lib/floorplan/types';
import { HANDLE_FILL, STROKE_SELECTED } from 'lib/floorplan/theme';

interface Props {
  room: Room;
  origin: [number, number];
  scale?: number; // 视口缩放 (阶段 1): 把手随之反比, 保持恒定屏幕尺寸。
  onHandleDown: (e: React.PointerEvent, room: Room, handle: string) => void;
}

// 把手方向光标映射 (阶段 0)。
const HANDLE_CURSOR: Record<string, string> = {
  nw: 'nwse-resize',
  se: 'nwse-resize',
  ne: 'nesw-resize',
  sw: 'nesw-resize',
  n: 'ns-resize',
  s: 'ns-resize',
  e: 'ew-resize',
  w: 'ew-resize',
};

// 8 把手缩放 (§②)。handle key: nw/n/ne/e/se/s/sw/w。
export default function ResizeHandles({
  room,
  origin,
  scale = 1,
  onHandleDown,
}: Props) {
  const [x, y, w, h] = room.rect;
  const X = x + origin[0];
  const Y = y + origin[1];
  const pts: Record<string, [number, number]> = {
    nw: [X, Y],
    n: [X + w / 2, Y],
    ne: [X + w, Y],
    e: [X + w, Y + h / 2],
    se: [X + w, Y + h],
    s: [X + w / 2, Y + h],
    sw: [X, Y + h],
    w: [X, Y + h / 2],
  };
  // 恒定屏幕尺寸: 几何尺寸 = 基准 / scale。
  const size = 12 / scale;
  const half = size / 2;
  const sw = 2 / scale;
  return (
    <g>
      {Object.entries(pts).map(([k, [px, py]]) => (
        <rect
          key={k}
          x={px - half}
          y={py - half}
          width={size}
          height={size}
          fill={HANDLE_FILL}
          stroke={STROKE_SELECTED}
          strokeWidth={sw}
          style={{ cursor: HANDLE_CURSOR[k] ?? 'pointer' }}
          onPointerDown={(e) => onHandleDown(e, room, k)}
        />
      ))}
    </g>
  );
}
