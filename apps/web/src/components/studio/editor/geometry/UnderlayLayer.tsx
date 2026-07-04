'use client';

import React from 'react';
import type { UnderlayMeta } from 'lib/floorplan/types';

// 底图描摹层 (P6): 参考底图半透明叠在网格之上、房间之下, 与内容层同一变换 (随缩放平移),
// 故描出的房间与底图对齐。pointerEvents:none -> 不拦截画布交互。scale/dx/dy 把图像原始
// 像素贴到 10mm/px 几何网格 (标定得来); 坐标同房间 = 几何坐标 + origin。
export default function UnderlayLayer({
  underlay,
  origin,
}: {
  underlay?: UnderlayMeta;
  origin: [number, number];
}) {
  if (!underlay?.url) return null;
  const { url, opacity, scale, dx, dy } = underlay;
  return (
    <g
      data-testid="underlay-layer"
      transform={`translate(${dx + origin[0]} ${dy + origin[1]}) scale(${scale})`}
      opacity={opacity}
      style={{ pointerEvents: 'none' }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <image href={url} x={0} y={0} />
    </g>
  );
}
