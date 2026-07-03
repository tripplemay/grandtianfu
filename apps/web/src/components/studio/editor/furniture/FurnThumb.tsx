'use client';

import React from 'react';
import { furnColor, isCircleType } from 'lib/floorplan/furniture';
import { FURN_STROKE, FURN_FILL_FALLBACK } from 'lib/floorplan/theme';

// 家具库小缩略图 (阶段 5b / P3): 用 FURN_COLORS + 形状 (圆/矩) 画 mini SVG。
// 纯展示, pointer-events 交给外层按钮。
export default function FurnThumb({
  type,
  size = 22,
}: {
  type: string;
  size?: number;
}) {
  const raw = furnColor(type) ?? FURN_FILL_FALLBACK;
  const fill = raw === 'none' ? 'rgba(0,0,0,0.06)' : raw;
  const circle = isCircleType(type);
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden="true"
      style={{ pointerEvents: 'none', flex: '0 0 auto' }}
    >
      {circle ? (
        <circle
          cx={12}
          cy={12}
          r={9}
          fill={fill}
          stroke={FURN_STROKE}
          strokeWidth={1.5}
        />
      ) : (
        <rect
          x={3}
          y={5}
          width={18}
          height={14}
          rx={2}
          fill={fill}
          stroke={FURN_STROKE}
          strokeWidth={1.5}
        />
      )}
    </svg>
  );
}
