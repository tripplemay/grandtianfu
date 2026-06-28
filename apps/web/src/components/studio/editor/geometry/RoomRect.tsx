'use client';

import React, { useState } from 'react';
import type { Room } from 'lib/floorplan/types';
import { ROOM_COLORS } from 'lib/floorplan/geometry';
import {
  ROOM_STROKE,
  ROOM_LABEL,
  ROOM_DIM_LABEL,
  ROOM_FILL_FALLBACK,
  STROKE_SELECTED,
  STROKE_ERROR,
  HOVER_STROKE,
} from 'lib/floorplan/theme';

interface Props {
  room: Room;
  origin: [number, number];
  selected: boolean;
  error?: boolean;
  scale?: number; // 视口缩放 (阶段 1): 选中/冲突描边随之反比, 保持恒定屏幕尺寸。
  dim?: boolean; // 只读淡显参考 (家具模式): 单行标签, 不可点 (由外层 g 统一降透明度)。
  onPointerDown: (e: React.PointerEvent, room: Room) => void;
}

// 房间地面色块 (可选中/拖动) + id/label 文本。坐标 = 几何 + origin。
// error=true (重叠未合并冲突) -> 红色粗描边高亮 (优先于选中态)。
// dim=true -> 家具模式只读参考层: 仅单行 label.zh, 无 id/中心标签, 不响应指针。
function RoomRect({
  room,
  origin,
  selected,
  error,
  scale = 1,
  dim,
  onPointerDown,
}: Props) {
  const [hover, setHover] = useState(false);
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

  // hover 高亮 (P2-6): 仅在既非选中也非冲突时生效, 不抢眼。
  const stroke = error
    ? STROKE_ERROR
    : selected
    ? STROKE_SELECTED
    : hover
    ? HOVER_STROKE
    : ROOM_STROKE;
  // 选中/冲突/hover 描边随 scale 反比 (恒定屏幕尺寸); 普通描边随内容缩放。
  const strokeWidth = error
    ? 4 / scale
    : selected
    ? 3 / scale
    : hover
    ? 2 / scale
    : 1;
  return (
    <g>
      <rect
        data-room-id={room.id}
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
        onPointerEnter={() => setHover(true)}
        onPointerLeave={() => setHover(false)}
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

// React.memo (阶段 3 / P2-1): props 多为原始值 / 稳定引用 (room/origin/回调), 拖一房时
// 仅被拖房 room 引用变化, 其余跳过重渲。
export default React.memo(RoomRect);
