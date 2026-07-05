'use client';

import React from 'react';
import type { Room, SpaceDef } from 'lib/floorplan/types';
import { groupOutlineSegments } from 'lib/floorplan/geometry';
import { groupUnionArea } from 'lib/floorplan/merge';
import {
  ROOM_STROKE,
  ROOM_LABEL,
  STROKE_SELECTED,
  STROKE_ERROR,
} from 'lib/floorplan/theme';
import type { EditorSelection } from '../EditorStage';
import RoomRect from './RoomRect';

interface Props {
  rooms: Room[];
  // 组标签取 space 标签 (CP5v2): 并房后名称归目标房, 与代表房 label 可能不一致。
  spaces?: Record<string, SpaceDef>;
  origin: [number, number];
  selection?: EditorSelection;
  errorRoomIds?: Set<string>;
  scale?: number; // 视口缩放 (阶段 1): 透传给 RoomRect 选中描边反比。
  onPointerDown?: (e: React.PointerEvent, room: Room) => void;
  readOnly?: boolean; // 家具模式: 淡显只读参考 (调用方负责外层 g 降透明度/禁指针)。
}

const noop = () => undefined;

// 异形组统一装饰 (P3 共享边不描边 + 单label): 画并集外轮廓 (共享/内部边已挖掉) + 组中心
// 单一 id/zh/面积 标签。选中/冲突高亮作用于整组外框。成员填充块由各自 plain RoomRect 提供。
function GroupDecor({
  members,
  spaces,
  origin,
  selected,
  error,
  scale,
}: {
  members: Room[];
  spaces?: Record<string, SpaceDef>;
  origin: [number, number];
  selected: boolean;
  error: boolean;
  scale: number;
}) {
  const [ox, oy] = origin;
  const segs = groupOutlineSegments(members.map((r) => r.rect));
  const stroke = error
    ? STROKE_ERROR
    : selected
    ? STROKE_SELECTED
    : ROOM_STROKE;
  const strokeWidth = error ? 4 / scale : selected ? 3 / scale : 1;
  // 组代表 (最大面积, 平局最小 id) —— 与引擎 group rep 规则一致。
  const primary = members.reduce((best, r) => {
    const a = r.rect[2] * r.rect[3];
    const ba = best.rect[2] * best.rect[3];
    if (a > ba) return r;
    if (a === ba && r.id < best.id) return r;
    return best;
  });
  const [px, py, pw, ph] = primary.rect;
  const cx = px + pw / 2 + ox;
  const cy = py + ph / 2 + oy;
  // 组名 = space 标签优先 (CP5v2 并房「名称归目标房」, 并房时已刷新), 退回代表房 label。
  const labelZh = spaces?.[primary.space]?.label || primary.label?.zh || '';
  // 组面积 = 精确矩形并集 (同组允许净矩形重叠, 求和会双计; CP5v3 与侧栏同源)。
  const areaM2 = groupUnionArea(members.map((r) => r.rect)) / 10000;
  return (
    <g style={{ pointerEvents: 'none' }}>
      {segs.map(([x1, y1, x2, y2], i) => (
        <line
          key={i}
          x1={x1 + ox}
          y1={y1 + oy}
          x2={x2 + ox}
          y2={y2 + oy}
          stroke={stroke}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
        />
      ))}
      <text
        x={cx}
        y={py + oy + 18}
        fontSize={12}
        fontWeight={600}
        fill={ROOM_LABEL}
        textAnchor="middle"
        dominantBaseline="middle"
      >
        {primary.id}
      </text>
      <text
        x={cx}
        y={cy}
        fontSize={12}
        fontWeight={600}
        fill={ROOM_LABEL}
        textAnchor="middle"
        dominantBaseline="middle"
      >
        {labelZh || primary.id}
      </text>
      <text
        x={cx}
        y={cy + 15}
        fontSize={9}
        fill={ROOM_LABEL}
        opacity={0.75}
        textAnchor="middle"
        dominantBaseline="middle"
      >
        {`${areaM2.toFixed(1)}㎡`}
      </text>
    </g>
  );
}

// 房间色块层 (审查清单 Q2-#5)。几何模式可交互 (选中/冲突高亮/拖动);
// 家具模式 readOnly 复用同一 RoomRect (dim), 不再手写一份。
// 异形 (P3): 同 merge 房聚为一个逻辑房间 —— 成员画 plain 填充块, 组统一画外框 + 单label。
function RoomsLayer({
  rooms,
  spaces,
  origin,
  selection,
  errorRoomIds,
  scale = 1,
  onPointerDown,
  readOnly,
}: Props) {
  // 多选高亮集合 (阶段 5a / P2-7): rooms[] + 兼容 room/room2。
  const selSet = new Set<string>(selection?.rooms ?? []);
  if (selection?.room) selSet.add(selection.room);
  if (selection?.room2) selSet.add(selection.room2);

  // 分组: merge 非空且 >=2 成员 -> 逻辑组; 其余单房。只读模式不做组装饰 (淡显参考层)。
  const groupMembers = new Map<string, Room[]>();
  if (!readOnly) {
    for (const r of rooms) {
      if (!r.merge || groupMembers.has(r.merge)) continue;
      const members = rooms.filter((x) => x.merge && x.merge === r.merge);
      if (members.length >= 2) groupMembers.set(r.merge, members);
    }
  }
  const groupedIds = new Set<string>();
  groupMembers.forEach((m) => m.forEach((r) => groupedIds.add(r.id)));
  // 组成员地板色统一按代表房 type (CP5v3): 旧数据成员 type 不一致时观感仍为一个房间。
  const groupFillType = new Map<string, string>();
  groupMembers.forEach((members) => {
    const rep = members.reduce((best, r) => {
      const a = r.rect[2] * r.rect[3];
      const ba = best.rect[2] * best.rect[3];
      if (a > ba) return r;
      if (a === ba && r.id < best.id) return r;
      return best;
    });
    members.forEach((r) => groupFillType.set(r.id, rep.type));
  });

  return (
    <>
      {rooms.map((r) => (
        <RoomRect
          key={r.id}
          room={r}
          origin={origin}
          scale={scale}
          selected={!readOnly && selSet.has(r.id)}
          error={!readOnly && (errorRoomIds?.has(r.id) ?? false)}
          dim={readOnly}
          plain={!readOnly && groupedIds.has(r.id)}
          fillType={groupFillType.get(r.id)}
          onPointerDown={readOnly ? noop : onPointerDown ?? noop}
        />
      ))}
      {[...groupMembers.entries()].map(([mid, members]) => (
        <GroupDecor
          key={`grp-${mid}`}
          members={members}
          spaces={spaces}
          origin={origin}
          selected={members.some((r) => selSet.has(r.id))}
          error={members.some((r) => errorRoomIds?.has(r.id) ?? false)}
          scale={scale}
        />
      ))}
    </>
  );
}

// React.memo (阶段 3 / P2-1): pan/zoom 时 rooms/origin/scale 不变则整层跳过重渲;
// 拖拽期虽因 rooms/errorRoomIds 引用变化而重渲, 但子 RoomRect 各自 memo 短路。
export default React.memo(RoomsLayer);
