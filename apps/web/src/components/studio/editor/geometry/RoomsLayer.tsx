'use client';

import React from 'react';
import type { Room } from 'lib/floorplan/types';
import type { EditorSelection } from '../EditorStage';
import RoomRect from './RoomRect';

interface Props {
  rooms: Room[];
  origin: [number, number];
  selection?: EditorSelection;
  errorRoomIds?: Set<string>;
  scale?: number; // 视口缩放 (阶段 1): 透传给 RoomRect 选中描边反比。
  onPointerDown?: (e: React.PointerEvent, room: Room) => void;
  readOnly?: boolean; // 家具模式: 淡显只读参考 (调用方负责外层 g 降透明度/禁指针)。
}

const noop = () => undefined;

// 房间色块层 (审查清单 Q2-#5)。几何模式可交互 (选中/冲突高亮/拖动);
// 家具模式 readOnly 复用同一 RoomRect (dim), 不再手写一份。
function RoomsLayer({
  rooms,
  origin,
  selection,
  errorRoomIds,
  scale = 1,
  onPointerDown,
  readOnly,
}: Props) {
  return (
    <>
      {rooms.map((r) => (
        <RoomRect
          key={r.id}
          room={r}
          origin={origin}
          scale={scale}
          selected={
            !readOnly && (selection?.room === r.id || selection?.room2 === r.id)
          }
          error={!readOnly && (errorRoomIds?.has(r.id) ?? false)}
          dim={readOnly}
          onPointerDown={readOnly ? noop : onPointerDown ?? noop}
        />
      ))}
    </>
  );
}

// React.memo (阶段 3 / P2-1): pan/zoom 时 rooms/origin/scale 不变则整层跳过重渲;
// 拖拽期虽因 rooms/errorRoomIds 引用变化而重渲, 但子 RoomRect 各自 memo 短路。
export default React.memo(RoomsLayer);
