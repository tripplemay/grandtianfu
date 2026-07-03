// 真实单位换算 (升级计划 P1): 数据层恒存引擎 px (1px=meta.mm_per_px mm, 默认 10),
// 展示层补 mm/㎡, 消除「1=10mm」心算负担。
import type { Geometry } from 'lib/studioApi';

export function mmPerPx(g: Geometry | null | undefined): number {
  const v = (g?.meta as { mm_per_px?: number } | undefined)?.mm_per_px;
  return typeof v === 'number' && v > 0 ? v : 10;
}

export function pxToMm(px: number, g: Geometry | null | undefined): number {
  return Math.round(px * mmPerPx(g));
}

export function fmtMm(px: number, g: Geometry | null | undefined): string {
  return `${pxToMm(px, g)}mm`;
}

export function fmtAreaSqm(
  wPx: number,
  hPx: number,
  g: Geometry | null | undefined,
): string {
  const m = mmPerPx(g);
  const sqm = (wPx * m * hPx * m) / 1_000_000;
  return `${sqm.toFixed(1)}㎡`;
}

// 墙面材质词表 (材质A): 与引擎 prompt_gen.WALL_MATERIAL_EN / axon.WALL_FINISH_TINT 同枚举。
export const WALL_MATERIALS: ReadonlyArray<{ value: string; zh: string }> = [
  { value: '', zh: '默认(乳胶漆白)' },
  { value: 'wood_panel', zh: '木饰面' },
  { value: 'stone', zh: '石材' },
  { value: 'tile', zh: '瓷砖' },
  { value: 'paint', zh: '乳胶漆(彩)' },
  { value: 'mirror', zh: '镜面' },
  { value: 'wallpaper', zh: '壁纸' },
];

export const WALL_SIDES: ReadonlyArray<{ side: 'N' | 'S' | 'E' | 'W'; zh: string }> = [
  { side: 'N', zh: '北墙' },
  { side: 'S', zh: '南墙' },
  { side: 'E', zh: '东墙' },
  { side: 'W', zh: '西墙' },
];
