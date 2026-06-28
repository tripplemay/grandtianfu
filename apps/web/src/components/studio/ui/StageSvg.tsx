'use client';

import React, { useEffect } from 'react';
import { CANVAS_BG } from 'lib/floorplan/theme';

interface Props {
  svgRef: React.RefObject<SVGSVGElement>;
  viewBox: [number, number, number, number];
  onPointerDown: (e: React.PointerEvent) => void;
  onPointerMove: (e: React.PointerEvent) => void;
  onPointerUp: (e: React.PointerEvent) => void;
  onPointerCancel?: (e: React.PointerEvent) => void;
  // 原生 WheelEvent: 经非被动监听绑定 (passive:false), 使 preventDefault 生效且不报警。
  onWheel?: (e: WheelEvent) => void;
  // 触控捕获阶段: 双指捏合 (先于元素 onPointerDown, 不受其 stopPropagation 影响)。
  onPointerDownCapture?: (e: React.PointerEvent) => void;
  onPointerMoveCapture?: (e: React.PointerEvent) => void;
  onPointerUpCapture?: (e: React.PointerEvent) => void;
  // 视口变换 (阶段 1): children 全部移入被 transform 的内容层 <g>; 背景捕获 rect
  // 留在外层 (随视口固定全屏覆盖)。命中坐标经 contentRef.getScreenCTM() 自动兼容。
  contentRef?: React.Ref<SVGGElement>;
  contentTransform?: string;
  children: React.ReactNode;
}

// 受控 inline SVG 画布外壳 (审查清单 Q2-#3)。EditorStage / FurnitureStage 共用:
// viewBox + 底色 (CANVAS_BG) + 背景捕获 rect (data-bg=1, 空白点击=清选/落点) +
// pointer 回调透传 + 视口变换内容层。非 canvas (红线)。
export default function StageSvg({
  svgRef,
  viewBox,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onPointerCancel,
  onWheel,
  onPointerDownCapture,
  onPointerMoveCapture,
  onPointerUpCapture,
  contentRef,
  contentTransform,
  children,
}: Props) {
  // 非被动 wheel 监听: React onWheel 默认 passive, preventDefault 无效且报警。
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || !onWheel) return;
    const handler = (e: WheelEvent) => onWheel(e);
    svg.addEventListener('wheel', handler, { passive: false });
    return () => svg.removeEventListener('wheel', handler);
  }, [svgRef, onWheel]);

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
      onPointerCancel={onPointerCancel}
      onPointerDownCapture={onPointerDownCapture}
      onPointerMoveCapture={onPointerMoveCapture}
      onPointerUpCapture={onPointerUpCapture}
    >
      {/* 背景捕获层: 空白点击 = 清选 / 自由墙落点。留在视口变换外, 始终全屏覆盖。 */}
      <rect
        data-bg="1"
        x={viewBox[0]}
        y={viewBox[1]}
        width={viewBox[2]}
        height={viewBox[3]}
        fill="transparent"
      />
      {/* 视口变换内容层 */}
      <g
        data-testid="content-layer"
        ref={contentRef}
        transform={contentTransform}
      >
        {children}
      </g>
    </svg>
  );
}
