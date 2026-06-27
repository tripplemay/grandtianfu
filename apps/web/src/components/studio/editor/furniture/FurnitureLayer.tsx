'use client';

import React from 'react';
import type { Geometry } from 'lib/floorplan/types';
import type { Furniture } from 'lib/floorplan/furniture';
import FurnitureItem from './FurnitureItem';

interface Props {
  furniture: Furniture[];
  geometry: Geometry;
  origin: [number, number];
  selectedIndex: number | null;
  readOnly?: boolean;
  onItemPointerDown?: (e: React.PointerEvent, index: number) => void;
}

// 家具层: 渲染全部家具件。readOnly=true 时整层半透只读 (几何模式参考)。
export default function FurnitureLayer({
  furniture,
  geometry,
  origin,
  selectedIndex,
  readOnly,
  onItemPointerDown,
}: Props) {
  return (
    <g>
      {furniture.map((it, i) => (
        <FurnitureItem
          key={i}
          item={it}
          index={i}
          geometry={geometry}
          origin={origin}
          selected={!readOnly && selectedIndex === i}
          readOnly={readOnly}
          onPointerDown={onItemPointerDown}
        />
      ))}
    </g>
  );
}
