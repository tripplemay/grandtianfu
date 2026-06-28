'use client';

import React, { useState } from 'react';
import type { Opening } from 'lib/floorplan/types';
import {
  STROKE_SELECTED,
  OPENING_IDLE,
  HOVER_STROKE,
} from 'lib/floorplan/theme';

interface Props {
  opening: Opening;
  origin: [number, number];
  selected: boolean;
  scale?: number; // 视口缩放 (阶段 1): 命中线宽随之反比, 保持恒定屏幕尺寸。
  onPointerDown: (e: React.PointerEvent, op: Opening) => void;
}

// 开洞滑块 (沿墙拖动, §⑤)。粗半透明线; 选中加深。叠加透明宽命中线 (P2-6): 选中态
// 可见线变细也能抓住; hover 高亮; 命中域随 scale 反比保持恒定屏幕宽度。
function OpeningMarker({
  opening,
  origin,
  selected,
  scale = 1,
  onPointerDown,
}: Props) {
  const [hover, setHover] = useState(false);
  const { axis, at, span } = opening.wall;
  const [lo, hi] = span;
  let coords: { x1: number; y1: number; x2: number; y2: number };
  if (axis === 'v') {
    coords = {
      x1: at + origin[0],
      y1: lo + origin[1],
      x2: at + origin[0],
      y2: hi + origin[1],
    };
  } else {
    coords = {
      x1: lo + origin[0],
      y1: at + origin[1],
      x2: hi + origin[0],
      y2: at + origin[1],
    };
  }
  const visStroke = selected
    ? STROKE_SELECTED
    : hover
    ? HOVER_STROKE
    : OPENING_IDLE;
  return (
    <g>
      {/* 透明宽命中线: 恒定 18u/scale, pointer-events:stroke 仅线段命中 */}
      <line
        {...coords}
        stroke="transparent"
        strokeWidth={18 / scale}
        strokeLinecap="round"
        style={{ cursor: 'grab', pointerEvents: 'stroke' }}
        onPointerDown={(e) => onPointerDown(e, opening)}
        onPointerEnter={() => setHover(true)}
        onPointerLeave={() => setHover(false)}
      />
      {/* 可见线: 视觉细, 不响应指针 (命中交给上面的宽线) */}
      <line
        {...coords}
        stroke={visStroke}
        strokeWidth={(selected ? 6 : 10) / scale}
        strokeLinecap="round"
        style={{ pointerEvents: 'none' }}
      />
    </g>
  );
}

// React.memo (阶段 3 / P2-1): props 原始值/稳定回调, 拖房时门窗不重渲。
export default React.memo(OpeningMarker);
