'use client';

import React, { useMemo } from 'react';
import type { Geometry } from 'lib/floorplan/types';
import { type Furniture, sortByZ } from 'lib/floorplan/furniture';
import FurnitureItem from './FurnitureItem';

interface Props {
  furniture: Furniture[];
  geometry: Geometry;
  origin: [number, number];
  selectedId: string | null;
  scale?: number; // 视口缩放 (阶段 1): 透传给 FurnitureItem 选中描边反比。
  blockedId?: string | null; // 越界拖动被夹取的件 (P2-5): 红描边提示。
  readOnly?: boolean;
  onItemPointerDown?: (e: React.PointerEvent, id: string) => void;
}

// 家具层: 渲染全部家具件。key/选中均以稳定 id 为身份 (阶段 0): 删中间件不错位。
// 渲染次序按 z 升序 (P2-13): 高 z 后画=在上层; 稳定排序对无 z 数据保持原序。
// readOnly=true 时整层半透只读 (几何模式参考)。
function FurnitureLayer({
  furniture,
  geometry,
  origin,
  selectedId,
  scale = 1,
  blockedId,
  readOnly,
  onItemPointerDown,
}: Props) {
  const ordered = useMemo(() => sortByZ(furniture), [furniture]);
  return (
    // 几何模式只读参考层 (readOnly): 整层 pointer-events:none, 不遮挡其下几何图元的
    // 命中 (门窗端点/翻转把手/墙等); 家具模式保持默认可交互。
    <g style={readOnly ? { pointerEvents: 'none' } : undefined}>
      {ordered.map((it, i) => (
        <FurnitureItem
          key={it.id ?? `idx-${i}`}
          item={it}
          geometry={geometry}
          origin={origin}
          scale={scale}
          selected={!readOnly && selectedId != null && it.id === selectedId}
          blocked={!readOnly && blockedId != null && it.id === blockedId}
          readOnly={readOnly}
          onPointerDown={onItemPointerDown}
        />
      ))}
    </g>
  );
}

// React.memo (阶段 3 / P2-1): pan/zoom 或他模式状态变化时, 入参不变则整层跳过。
export default React.memo(FurnitureLayer);
