'use client';

import React from 'react';
import type { Furniture } from 'lib/floorplan/furniture';
import {
  furnColor,
  furnAbs,
  furnZh,
  isCircle,
  catalogEntry,
} from 'lib/floorplan/furniture';
import { detailPrims } from 'lib/floorplan/furnShapes';
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

// 单件家具 (矩形/圆形) + 中文标签 + 朝向贴边条 (orient 那侧的床头板/靠背/柜背, 随 rot 转)。
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
  const raw = furnColor(item.t) ?? item.color ?? FURN_FILL_FALLBACK;
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

  // a11y (阶段 5b / P3): 图元加 role + aria-label (类型/朝向) + 选中态。
  const ariaLabel = `家具 ${item.label ? String(item.label) : furnZh(item.t)} ${
    item.t
  }`;
  const a11y = readOnly
    ? { role: 'img' as const, 'aria-label': ariaLabel }
    : {
        role: 'button' as const,
        'aria-label': ariaLabel,
        'aria-pressed': selected,
      };

  // 声明式俯视外形 (Phase C-3 / #3-2): 有 plan2d_spec 的类型画内部细节 (床头板/扶手/盆/门线),
  // 与画廊平面图同源同解释器。无 spec 的方向件退回"朝向贴边条"(#3-1)。圆形/无 orient 件不画。
  const spec = catalogEntry(item.t)?.plan2d_spec;
  const detail = (() => {
    if (isCircle(item)) return null;
    const bx = a.x + origin[0];
    const by = a.y + origin[1];
    if (spec && spec.length) {
      const prims = detailPrims(bx, by, a.w, a.h, item.orient, spec);
      return prims.map((p, i) =>
        p.k === 'line' ? (
          <line
            key={i}
            x1={p.x1}
            y1={p.y1}
            x2={p.x2}
            y2={p.y2}
            stroke={FURN_ARROW}
            strokeWidth={1}
            opacity={0.55}
            style={{ pointerEvents: 'none' }}
          />
        ) : (
          <rect
            key={i}
            x={p.x}
            y={p.y}
            width={p.w}
            height={p.h}
            rx={p.rx ?? 0}
            fill={p.hollow ? 'none' : FURN_ARROW}
            fillOpacity={p.hollow ? undefined : 0.4}
            stroke={p.hollow ? FURN_ARROW : undefined}
            strokeWidth={p.hollow ? 1.2 : undefined}
            style={{ pointerEvents: 'none' }}
          />
        ),
      );
    }
    // 无 spec: 保留 #3-1 朝向贴边条。
    if (!item.orient) return null;
    const th = Math.max(3, Math.min(a.w, a.h) * 0.22);
    const edge: Record<string, [number, number, number, number]> = {
      N: [bx, by, a.w, th],
      S: [bx, by + a.h - th, a.w, th],
      W: [bx, by, th, a.h],
      E: [bx + a.w - th, by, th, a.h],
    };
    const r = edge[item.orient];
    if (!r) return null;
    return (
      <rect
        x={r[0]}
        y={r[1]}
        width={r[2]}
        height={r[3]}
        fill={FURN_ARROW}
        fillOpacity={0.55}
        rx={1.5}
        style={{ pointerEvents: 'none' }}
      />
    );
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
          {...a11y}
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
          {...a11y}
        />
      )}
      {detail}
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
    </g>
  );
}

// React.memo (阶段 3 / P2-1): 拖一件家具时, 仅被拖件 item 引用变化, 其余件跳过重渲。
// geometry 引用在家具拖拽期不变 (家具走 updateFurniture, 不动 G), 故几何模式只读叠加
// 在房间拖动时随 geometry 变化重渲 (家具锚定房间需跟随), 符合预期。
export default React.memo(FurnitureItem);
