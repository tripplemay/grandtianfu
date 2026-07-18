'use client';

import React, { useMemo } from 'react';
import type { CalibrationFeature } from 'lib/studioApi';

// calib-cure-b1 F009: 特征点标定的平面小窗 —— 轻量内联 SVG (刻意不复用 editor 画布, 太重)。
// 统一在毫米空间绘制: 房间 rect(几何像素)×mmPerPx 与 feature.world(mm) 同系, viewBox 取
// merge 成员 rect 并集外扩。内容: 成员轮廓 + 开口刻痕 (door_jamb/window_floor 成对地面
// 交点连线 = 开口跨度) + 全部特征点圆点 (当前待放高亮脉冲 / 已放打勾变绿 / 其余灰点)。
// F010 复用本组件 (props 契约见下), 纯展示件 —— 交互状态全部由宿主持有。

export interface CalibrationMiniMapRoom {
  id: string;
  rect: [number, number, number, number]; // 几何像素 [x, y, w, h]
  labelZh?: string;
}

const KIND_NOTCH_CLS: Record<string, string> = {
  door_jamb: 'text-amber-500',
  window_floor: 'text-sky-500',
};

export default function CalibrationMiniMap({
  rooms,
  mmPerPx,
  features,
  placedIds,
  activeId,
  highlightAxis,
  className = '',
}: {
  rooms: CalibrationMiniMapRoom[]; // merge 组成员 (轮廓)
  mmPerPx: number; // 几何像素 -> mm
  features: CalibrationFeature[]; // 特征池 (world 为 mm)
  placedIds: readonly string[]; // 已放置的 feature id (打勾变绿)
  activeId: string | null; // 当前待放 feature id (脉冲高亮)
  highlightAxis?: 'ns' | 'ew'; // F010 专家模式: 高亮南北走向墙(竖边)/东西走向墙(横边)
  className?: string;
}) {
  const placed = useMemo(() => new Set(placedIds), [placedIds]);

  // 平面小窗是 2D 俯视图: 异面点 (天花板/门窗顶, Z>0) 与其地面孪生同 XY 位置, 只画地面点去重
  // (高度差异由照片侧提示承担; 调用方把异面 target 的高亮映射到地面孪生 id)。
  const groundFeatures = useMemo(
    () => features.filter((f) => f.world[2] <= 1),
    [features],
  );

  // 成对开口刻痕: door:{oid}:a + door:{oid}:b -> 两地面交点连线 (开口在墙上的跨度)。
  const notches = useMemo(() => {
    const byOpening = new Map<string, CalibrationFeature[]>();
    for (const f of groundFeatures) {
      if (f.kind === 'wall_corner') continue;
      const key = f.id.replace(/:[ab]$/, '');
      byOpening.set(key, [...(byOpening.get(key) ?? []), f]);
    }
    return [...byOpening.values()].filter((pair) => pair.length === 2);
  }, [groundFeatures]);

  const box = useMemo(() => {
    if (rooms.length === 0) return null;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const r of rooms) {
      const [x, y, w, h] = r.rect;
      minX = Math.min(minX, x * mmPerPx);
      minY = Math.min(minY, y * mmPerPx);
      maxX = Math.max(maxX, (x + w) * mmPerPx);
      maxY = Math.max(maxY, (y + h) * mmPerPx);
    }
    const pad = Math.max(250, Math.max(maxX - minX, maxY - minY) * 0.06);
    return {
      x: minX - pad,
      y: minY - pad,
      w: maxX - minX + pad * 2,
      h: maxY - minY + pad * 2,
    };
  }, [rooms, mmPerPx]);

  if (box === null) return null;

  // 圆点/字号随图幅缩放 (SVG 用户单位 = mm); 轮廓/刻痕描边用 non-scaling 保持像素级粗细。
  const span = Math.max(box.w, box.h);
  const r = span * 0.022;
  const fontSize = span * 0.05;

  return (
    <svg
      data-testid="calib-minimap"
      viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`}
      className={`h-auto w-full rounded-lg bg-gray-100 dark:bg-navy-900 ${className}`.trim()}
      role="img"
      aria-label="标定房间平面小窗"
    >
      {/* 成员房间轮廓 (世界系与照片方位一致: X=东=右, Y=南=下) */}
      {rooms.map((room) => {
        const [x, y, w, h] = room.rect;
        return (
          <g key={room.id} className="text-gray-400 dark:text-gray-500">
            <rect
              x={x * mmPerPx}
              y={y * mmPerPx}
              width={w * mmPerPx}
              height={h * mmPerPx}
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={(x + w / 2) * mmPerPx}
              y={(y + h / 2) * mmPerPx}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={fontSize}
              fill="currentColor"
            >
              {room.labelZh || room.id}
            </text>
          </g>
        );
      })}
      {/* F010: 专家模式墙向高亮 —— 当前步该画哪个走向的墙, 图上直说 (A3 缺陷闭环) */}
      {highlightAxis &&
        rooms.map((room) => {
          const [x, y, w, h] = room.rect;
          const X0 = x * mmPerPx;
          const Y0 = y * mmPerPx;
          const X1 = (x + w) * mmPerPx;
          const Y1 = (y + h) * mmPerPx;
          const edges: Array<[number, number, number, number]> =
            highlightAxis === 'ns'
              ? [
                  [X0, Y0, X0, Y1],
                  [X1, Y0, X1, Y1],
                ]
              : [
                  [X0, Y0, X1, Y0],
                  [X0, Y1, X1, Y1],
                ];
          return (
            <g key={`hl-${room.id}`} className="text-brand-500">
              {edges.map(([ax, ay, bx, by], i) => (
                <line
                  key={i}
                  x1={ax}
                  y1={ay}
                  x2={bx}
                  y2={by}
                  stroke="currentColor"
                  strokeWidth={4}
                  vectorEffect="non-scaling-stroke"
                  opacity={0.85}
                />
              ))}
            </g>
          );
        })}
      {/* 开口刻痕: 门框琥珀 / 落地窗框天蓝 */}
      {notches.map((pair) => (
        <line
          key={pair[0].id}
          x1={pair[0].world[0]}
          y1={pair[0].world[1]}
          x2={pair[1].world[0]}
          y2={pair[1].world[1]}
          stroke="currentColor"
          strokeWidth={5}
          vectorEffect="non-scaling-stroke"
          className={KIND_NOTCH_CLS[pair[0].kind] ?? 'text-amber-500'}
        />
      ))}
      {/* 特征点: 待放脉冲 (brand) / 已放打勾 (emerald) / 其余灰点 (仅地面点, 异面点 2D 重叠) */}
      {groundFeatures.map((f) => {
        const [wx, wy] = f.world;
        const isPlaced = placed.has(f.id);
        const isActive = !isPlaced && f.id === activeId;
        return (
          <g key={f.id} data-feature-id={f.id}>
            {isActive && (
              <circle
                cx={wx}
                cy={wy}
                r={r}
                fill="currentColor"
                className="text-brand-500"
              >
                <animate
                  attributeName="r"
                  values={`${r};${r * 2.6};${r}`}
                  dur="1.5s"
                  repeatCount="indefinite"
                />
                <animate
                  attributeName="opacity"
                  values="0.5;0;0.5"
                  dur="1.5s"
                  repeatCount="indefinite"
                />
              </circle>
            )}
            <circle
              cx={wx}
              cy={wy}
              r={isActive ? r * 0.9 : r * 0.7}
              fill="currentColor"
              className={
                isPlaced
                  ? 'text-emerald-500'
                  : isActive
                  ? 'text-brand-500'
                  : 'text-gray-400 dark:text-gray-500'
              }
            />
            {isPlaced && (
              <polyline
                points={`${wx - r * 0.35},${wy + r * 0.02} ${wx - r * 0.08},${
                  wy + r * 0.3
                } ${wx + r * 0.4},${wy - r * 0.28}`}
                fill="none"
                stroke="#fff"
                strokeWidth={r * 0.18}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            )}
          </g>
        );
      })}
    </svg>
  );
}
