'use client';

import React from 'react';
import type { Geometry } from 'lib/floorplan/types';
import type { Furniture } from 'lib/floorplan/furniture';
import FurnitureItem from './FurnitureItem';

interface Props {
  furniture: Furniture[];
  geometry: Geometry;
  origin: [number, number];
  selectedId: string | null;
  scale?: number; // 视口缩放 (阶段 1): 透传给 FurnitureItem 选中描边反比。
  readOnly?: boolean;
  onItemPointerDown?: (e: React.PointerEvent, id: string) => void;
}

// 家具层: 渲染全部家具件。key/选中均以稳定 id 为身份 (阶段 0): 删中间件不错位。
// readOnly=true 时整层半透只读 (几何模式参考)。
export default function FurnitureLayer({
  furniture,
  geometry,
  origin,
  selectedId,
  scale = 1,
  readOnly,
  onItemPointerDown,
}: Props) {
  return (
    <g>
      {furniture.map((it, i) => (
        <FurnitureItem
          key={it.id ?? `idx-${i}`}
          item={it}
          geometry={geometry}
          origin={origin}
          scale={scale}
          selected={!readOnly && selectedId != null && it.id === selectedId}
          readOnly={readOnly}
          onPointerDown={onItemPointerDown}
        />
      ))}
    </g>
  );
}
