'use client';

import React, { useState } from 'react';
import type { Opening } from 'lib/floorplan/types';
import {
  STROKE_SELECTED,
  OPENING_IDLE,
  HOVER_STROKE,
  HANDLE_FILL,
} from 'lib/floorplan/theme';

interface Props {
  opening: Opening;
  origin: [number, number];
  selected: boolean;
  scale?: number; // 视口缩放 (阶段 1): 命中线宽随之反比, 保持恒定屏幕尺寸。
  onPointerDown: (e: React.PointerEvent, op: Opening) => void;
  // 端点拖宽 (P2-8): 拖某端改 span (夹取寄主墙 + 最小宽)。
  onHandleDown: (e: React.PointerEvent, op: Opening, end: 'lo' | 'hi') => void;
  // 画布翻转 (P2-8): 门翻 hinge / 推拉窗翻 swing。
  onFlip: (op: Opening) => void;
}

// 开洞滑块 (沿墙拖动, §⑤)。粗半透明线; 选中加深。叠加透明宽命中线 (P2-6); 选中态线
// 更粗更易抓 (非变细)。选中时两端出 resize 把手 (拖宽, P2-8) + 门出画布翻转小按钮。
function OpeningMarker({
  opening,
  origin,
  selected,
  scale = 1,
  onPointerDown,
  onHandleDown,
  onFlip,
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
  // 选中态更粗 (P2-8: 选中应更粗更易抓, 非变细): idle 8 / hover 10 / selected 12。
  const visWidth = (selected ? 12 : hover ? 10 : 8) / scale;

  // 端点把手 (P2-8): 恒定屏幕尺寸; 沿墙轴 resize 光标。
  const hs = 11 / scale;
  const hHalf = hs / 2;
  const hsw = 2 / scale;
  const handleCursor = axis === 'v' ? 'ns-resize' : 'ew-resize';
  const loPt: [number, number] = axis === 'v' ? [at, lo] : [lo, at];
  const hiPt: [number, number] = axis === 'v' ? [at, hi] : [hi, at];

  // 翻转按钮 (P2-8, 仅门): 墙中点垂直偏移, 小圆 + ⇄。
  const isDoor = opening.kind === 'door';
  const mid = (lo + hi) / 2;
  const flipOff = 18 / scale;
  const flipR = 9 / scale;
  const flipPt: [number, number] =
    axis === 'v' ? [at + flipOff, mid] : [mid, at - flipOff];

  return (
    <g>
      {/* 透明宽命中线: 恒定 18u/scale, pointer-events:stroke 仅线段命中 */}
      <line
        {...coords}
        data-testid={`op-hit-${opening.id}`}
        stroke="transparent"
        strokeWidth={18 / scale}
        strokeLinecap="round"
        style={{ cursor: 'grab', pointerEvents: 'stroke' }}
        onPointerDown={(e) => onPointerDown(e, opening)}
        onPointerEnter={() => setHover(true)}
        onPointerLeave={() => setHover(false)}
      />
      {/* 可见线: 选中更粗; 不响应指针 (命中交给上面的宽线) */}
      <line
        {...coords}
        data-testid={`op-vis-${opening.id}`}
        stroke={visStroke}
        strokeWidth={visWidth}
        strokeLinecap="round"
        style={{ pointerEvents: 'none' }}
      />
      {selected && (
        <>
          {/* 两端拖宽把手 (P2-8) */}
          {(['lo', 'hi'] as const).map((end) => {
            const [px, py] = end === 'lo' ? loPt : hiPt;
            return (
              <rect
                key={end}
                data-testid={`op-handle-${end}`}
                x={px + origin[0] - hHalf}
                y={py + origin[1] - hHalf}
                width={hs}
                height={hs}
                fill={HANDLE_FILL}
                stroke={STROKE_SELECTED}
                strokeWidth={hsw}
                style={{ cursor: handleCursor }}
                onPointerDown={(e) => onHandleDown(e, opening, end)}
              />
            );
          })}
          {/* 翻转小按钮 (P2-8, 仅门) */}
          {isDoor && (
            <g
              data-testid="op-flip"
              style={{ cursor: 'pointer' }}
              onPointerDown={(e) => {
                e.stopPropagation();
                onFlip(opening);
              }}
            >
              <circle
                data-testid="op-flip-dot"
                cx={flipPt[0] + origin[0]}
                cy={flipPt[1] + origin[1]}
                r={flipR}
                fill={HANDLE_FILL}
                stroke={STROKE_SELECTED}
                strokeWidth={hsw}
              />
              <text
                x={flipPt[0] + origin[0]}
                y={flipPt[1] + origin[1]}
                fontSize={11 / scale}
                fill={STROKE_SELECTED}
                textAnchor="middle"
                dominantBaseline="central"
                style={{ pointerEvents: 'none' }}
              >
                ⇄
              </text>
            </g>
          )}
        </>
      )}
    </g>
  );
}

// React.memo (阶段 3 / P2-1): props 原始值/稳定回调, 拖房时门窗不重渲。
export default React.memo(OpeningMarker);
