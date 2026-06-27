'use client';

import React from 'react';
import type { Room } from 'lib/floorplan/types';

interface Props {
  room: Room;
  origin: [number, number];
  onHandleDown: (e: React.PointerEvent, room: Room, handle: string) => void;
}

// 8 把手缩放 (§②)。handle key: nw/n/ne/e/se/s/sw/w。
export default function ResizeHandles({ room, origin, onHandleDown }: Props) {
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
  return (
    <g>
      {Object.entries(pts).map(([k, [px, py]]) => (
        <rect
          key={k}
          x={px - 6}
          y={py - 6}
          width={12}
          height={12}
          fill="#fff"
          stroke="#e0701a"
          strokeWidth={2}
          style={{ cursor: 'pointer' }}
          onPointerDown={(e) => onHandleDown(e, room, k)}
        />
      ))}
    </g>
  );
}
