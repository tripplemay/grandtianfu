'use client';

import React from 'react';
import type { Furniture } from 'lib/floorplan/furniture';
import {
  FURN_COLORS,
  furnAbs,
  furnZh,
  isCircle,
} from 'lib/floorplan/furniture';
import type { Geometry } from 'lib/floorplan/types';
import {
  STROKE_SELECTED,
  STROKE_ERROR,
  FURN_STROKE,
  FURN_LABEL,
  FURN_ARROW,
  FURN_FILL_FALLBACK,
  FURN_FILL_NONE,
} from 'lib/floorplan/theme';

interface Props {
  item: Furniture;
  geometry: Geometry;
  origin: [number, number];
  selected: boolean;
  scale?: number; // 视口缩放 (阶段 1): 选中描边随之反比, 保持恒定屏幕尺寸。
  blocked?: boolean; // 越界拖动被夹取 (P2-5): 红描边提示该位置不允许。
  readOnly?: boolean;
  onPointerDown?: (e: React.PointerEvent, id: string) => void;
}

// 单件家具 (矩形/圆形) + 中文标签 + 朝向短线 (移植 editor.html render/arrow)。
// 坐标 = 解析后的绝对几何坐标 + origin。readOnly=true 时半透只读 (几何模式参考层)。
function FurnitureItem({
  item,
  geometry,
  origin,
  selected,
  scale = 1,
  blocked,
  readOnly,
  onPointerDown,
}: Props) {
  const a = furnAbs(item, geometry);
  const raw = FURN_COLORS[item.t] ?? item.color ?? FURN_FILL_FALLBACK;
  const fill = raw === 'none' ? FURN_FILL_NONE : raw;
  const stroke = blocked
    ? STROKE_ERROR
    : selected
    ? STROKE_SELECTED
    : FURN_STROKE;
  const strokeWidth = blocked ? 6 / scale : selected ? 6 / scale : 1.5;
  const cx = a.cx + origin[0];
  const cy = a.cy + origin[1];
  // 自由旋转 (P2-2): 仅 rot≠0 时套 rotate(rot, 中心)。命中/反推仍走未旋转坐标 (上层用
  // contentRef 的 CTM, 不含本 g 的 rotate), 故 reanchor 不变。
  const rot = typeof item.rot === 'number' ? item.rot : 0;
  const groupTransform = rot ? `rotate(${rot} ${cx} ${cy})` : undefined;

  const id = item.id;
  const down =
    readOnly || !id
      ? undefined
      : (e: React.PointerEvent) => onPointerDown?.(e, id);

  // 朝向短线 (仅矩形件): 从中心指向 orient 方向。
  const arrow = (() => {
    if (item.orient && !isCircle(item)) {
      const d = Math.min(a.w, a.h) * 0.32;
      const m: Record<string, [number, number]> = {
        N: [0, -1],
        S: [0, 1],
        W: [-1, 0],
        E: [1, 0],
      };
      const v = m[item.orient];
      if (v) {
        return (
          <line
            x1={cx}
            y1={cy}
            x2={cx + v[0] * d}
            y2={cy + v[1] * d}
            stroke={FURN_ARROW}
            strokeWidth={3}
            style={{ pointerEvents: 'none' }}
          />
        );
      }
    }
    return null;
  })();

  return (
    <g
      opacity={readOnly ? 0.3 : 1}
      transform={groupTransform}
      data-furn-id={item.id}
      data-furn-t={item.t}
      data-furn-rot={rot || undefined}
    >
      {isCircle(item) ? (
        <circle
          cx={cx}
          cy={cy}
          r={a.r}
          fill={fill}
          stroke={stroke}
          strokeWidth={strokeWidth}
          style={{ cursor: readOnly ? 'default' : 'move' }}
          onPointerDown={down}
        />
      ) : (
        <rect
          x={a.x + origin[0]}
          y={a.y + origin[1]}
          width={a.w}
          height={a.h}
          rx={2}
          fill={fill}
          stroke={stroke}
          strokeWidth={strokeWidth}
          style={{ cursor: readOnly ? 'default' : 'move' }}
          onPointerDown={down}
        />
      )}
      <text
        x={cx}
        y={cy}
        fontSize={11}
        fill={FURN_LABEL}
        textAnchor="middle"
        dominantBaseline="middle"
        style={{ pointerEvents: 'none' }}
      >
        {item.label ? String(item.label) : furnZh(item.t)}
      </text>
      {arrow}
    </g>
  );
}

// React.memo (阶段 3 / P2-1): 拖一件家具时, 仅被拖件 item 引用变化, 其余件跳过重渲。
// geometry 引用在家具拖拽期不变 (家具走 updateFurniture, 不动 G), 故几何模式只读叠加
// 在房间拖动时随 geometry 变化重渲 (家具锚定房间需跟随), 符合预期。
export default React.memo(FurnitureItem);
