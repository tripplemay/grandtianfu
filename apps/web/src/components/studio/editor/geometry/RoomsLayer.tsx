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
  onPointerDown?: (e: React.PointerEvent, room: Room) => void;
  readOnly?: boolean; // 家具模式: 淡显只读参考 (调用方负责外层 g 降透明度/禁指针)。
}

const noop = () => undefined;

// 房间色块层 (审查清单 Q2-#5)。几何模式可交互 (选中/冲突高亮/拖动);
// 家具模式 readOnly 复用同一 RoomRect (dim), 不再手写一份。
export default function RoomsLayer({
  rooms,
  origin,
  selection,
  errorRoomIds,
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
          selected={
            !readOnly &&
            (selection?.room === r.id || selection?.room2 === r.id)
          }
          error={!readOnly && (errorRoomIds?.has(r.id) ?? false)}
          dim={readOnly}
          onPointerDown={readOnly ? noop : onPointerDown ?? noop}
        />
      ))}
    </>
  );
}
