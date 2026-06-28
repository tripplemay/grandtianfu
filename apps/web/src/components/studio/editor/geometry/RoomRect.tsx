'use client';

import React from 'react';
import type { Room } from 'lib/floorplan/types';
import { ROOM_COLORS } from 'lib/floorplan/geometry';
import {
  ROOM_STROKE,
  ROOM_LABEL,
  ROOM_DIM_LABEL,
  ROOM_FILL_FALLBACK,
  STROKE_SELECTED,
  STROKE_ERROR,
} from 'lib/floorplan/theme';

interface Props {
  room: Room;
  origin: [number, number];
  selected: boolean;
  error?: boolean;
  dim?: boolean; // 只读淡显参考 (家具模式): 单行标签, 不可点 (由外层 g 统一降透明度)。
  onPointerDown: (e: React.PointerEvent, room: Room) => void;
}

// 房间地面色块 (可选中/拖动) + id/label 文本。坐标 = 几何 + origin。
// error=true (重叠未合并冲突) -> 红色粗描边高亮 (优先于选中态)。
// dim=true -> 家具模式只读参考层: 仅单行 label.zh, 无 id/中心标签, 不响应指针。
export default function RoomRect({
  room,
  origin,
  selected,
  error,
  dim,
  onPointerDown,
}: Props) {
  const [x, y, w, h] = room.rect;
  const X = x + origin[0];
  const Y = y + origin[1];
  const labelZh = room.label?.zh ?? '';
  const fill = ROOM_COLORS[room.type] ?? ROOM_FILL_FALLBACK;

  if (dim) {
    return (
      <g>
        <rect
          x={X}
          y={Y}
          width={w}
          height={h}
          rx={2}
          fill={fill}
          fillOpacity={0.5}
          stroke={ROOM_STROKE}
          strokeWidth={1}
        />
        <text
          x={X + w / 2}
          y={Y + 16}
          fontSize={12}
          fontWeight={600}
          fill={ROOM_DIM_LABEL}
          textAnchor="middle"
          dominantBaseline="middle"
        >
          {labelZh || room.id}
        </text>
      </g>
    );
  }

  const stroke = error ? STROKE_ERROR : selected ? STROKE_SELECTED : ROOM_STROKE;
  const strokeWidth = error ? 4 : selected ? 3 : 1;
  return (
    <g>
      <rect
        x={X}
        y={Y}
        width={w}
        height={h}
        rx={2}
        fill={fill}
        fillOpacity={0.55}
        stroke={stroke}
        strokeWidth={strokeWidth}
        style={{ cursor: 'move' }}
        onPointerDown={(e) => onPointerDown(e, room)}
      />
      <text
        x={X + w / 2}
        y={Y + 18}
        fontSize={12}
        fontWeight={600}
        fill={ROOM_LABEL}
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
        fill={ROOM_LABEL}
        textAnchor="middle"
        dominantBaseline="middle"
        style={{ pointerEvents: 'none' }}
      >
        {labelZh || room.id}
      </text>
    </g>
  );
}
