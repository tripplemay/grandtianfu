'use client';

import React from 'react';
import type { DeriveResult, WallRaw, DerivedDoor, DerivedWindow } from 'lib/floorplan/types';
import { wallIsExt, sweepFlag } from 'lib/floorplan/geometry';

interface Props {
  derived: DeriveResult | null;
  origin: [number, number];
  doorInsertMode: boolean;
  onWallDown: (e: React.PointerEvent, wall: WallRaw) => void;
}

// 派生墙/门/窗 只读叠加层 (§⑧)。门窗 pointerEvents:none; 开门模式下墙可点。
export default function DerivedWallsLayer({
  derived,
  origin,
  doorInsertMode,
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
  onWallDown,
}: {
  wall: WallRaw;
  origin: [number, number];
  doorInsertMode: boolean;
  onWallDown: (e: React.PointerEvent, wall: WallRaw) => void;
}) {
  const dashed = wall.style === 'dashed';
  const col = dashed ? '#9a9a9a' : '#444';
  const tw = wall.style === 'thin' ? 2 : dashed ? 2 : wallIsExt(wall.role) ? 5 : 3;
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
    <line
      {...coords}
      stroke={col}
      strokeWidth={tw}
      strokeLinecap="round"
      strokeDasharray={dashed ? '8 5' : undefined}
      style={doorInsertMode ? { cursor: 'crosshair' } : { pointerEvents: 'none' }}
      onPointerDown={doorInsertMode ? (e) => onWallDown(e, wall) : undefined}
    />
  );
}

function WindowLine({ win, origin }: { win: DerivedWindow; origin: [number, number] }) {
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
    <line {...coords} stroke="#2a6cb0" strokeWidth={3} style={{ pointerEvents: 'none' }} />
  );
}

function DoorMark({ door, origin }: { door: DerivedDoor; origin: [number, number] }) {
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
        <line key={i} {...c} stroke="#7a5a3c" strokeWidth={3} style={{ pointerEvents: 'none' }} />,
      );
    }
    return <g>{panels}</g>;
  }
  if (!door.hinge_pt || !door.jamb_pt || !door.open_tip || door.width == null) return null;
  const h: [number, number] = [door.hinge_pt[0] + origin[0], door.hinge_pt[1] + origin[1]];
  const j: [number, number] = [door.jamb_pt[0] + origin[0], door.jamb_pt[1] + origin[1]];
  const tp: [number, number] = [door.open_tip[0] + origin[0], door.open_tip[1] + origin[1]];
  const sf = sweepFlag(h, j, tp);
  return (
    <g>
      <path
        d={`M ${j[0]} ${j[1]} A ${door.width} ${door.width} 0 0 ${sf} ${tp[0]} ${tp[1]}`}
        fill="none"
        stroke="#b08a5a"
        strokeWidth={1}
        strokeDasharray="4 3"
        style={{ pointerEvents: 'none' }}
      />
      <line
        x1={h[0]}
        y1={h[1]}
        x2={tp[0]}
        y2={tp[1]}
        stroke="#7a3f2a"
        strokeWidth={2}
        style={{ pointerEvents: 'none' }}
      />
    </g>
  );
}
