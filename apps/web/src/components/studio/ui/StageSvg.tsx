'use client';

import React from 'react';
import { CANVAS_BG } from 'lib/floorplan/theme';

interface Props {
  svgRef: React.RefObject<SVGSVGElement>;
  viewBox: [number, number, number, number];
  onPointerDown: (e: React.PointerEvent) => void;
  onPointerMove: (e: React.PointerEvent) => void;
  onPointerUp: (e: React.PointerEvent) => void;
  children: React.ReactNode;
}

// 受控 inline SVG 画布外壳 (审查清单 Q2-#3)。EditorStage / FurnitureStage 共用:
// viewBox + 底色 (CANVAS_BG) + 背景捕获 rect (data-bg=1, 空白点击=清选/落点) +
// pointer 回调透传。非 canvas (红线)。
export default function StageSvg({
  svgRef,
  viewBox,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  children,
}: Props) {
  return (
    <svg
      ref={svgRef}
      viewBox={viewBox.join(' ')}
      xmlns="http://www.w3.org/2000/svg"
      className="block h-auto w-full touch-none select-none"
      style={{ background: CANVAS_BG }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
    >
      {/* 背景捕获层: 空白点击 = 清选 / 自由墙落点 */}
      <rect
        data-bg="1"
        x={viewBox[0]}
        y={viewBox[1]}
        width={viewBox[2]}
        height={viewBox[3]}
        fill="transparent"
      />
      {children}
    </svg>
  );
}
