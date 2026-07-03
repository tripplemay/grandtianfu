'use client';

import React, { useEffect, useId } from 'react';
import {
  CANVAS_BG,
  GRID_MINOR,
  GRID_MAJOR,
  SCALE_BAR,
} from 'lib/floorplan/theme';

interface Props {
  svgRef: React.RefObject<SVGSVGElement>;
  viewBox: [number, number, number, number];
  onPointerDown: (e: React.PointerEvent) => void;
  onPointerMove: (e: React.PointerEvent) => void;
  onPointerUp: (e: React.PointerEvent) => void;
  onPointerCancel?: (e: React.PointerEvent) => void;
  // 原生 WheelEvent: 经非被动监听绑定 (passive:false), 使 preventDefault 生效且不报警。
  onWheel?: (e: WheelEvent) => void;
  // 触控捕获阶段: 双指捏合 (先于元素 onPointerDown, 不受其 stopPropagation 影响)。
  onPointerDownCapture?: (e: React.PointerEvent) => void;
  onPointerMoveCapture?: (e: React.PointerEvent) => void;
  onPointerUpCapture?: (e: React.PointerEvent) => void;
  onPointerCancelCapture?: (e: React.PointerEvent) => void;
  // 视口变换 (阶段 1): children 全部移入被 transform 的内容层 <g>; 背景捕获 rect
  // 留在外层 (随视口固定全屏覆盖)。命中坐标经 contentRef.getScreenCTM() 自动兼容。
  contentRef?: React.Ref<SVGGElement>;
  contentTransform?: string;
  // 阶段 3: 视口缩放比 (比例尺条 px 长度 / grid 反比); 拖拽态 (cursor=grabbing)。
  scale?: number;
  dragging?: boolean;
  // 网格 / 比例尺 (P3): 默认开启; 网格步长以内容(几何)单位计。
  showGrid?: boolean;
  gridStep?: number;
  showScaleBar?: boolean;
  scaleBarLabel?: string;
  children: React.ReactNode;
}

const GRID_STEP_DEFAULT = 100; // 内容单位 (1px=10mm -> 100=1m), 主网格步长。
const GRID_MINOR_DIV = 5; // 次网格 = 主网格 / 5。

// 受控 inline SVG 画布外壳 (审查清单 Q2-#3)。EditorStage / FurnitureStage 共用:
// viewBox + 底色 (CANVAS_BG) + 背景捕获 rect (data-bg=1, 空白点击=清选/落点) +
// pointer 回调透传 + 视口变换内容层 + 阶段 3 网格/比例尺。非 canvas (红线)。
export default function StageSvg({
  svgRef,
  viewBox,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onPointerCancel,
  onWheel,
  onPointerDownCapture,
  onPointerMoveCapture,
  onPointerUpCapture,
  onPointerCancelCapture,
  contentRef,
  contentTransform,
  scale = 1,
  dragging = false,
  showGrid = true,
  gridStep = GRID_STEP_DEFAULT,
  showScaleBar = true,
  scaleBarLabel = '1 m',
  children,
}: Props) {
  // 非被动 wheel 监听: React onWheel 默认 passive, preventDefault 无效且报警。
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || !onWheel) return;
    const handler = (e: WheelEvent) => onWheel(e);
    svg.addEventListener('wheel', handler, { passive: false });
    return () => svg.removeEventListener('wheel', handler);
  }, [svgRef, onWheel]);

  const uid = useId().replace(/[:]/g, '');
  const minorId = `grid-minor-${uid}`;
  const majorId = `grid-major-${uid}`;
  const minor = gridStep / GRID_MINOR_DIV;

  const [vx, vy, vw, vh] = viewBox;
  // 网格铺满 (含平移余量): 以 viewBox 为基扩 1 倍向四周延展, 缩小/平移时不露空。
  const gx = vx - vw;
  const gy = vy - vh;
  const gw = vw * 3;
  const gh = vh * 3;

  // 比例尺条 (外层, 不随视口变换): 长度 = gridStep * scale (viewBox 单位), 故屏幕上
  // 表示 gridStep 个内容单位; 位置固定在 viewBox 左下角 = 屏幕左下角。
  const barLen = gridStep * scale;
  const barX = vx + vw * 0.02;
  const barY = vy + vh - vh * 0.03;
  const barTick = vh * 0.012;
  const barStroke = Math.max(vw, vh) * 0.0015;

  return (
    <svg
      ref={svgRef}
      viewBox={viewBox.join(' ')}
      xmlns="http://www.w3.org/2000/svg"
      className={`block h-auto w-full touch-none select-none${
        dragging ? ' cursor-grabbing' : ''
      }`}
      style={{ background: CANVAS_BG }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      data-testid="stage-svg"
      onPointerDownCapture={onPointerDownCapture}
      onPointerMoveCapture={onPointerMoveCapture}
      onPointerUpCapture={onPointerUpCapture}
      onPointerCancelCapture={onPointerCancelCapture}
    >
      {showGrid && (
        <defs>
          <pattern
            id={minorId}
            width={minor}
            height={minor}
            patternUnits="userSpaceOnUse"
          >
            <path
              d={`M ${minor} 0 L 0 0 0 ${minor}`}
              fill="none"
              stroke={GRID_MINOR}
              strokeWidth={0.5}
            />
          </pattern>
          <pattern
            id={majorId}
            width={gridStep}
            height={gridStep}
            patternUnits="userSpaceOnUse"
          >
            <rect width={gridStep} height={gridStep} fill={`url(#${minorId})`} />
            <path
              d={`M ${gridStep} 0 L 0 0 0 ${gridStep}`}
              fill="none"
              stroke={GRID_MAJOR}
              strokeWidth={1}
            />
          </pattern>
        </defs>
      )}

      {/* 背景捕获层: 空白点击 = 清选 / 自由墙落点。留在视口变换外, 始终全屏覆盖。 */}
      <rect
        data-bg="1"
        x={viewBox[0]}
        y={viewBox[1]}
        width={viewBox[2]}
        height={viewBox[3]}
        fill="transparent"
      />
      {/* 视口变换内容层 */}
      <g
        data-testid="content-layer"
        ref={contentRef}
        transform={contentTransform}
      >
        {showGrid && (
          <rect
            data-testid="grid-bg"
            x={gx}
            y={gy}
            width={gw}
            height={gh}
            fill={`url(#${majorId})`}
            style={{ pointerEvents: 'none' }}
          />
        )}
        {children}
      </g>

      {/* 比例尺 (P3): 外层固定, pointerEvents:none。 */}
      {showScaleBar && (
        <g data-testid="scale-bar" style={{ pointerEvents: 'none' }}>
          <line
            x1={barX}
            y1={barY}
            x2={barX + barLen}
            y2={barY}
            stroke={SCALE_BAR}
            strokeWidth={barStroke}
          />
          <line
            x1={barX}
            y1={barY - barTick}
            x2={barX}
            y2={barY + barTick}
            stroke={SCALE_BAR}
            strokeWidth={barStroke}
          />
          <line
            x1={barX + barLen}
            y1={barY - barTick}
            x2={barX + barLen}
            y2={barY + barTick}
            stroke={SCALE_BAR}
            strokeWidth={barStroke}
          />
          <text
            x={barX + barLen / 2}
            y={barY - barTick * 1.6}
            fontSize={vh * 0.018}
            fill={SCALE_BAR}
            textAnchor="middle"
          >
            {scaleBarLabel}
          </text>
        </g>
      )}
    </svg>
  );
}
