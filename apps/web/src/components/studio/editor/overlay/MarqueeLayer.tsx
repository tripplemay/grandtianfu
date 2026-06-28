'use client';

import React from 'react';
import { MARQUEE_STROKE, MARQUEE_FILL } from 'lib/floorplan/theme';

interface Marquee {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

interface Props {
  marquee: Marquee | null;
  origin: [number, number];
  scale?: number; // 视口缩放: 描边随之反比保持恒定屏幕尺寸。
}

// 框选 marquee 覆盖层 (阶段 5a / P2-7): 几何坐标 + origin, 置于内容变换层内 (随视口缩放/平移)。
// pointerEvents:none 不干扰命中。无 marquee 时返回 null。
function MarqueeLayer({ marquee, origin, scale = 1 }: Props) {
  if (!marquee) return null;
  const x = Math.min(marquee.x0, marquee.x1) + origin[0];
  const y = Math.min(marquee.y0, marquee.y1) + origin[1];
  const w = Math.abs(marquee.x1 - marquee.x0);
  const h = Math.abs(marquee.y1 - marquee.y0);
  return (
    <rect
      data-testid="marquee-rect"
      x={x}
      y={y}
      width={w}
      height={h}
      fill={MARQUEE_FILL}
      stroke={MARQUEE_STROKE}
      strokeWidth={1 / scale}
      strokeDasharray={`${4 / scale} ${3 / scale}`}
      style={{ pointerEvents: 'none' }}
    />
  );
}

export default React.memo(MarqueeLayer);
