'use client';

import React from 'react';
import type { SnapGuide } from 'lib/floorplan/geometry';
import type { DragHud } from 'lib/floorplan/overlay';
import { GUIDE_LINE, HUD_BG, HUD_TEXT } from 'lib/floorplan/theme';

interface Props {
  guides: SnapGuide[];
  hud: DragHud | null;
  origin: [number, number];
  scale?: number; // 视口缩放: 线宽/字号随之反比, 保持恒定屏幕尺寸 (P1-4)。
}

// 拖动/缩放期覆盖层 (P1-4): 吸附对齐红线 + 实时尺寸标签。坐标为几何 + origin, 置于
// 内容变换层内 (随视口缩放/平移)。松手时上层清空 guides/hud -> 本层返回 null 卸载。
// 全程 pointerEvents:none, 不干扰命中。
function GuideLayer({ guides, hud, origin, scale = 1 }: Props) {
  if (!guides.length && !hud) return null;
  const sw = 1 / scale;
  const dash = `${6 / scale} ${4 / scale}`;
  const fs = 12 / scale;
  const padX = 6 / scale;
  const padY = 4 / scale;
  const gap = 8 / scale;

  let hudNode: React.ReactNode = null;
  if (hud) {
    const tx = hud.x + origin[0];
    // 标签盒底边距元素顶边 gap, 整体在元素上方。
    const boxH = fs + padY * 2;
    const boxW = (hud.text.length * 7 + 12) / scale;
    const boxX = tx - boxW / 2;
    const boxBottom = hud.y + origin[1] - gap;
    const boxY = boxBottom - boxH;
    hudNode = (
      <g data-testid="dim-hud">
        <rect
          x={boxX}
          y={boxY}
          width={boxW}
          height={boxH}
          rx={3 / scale}
          fill={HUD_BG}
        />
        <text
          x={tx}
          y={boxY + boxH / 2}
          fontSize={fs}
          fill={HUD_TEXT}
          textAnchor="middle"
          dominantBaseline="middle"
        >
          {hud.text}
        </text>
      </g>
    );
  }

  return (
    <g data-testid="guide-layer" style={{ pointerEvents: 'none' }}>
      {guides.map((gd, i) => {
        const isV = gd.axis === 'v';
        const x1 = (isV ? gd.pos : gd.from) + origin[0];
        const y1 = (isV ? gd.from : gd.pos) + origin[1];
        const x2 = (isV ? gd.pos : gd.to) + origin[0];
        const y2 = (isV ? gd.to : gd.pos) + origin[1];
        return (
          <line
            key={`${gd.axis}-${i}`}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke={GUIDE_LINE}
            strokeWidth={sw}
            strokeDasharray={dash}
          />
        );
      })}
      {hudNode}
    </g>
  );
}

export default React.memo(GuideLayer);
