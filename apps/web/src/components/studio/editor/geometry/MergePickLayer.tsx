'use client';

import React from 'react';
import type { Geometry } from 'lib/floorplan/types';
import type { MergePick } from 'lib/floorplan/merge';
import { MERGE_CAND_FILL, MERGE_CAND_STROKE } from 'lib/floorplan/theme';

interface Props {
  geometry: Geometry;
  pick: MergePick | null;
  origin: [number, number];
  scale?: number;
}

// 贴合并房点选高亮层 (CP5v2): 候选房绿色虚线描边 + 微填充。指针穿透 (点击仍落在
// 下层房块上, 由 onRoomPointerDown 的点选拦截消费), 描边随 scale 反比恒定屏宽。
function MergePickLayer({ geometry, pick, origin, scale = 1 }: Props) {
  if (!pick) return null;
  const ids = new Set(pick.candidates);
  const [ox, oy] = origin;
  return (
    <g style={{ pointerEvents: 'none' }} data-testid="merge-pick-layer">
      {geometry.rooms
        .filter((r) => ids.has(r.id))
        .map((r) => {
          const [x, y, w, h] = r.rect;
          return (
            <rect
              key={r.id}
              x={x + ox}
              y={y + oy}
              width={w}
              height={h}
              rx={2}
              fill={MERGE_CAND_FILL}
              stroke={MERGE_CAND_STROKE}
              strokeWidth={2.5 / scale}
              strokeDasharray={`${8 / scale} ${5 / scale}`}
            />
          );
        })}
    </g>
  );
}

// React.memo: 点选模式外恒 null; 模式中仅 pick/scale 变化时重渲。
export default React.memo(MergePickLayer);
