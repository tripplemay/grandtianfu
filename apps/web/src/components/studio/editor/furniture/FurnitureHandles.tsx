'use client';

import React from 'react';
import type { Geometry } from 'lib/floorplan/types';
import { type Furniture, furnAbs, isCircle } from 'lib/floorplan/furniture';
import { HANDLE_FILL, STROKE_SELECTED } from 'lib/floorplan/theme';

interface Props {
  item: Furniture;
  geometry: Geometry;
  origin: [number, number];
  scale?: number; // 视口缩放: 把手随之反比, 保持恒定屏幕尺寸。
  onResizeDown: (e: React.PointerEvent, handle: string) => void;
  onRotateDown: (e: React.PointerEvent) => void;
}

// 把手方向光标 (复用 geometry ResizeHandles 约定)。
const HANDLE_CURSOR: Record<string, string> = {
  nw: 'nwse-resize',
  se: 'nwse-resize',
  ne: 'nesw-resize',
  sw: 'nesw-resize',
  n: 'ns-resize',
  s: 'ns-resize',
  e: 'ew-resize',
  w: 'ew-resize',
};

// 选中家具的包围盒 + 8 缩放把手 (P2-3) + 顶部旋转柄 (P2-2)。整组套与件相同的
// rotate(rot, 中心) 变换, 故把手始终贴合旋转后的件; 缩放/旋转的指针几何由 hook 在
// 件本地坐标系内换算 (computeFurnResize / computeRotation)。
function FurnitureHandles({
  item,
  geometry,
  origin,
  scale = 1,
  onResizeDown,
  onRotateDown,
}: Props) {
  const a = furnAbs(item, geometry);
  const circle = isCircle(item);
  const X = a.x + origin[0];
  const Y = a.y + origin[1];
  const cx = a.cx + origin[0];
  const cy = a.cy + origin[1];
  const w = a.w;
  const h = a.h;
  const rot = typeof item.rot === 'number' ? item.rot : 0;
  const groupTransform = rot ? `rotate(${rot} ${cx} ${cy})` : undefined;

  const size = 12 / scale;
  const half = size / 2;
  const sw = 2 / scale;

  // 圆形件: 仅 4 角把手 (改半径); 矩形件: 8 把手 (改 w/h)。
  const pts: Record<string, [number, number]> = circle
    ? {
        nw: [X, Y],
        ne: [X + w, Y],
        se: [X + w, Y + h],
        sw: [X, Y + h],
      }
    : {
        nw: [X, Y],
        n: [X + w / 2, Y],
        ne: [X + w, Y],
        e: [X + w, Y + h / 2],
        se: [X + w, Y + h],
        s: [X + w / 2, Y + h],
        sw: [X, Y + h],
        w: [X, Y + h / 2],
      };

  // 旋转柄: 件本地正上方 (Y 顶边再上移 gap), 一根连接线 + 圆点。
  const gap = 22 / scale;
  const rotX = cx;
  const rotY = Y - gap;

  return (
    <g transform={groupTransform}>
      {/* 包围盒 (圆形件也画矩形包围, 便于对齐) */}
      <rect
        x={X}
        y={Y}
        width={w}
        height={h}
        fill="none"
        stroke={STROKE_SELECTED}
        strokeWidth={sw}
        strokeDasharray={`${4 / scale} ${3 / scale}`}
        style={{ pointerEvents: 'none' }}
      />

      {/* 旋转柄连接线 + 圆点 */}
      <line
        x1={cx}
        y1={Y}
        x2={rotX}
        y2={rotY}
        stroke={STROKE_SELECTED}
        strokeWidth={sw}
        style={{ pointerEvents: 'none' }}
      />
      <circle
        data-testid="furn-rotate-handle"
        cx={rotX}
        cy={rotY}
        r={size * 0.7}
        fill={HANDLE_FILL}
        stroke={STROKE_SELECTED}
        strokeWidth={sw}
        style={{ cursor: 'grab' }}
        onPointerDown={onRotateDown}
      />

      {/* 缩放把手 */}
      {Object.entries(pts).map(([k, [px, py]]) => (
        <rect
          key={k}
          data-testid={`furn-resize-${k}`}
          x={px - half}
          y={py - half}
          width={size}
          height={size}
          fill={HANDLE_FILL}
          stroke={STROKE_SELECTED}
          strokeWidth={sw}
          style={{ cursor: HANDLE_CURSOR[k] ?? 'pointer' }}
          onPointerDown={(e) => onResizeDown(e, k)}
        />
      ))}
    </g>
  );
}

// React.memo: 仅选中件挂载; 缩放/旋转期 item 变化重渲跟随, pan 时跳过。
export default React.memo(FurnitureHandles);
