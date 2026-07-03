'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';

// 视口变换 (阶段 1): 持 {scale,tx,ty}, 内容层 <g transform="translate(tx,ty) scale(s)">。
// tx/ty/s 均以 viewBox 用户单位表达 (内容坐标系 == scale=1 时的 viewBox 坐标系)。
// 命中坐标由内层 g 的 getScreenCTM().inverse() 自动反算 (见各 canvas hook),
// 故所有现有拖拽/吸附逻辑零改。
//
// 坐标推导: 内容点 P -> viewBox 点 V = P*s + t -> 屏幕 = M0 * V (M0=svg.getScreenCTM,
//   与本变换无关, 仅 viewBox->屏幕的浏览器基变换)。
// 以光标为锚缩放: 光标 viewBox 坐标 V0 = M0^-1 * cursor (不随本变换变), 令新 t' 使
//   同一 viewBox 点保持在光标下: t' = V0 - (V0 - t)*(s'/s)。

export interface ViewportState {
  scale: number;
  tx: number;
  ty: number;
}

const MIN_SCALE = 0.2;
const MAX_SCALE = 12;
const FIT_PAD = 0.92;

const clampScale = (s: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));

export type ViewportStatePair = [
  ViewportState,
  React.Dispatch<React.SetStateAction<ViewportState>>,
];

// fitBox 的纯函数版 (P1 共享视口): 挂载前/无 svg 也能算出初始 fit 变换。
export function computeFitVp(
  viewBox: [number, number, number, number],
  box: { x: number; y: number; w: number; h: number } | null,
  pad = FIT_PAD,
): ViewportState {
  const [vx, vy, vw, vh] = viewBox;
  if (!box || box.w <= 0 || box.h <= 0) return { scale: 1, tx: 0, ty: 0 };
  const s = clampScale(Math.min(vw / box.w, vh / box.h) * pad);
  return {
    scale: s,
    tx: vx + vw / 2 - (box.x + box.w / 2) * s,
    ty: vy + vh / 2 - (box.y + box.h / 2) * s,
  };
}

// svg 的 viewBox->屏幕 基缩放 (M0.a)。未挂载时回退 1。
function baseA(svg: SVGSVGElement | null): number {
  const m = svg?.getScreenCTM();
  return m && m.a ? m.a : 1;
}

// 光标 client 坐标 -> viewBox 坐标 (经 M0^-1, 不含本视口变换)。
function cursorViewBox(
  svg: SVGSVGElement,
  clientX: number,
  clientY: number,
): { x: number; y: number } | null {
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  const m = svg.getScreenCTM();
  if (!m) return null;
  const p = pt.matrixTransform(m.inverse());
  return { x: p.x, y: p.y };
}

export function useViewport(
  svgRef: React.RefObject<SVGSVGElement>,
  // 受控视口 (P1 共享视口): 传入同一 state 对, 几何/家具两 Tab 共享缩放平移。
  state?: ViewportStatePair,
) {
  const inner = useState<ViewportState>({ scale: 1, tx: 0, ty: 0 });
  const [vp, setVp] = state ?? inner;
  const vpRef = useRef(vp);
  vpRef.current = vp;

  // 平移 / 捏合 内部态。
  const panRef = useRef<{ x: number; y: number; pointerId: number } | null>(
    null,
  );
  const pointers = useRef<Map<number, { x: number; y: number }>>(new Map());
  const pinchRef = useRef<{
    dist: number;
    cx: number;
    cy: number;
    scale: number;
    tx: number;
    ty: number;
  } | null>(null);
  const spaceRef = useRef(false);

  // ---- 空格键平移 (空格按下时拖拽 = 平移) ---- //
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const isFormEl = (el: EventTarget | null) => {
      const t = el as HTMLElement | null;
      if (!t) return false;
      const tag = t.tagName;
      return (
        tag === 'INPUT' ||
        tag === 'TEXTAREA' ||
        tag === 'SELECT' ||
        t.isContentEditable
      );
    };
    const down = (e: KeyboardEvent) => {
      // 仅当指针悬停在画布上时才进入空格平移 (P0 修复: 此前挂 window 全局,
      // 在页面任意处按空格都会 preventDefault 劫持滚动)。
      const overCanvas = svgRef.current?.matches(':hover') ?? false;
      if (e.code === 'Space' && overCanvas && !isFormEl(document.activeElement)) {
        spaceRef.current = true;
        e.preventDefault();
      }
    };
    const up = (e: KeyboardEvent) => {
      if (e.code === 'Space') spaceRef.current = false;
    };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
    };
  }, []);

  // ---- 以光标为锚缩放 ---- //
  const zoomAt = useCallback(
    (clientX: number, clientY: number, factor: number) => {
      const svg = svgRef.current;
      if (!svg) return;
      const v0 = cursorViewBox(svg, clientX, clientY);
      if (!v0) return;
      setVp((prev) => {
        const s2 = clampScale(prev.scale * factor);
        const k = s2 / prev.scale;
        return {
          scale: s2,
          tx: v0.x - (v0.x - prev.tx) * k,
          ty: v0.y - (v0.y - prev.ty) * k,
        };
      });
    },
    [svgRef],
  );

  // ---- 平移 (屏幕 px -> viewBox 单位) ---- //
  const panByScreen = useCallback(
    (dxScreen: number, dyScreen: number) => {
      const a = baseA(svgRef.current);
      setVp((prev) => ({
        ...prev,
        tx: prev.tx + dxScreen / a,
        ty: prev.ty + dyScreen / a,
      }));
    },
    [svgRef],
  );

  // ---- 滚轮: ctrl/cmd=锚点缩放; 否则平移。原生 WheelEvent (非被动监听, 见 StageSvg) ---- //
  const onWheel = useCallback(
    (e: WheelEvent) => {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        const factor = Math.exp(-e.deltaY * 0.0015);
        zoomAt(e.clientX, e.clientY, factor);
      } else {
        const a = baseA(svgRef.current);
        setVp((prev) => ({
          ...prev,
          tx: prev.tx - e.deltaX / a,
          ty: prev.ty - e.deltaY / a,
        }));
      }
    },
    [svgRef, zoomAt],
  );

  // ---- 鼠标指针 (bubble): 空格/中键=平移。返回 true=已消费(跳过元素拖拽) ---- //
  const onPointerDown = useCallback(
    (e: React.PointerEvent): boolean => {
      if (e.pointerType === 'touch') return false; // 触控走捕获阶段 (见下)
      if (spaceRef.current || e.button === 1) {
        e.preventDefault();
        panRef.current = { x: e.clientX, y: e.clientY, pointerId: e.pointerId };
        svgRef.current?.setPointerCapture(e.pointerId);
        return true;
      }
      return false;
    },
    [svgRef],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent): boolean => {
      if (panRef.current && panRef.current.pointerId === e.pointerId) {
        const last = panRef.current;
        panByScreen(e.clientX - last.x, e.clientY - last.y);
        panRef.current = { x: e.clientX, y: e.clientY, pointerId: e.pointerId };
        return true;
      }
      return false;
    },
    [panByScreen],
  );

  const onPointerUp = useCallback((e: React.PointerEvent): boolean => {
    if (panRef.current && panRef.current.pointerId === e.pointerId) {
      panRef.current = null;
      return true;
    }
    return false;
  }, []);

  // ---- 触控捕获阶段: 双指捏合缩放+平移。捕获阶段先于元素 onPointerDown 执行, 故
  //   元素 stopPropagation 不影响此处指针记录; 单指不消费 -> 保留拖拽元素能力。 ---- //
  const onTouchCaptureDown = useCallback((e: React.PointerEvent) => {
    if (e.pointerType !== 'touch') return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 2) {
      const pts = Array.from(pointers.current.values());
      pinchRef.current = {
        dist: Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) || 1,
        cx: (pts[0].x + pts[1].x) / 2,
        cy: (pts[0].y + pts[1].y) / 2,
        scale: vpRef.current.scale,
        tx: vpRef.current.tx,
        ty: vpRef.current.ty,
      };
    }
  }, []);

  const onTouchCaptureMove = useCallback(
    (e: React.PointerEvent) => {
      if (e.pointerType !== 'touch') return;
      if (!pinchRef.current || !pointers.current.has(e.pointerId)) return;
      pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.current.size < 2) return;
      // 捏合进行中: 阻断元素拖拽 (单指拖拽已被第二指升级为捏合)。
      e.stopPropagation();
      const pts = Array.from(pointers.current.values());
      const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) || 1;
      const cx = (pts[0].x + pts[1].x) / 2;
      const cy = (pts[0].y + pts[1].y) / 2;
      const svg = svgRef.current;
      const start = pinchRef.current;
      if (!svg) return;
      const vStart = cursorViewBox(svg, start.cx, start.cy);
      if (!vStart) return;
      const s2 = clampScale(start.scale * (dist / start.dist));
      const k = s2 / start.scale;
      const a = baseA(svg);
      setVp({
        scale: s2,
        tx: vStart.x - (vStart.x - start.tx) * k + (cx - start.cx) / a,
        ty: vStart.y - (vStart.y - start.ty) * k + (cy - start.cy) / a,
      });
    },
    [svgRef],
  );

  const onTouchCaptureUp = useCallback((e: React.PointerEvent) => {
    if (e.pointerType !== 'touch') return;
    pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) pinchRef.current = null;
  }, []);

  // 步进缩放 (P1): 以 viewBox 中心为锚, 供 ± 按钮与 Ctrl± 快捷键。
  const zoomStep = useCallback(
    (factor: number, viewBox: [number, number, number, number]) => {
      const cx = viewBox[0] + viewBox[2] / 2;
      const cy = viewBox[1] + viewBox[3] / 2;
      setVp((p) => {
        const s2 = clampScale(p.scale * factor);
        const k = s2 / p.scale;
        return { scale: s2, tx: cx - (cx - p.tx) * k, ty: cy - (cy - p.ty) * k };
      });
    },
    [setVp],
  );

  // ---- Fit / 100% / 缩放到选区 ---- //
  // 把内容包围盒 (内容坐标, 即 scale=1 时的 viewBox 坐标) 框入 viewBox。
  const fitBox = useCallback(
    (
      viewBox: [number, number, number, number],
      box: { x: number; y: number; w: number; h: number } | null,
      pad = FIT_PAD,
    ) => {
      const [vx, vy, vw, vh] = viewBox;
      if (!box || box.w <= 0 || box.h <= 0) {
        setVp({ scale: 1, tx: 0, ty: 0 });
        return;
      }
      const s = clampScale(Math.min(vw / box.w, vh / box.h) * pad);
      const bcx = box.x + box.w / 2;
      const bcy = box.y + box.h / 2;
      setVp({
        scale: s,
        tx: vx + vw / 2 - bcx * s,
        ty: vy + vh / 2 - bcy * s,
      });
    },
    [],
  );

  const reset100 = useCallback(() => setVp({ scale: 1, tx: 0, ty: 0 }), []);

  const transform = `translate(${vp.tx} ${vp.ty}) scale(${vp.scale})`;
  const zoomPct = Math.round(vp.scale * 100);

  return {
    scale: vp.scale,
    tx: vp.tx,
    ty: vp.ty,
    transform,
    zoomPct,
    onWheel,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onTouchCaptureDown,
    onTouchCaptureMove,
    onTouchCaptureUp,
    zoomAt,
    zoomStep,
    fitBox,
    reset100,
  };
}

export type Viewport = ReturnType<typeof useViewport>;
