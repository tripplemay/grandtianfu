'use client';

import React from 'react';
import type { Room } from 'lib/floorplan/types';
import { ROOM_COLORS } from 'lib/floorplan/geometry';

interface Props {
  room: Room;
  origin: [number, number];
  selected: boolean;
  onPointerDown: (e: React.PointerEvent, room: Room) => void;
}

// 房间地面色块 (可选中/拖动) + id/label 文本。坐标 = 几何 + origin。
export default function RoomRect({ room, origin, selected, onPointerDown }: Props) {
  const [x, y, w, h] = room.rect;
  const X = x + origin[0];
  const Y = y + origin[1];
  const labelZh = room.label?.zh ?? '';
  return (
    <g>
      <rect
        x={X}
        y={Y}
        width={w}
        height={h}
        rx={2}
        fill={ROOM_COLORS[room.type] ?? '#eee'}
        fillOpacity={0.55}
        stroke={selected ? '#e0701a' : '#b3a98f'}
        strokeWidth={selected ? 3 : 1}
        style={{ cursor: 'move' }}
        onPointerDown={(e) => onPointerDown(e, room)}
      />
      <text
        x={X + w / 2}
        y={Y + 18}
        fontSize={12}
        fontWeight={600}
        fill="#3a3024"
        textAnchor="middle"
        dominantBaseline="middle"
        style={{ pointerEvents: 'none' }}
      >
        {room.id}
      </text>
      <text
        x={X + w / 2}
        y={Y + h / 2}
        fontSize={12}
        fontWeight={600}
        fill="#3a3024"
        textAnchor="middle"
        dominantBaseline="middle"
        style={{ pointerEvents: 'none' }}
      >
        {labelZh || room.id}
      </text>
    </g>
  );
}
