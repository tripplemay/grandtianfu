'use client';

import React, { useState } from 'react';
import type {
  DeriveResult,
  WallRaw,
  DerivedDoor,
  DerivedLeaf,
  DerivedWindow,
} from 'lib/floorplan/types';
import { wallIsExt, sweepFlag } from 'lib/floorplan/geometry';
import {
  WALL_SOLID,
  WALL_DASHED,
  WINDOW_STROKE,
  DOOR_SLIDING,
  DOOR_ARC,
  DOOR_LEAF,
  HOVER_STROKE,
} from 'lib/floorplan/theme';

interface Props {
  derived: DeriveResult | null;
  origin: [number, number];
  doorInsertMode: boolean;
  scale?: number; // 视口缩放 (阶段 3): 开门模式命中线宽随之反比。
  onWallDown: (e: React.PointerEvent, wall: WallRaw) => void;
}

// 派生墙/门/窗 只读叠加层 (§⑧)。门窗 pointerEvents:none; 开门模式下墙可点 (透明宽命中线)。
function DerivedWallsLayer({
  derived,
  origin,
  doorInsertMode,
  scale = 1,
  onWallDown,
}: Props) {
  if (!derived) return null;
  return (
    <g>
      {(derived._walls_raw ?? []).map((w, i) => (
        <WallLine
          key={`w${i}`}
          wall={w}
          origin={origin}
          doorInsertMode={doorInsertMode}
          scale={scale}
          onWallDown={onWallDown}
        />
      ))}
      {(derived.windows ?? []).map((wn, i) => (
        <WindowLine key={`win${i}`} win={wn} origin={origin} />
      ))}
      {(derived.doors ?? []).map((d, i) => (
        <DoorMark key={`d${i}`} door={d} origin={origin} />
      ))}
    </g>
  );
}

function WallLine({
  wall,
  origin,
  doorInsertMode,
  scale = 1,
  onWallDown,
}: {
  wall: WallRaw;
  origin: [number, number];
  doorInsertMode: boolean;
  scale?: number;
  onWallDown: (e: React.PointerEvent, wall: WallRaw) => void;
}) {
  const [hover, setHover] = useState(false);
  const dashed = wall.style === 'dashed';
  const col = dashed ? WALL_DASHED : WALL_SOLID;
  const tw =
    wall.style === 'thin' ? 2 : dashed ? 2 : wallIsExt(wall.role) ? 5 : 3;
  let coords: { x1: number; y1: number; x2: number; y2: number };
  if (wall.axis === 'v') {
    coords = {
      x1: wall.at + origin[0],
      y1: wall.lo + origin[1],
      x2: wall.at + origin[0],
      y2: wall.hi + origin[1],
    };
  } else {
    coords = {
      x1: wall.lo + origin[0],
      y1: wall.at + origin[1],
      x2: wall.hi + origin[0],
      y2: wall.at + origin[1],
    };
  }
  return (
    <g>
      <line
        {...coords}
        stroke={doorInsertMode && hover ? HOVER_STROKE : col}
        strokeWidth={tw}
        strokeLinecap="round"
        strokeDasharray={dashed ? '8 5' : undefined}
        style={{ pointerEvents: 'none' }}
      />
      {/* 开门模式: 叠加透明宽命中线, 易于点中细墙插门 (P2-6) */}
      {doorInsertMode && (
        <line
          {...coords}
          stroke="transparent"
          strokeWidth={16 / scale}
          strokeLinecap="round"
          style={{ cursor: 'crosshair', pointerEvents: 'stroke' }}
          onPointerDown={(e) => onWallDown(e, wall)}
          onPointerEnter={() => setHover(true)}
          onPointerLeave={() => setHover(false)}
        />
      )}
    </g>
  );
}

function WindowLine({
  win,
  origin,
}: {
  win: DerivedWindow;
  origin: [number, number];
}) {
  let coords: { x1: number; y1: number; x2: number; y2: number };
  if (win.axis === 'v') {
    coords = {
      x1: win.at + origin[0],
      y1: win.span[0] + origin[1],
      x2: win.at + origin[0],
      y2: win.span[1] + origin[1],
    };
  } else {
    coords = {
      x1: win.span[0] + origin[0],
      y1: win.at + origin[1],
      x2: win.span[1] + origin[0],
      y2: win.at + origin[1],
    };
  }
  return (
    <line
      {...coords}
      stroke={WINDOW_STROKE}
      strokeWidth={3}
      style={{ pointerEvents: 'none' }}
    />
  );
}

// 玻璃门预览色 (P5): 复用窗玻璃色系, 与木门 (DOOR_ARC/DOOR_LEAF/DOOR_SLIDING) 区分。
const DOOR_GLASS = '#7fa6bc';

// 一扇平开门叶 (P5): 弧 + 扇。glass=true 时改玻璃色。单扇 / 对开每扇共用。
function SwingLeaf({
  leaf,
  origin,
  glass,
}: {
  leaf: DerivedLeaf;
  origin: [number, number];
  glass: boolean;
}) {
  const h: [number, number] = [
    leaf.hinge_pt[0] + origin[0],
    leaf.hinge_pt[1] + origin[1],
  ];
  const j: [number, number] = [
    leaf.jamb_pt[0] + origin[0],
    leaf.jamb_pt[1] + origin[1],
  ];
  const tp: [number, number] = [
    leaf.open_tip[0] + origin[0],
    leaf.open_tip[1] + origin[1],
  ];
  const sf = sweepFlag(h, j, tp);
  return (
    <g>
      <path
        d={`M ${j[0]} ${j[1]} A ${leaf.width} ${leaf.width} 0 0 ${sf} ${tp[0]} ${tp[1]}`}
        fill="none"
        stroke={glass ? DOOR_GLASS : DOOR_ARC}
        strokeWidth={1}
        strokeDasharray="4 3"
        style={{ pointerEvents: 'none' }}
      />
      <line
        x1={h[0]}
        y1={h[1]}
        x2={tp[0]}
        y2={tp[1]}
        stroke={glass ? DOOR_GLASS : DOOR_LEAF}
        strokeWidth={2}
        style={{ pointerEvents: 'none' }}
      />
    </g>
  );
}

function DoorMark({
  door,
  origin,
}: {
  door: DerivedDoor;
  origin: [number, number];
}) {
  const glass = door.material === 'glass'; // P5 玻璃门预览着色
  if (door.door_type === 'sliding') {
    const n = door.panels ?? 2;
    const [lo, hi] = door.span;
    const len = (hi - lo) / n;
    const panels: React.ReactNode[] = [];
    for (let i = 0; i < n; i++) {
      const a = lo + i * len;
      const b = a + len;
      const off = i % 2 ? 4 : -4;
      let c: { x1: number; y1: number; x2: number; y2: number };
      if (door.axis === 'v') {
        c = {
          x1: door.at + origin[0] + off,
          y1: a + origin[1],
          x2: door.at + origin[0] + off,
          y2: b + origin[1],
        };
      } else {
        c = {
          x1: a + origin[0],
          y1: door.at + origin[1] + off,
          x2: b + origin[0],
          y2: door.at + origin[1] + off,
        };
      }
      panels.push(
        <line
          key={i}
          {...c}
          stroke={glass ? DOOR_GLASS : DOOR_SLIDING}
          strokeWidth={3}
          style={{ pointerEvents: 'none' }}
        />,
      );
    }
    return <g>{panels}</g>;
  }
  // 对开双扇 (P5): 引擎 build_door double -> leaves[]; 两扇各自渲染 (修复原按单扇/不渲染)。
  if (door.door_type === 'double' && door.leaves?.length) {
    return (
      <g>
        {door.leaves.map((lf, i) => (
          <SwingLeaf key={i} leaf={lf} origin={origin} glass={glass} />
        ))}
      </g>
    );
  }
  // 单扇平开
  if (!door.hinge_pt || !door.jamb_pt || !door.open_tip || door.width == null)
    return null;
  return (
    <SwingLeaf
      leaf={{
        hinge_pt: door.hinge_pt,
        jamb_pt: door.jamb_pt,
        open_tip: door.open_tip,
        width: door.width,
      }}
      origin={origin}
      glass={glass}
    />
  );
}

// React.memo (阶段 3 / P2-1): derived/origin/scale/doorInsertMode 不变则整层跳过重渲
// (拖房间几何变 -> derived 仍待派生, 期间引用不变, 不随被拖房每帧重建)。
export default React.memo(DerivedWallsLayer);
