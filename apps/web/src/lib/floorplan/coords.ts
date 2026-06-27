// 坐标系: 几何坐标 (引擎/数据) <-> 画布坐标 (SVG)。
// 画布坐标 = 几何坐标 + origin。origin 从 G.meta.origin 读 (§① 勿硬编码 150,250)。

import type { Geometry } from './types';

export const FALLBACK_ORIGIN: [number, number] = [150, 250];
export const FALLBACK_VIEWBOX: [number, number, number, number] = [0, 0, 2200, 1800];

export function readOrigin(g: Geometry | null | undefined): [number, number] {
  const o = g?.meta?.origin;
  if (Array.isArray(o) && o.length === 2 && typeof o[0] === 'number' && typeof o[1] === 'number') {
    return [o[0], o[1]];
  }
  return FALLBACK_ORIGIN;
}

export function readViewBox(g: Geometry | null | undefined): [number, number, number, number] {
  const v = g?.meta?.canvas_viewbox;
  if (Array.isArray(v) && v.length === 4 && v.every((n) => typeof n === 'number')) {
    return [v[0], v[1], v[2], v[3]];
  }
  return FALLBACK_VIEWBOX;
}

export function readGrid(g: Geometry | null | undefined): number {
  const grid = g?.meta?.grid;
  return typeof grid === 'number' && grid > 0 ? grid : 5;
}

// 几何坐标 -> 画布坐标。
export function geoToCanvasX(gx: number, origin: [number, number]): number {
  return gx + origin[0];
}
export function geoToCanvasY(gy: number, origin: [number, number]): number {
  return gy + origin[1];
}

// 画布坐标 -> 几何坐标。
export function canvasToGeoX(cx: number, origin: [number, number]): number {
  return cx - origin[0];
}
export function canvasToGeoY(cy: number, origin: [number, number]): number {
  return cy - origin[1];
}
