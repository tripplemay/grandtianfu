'use client';

import React from 'react';
import { Badge, type BadgeTone } from 'components/studio/ui/status';
import type {
  CalibrationPreviewResult,
  CalibrationWireframeRoom,
} from 'lib/studioApi';

// calib-cure-b1 F002: 标定预览确认门的展示件, 从 PerspectiveCalibrator 抽出 ——
// F009 特征点对齐模式将复用同一确认门 (线框叠照片 + 误差评级 + reasons)。
//
// - CalibrationWireframeOverlay: 渲染进照片覆盖层 <svg viewBox={`0 0 ${natW} ${natH}`}>
//   内部 (返回 <g>), 画 dry-run 返回的房间线框: merge 组每成员地面四边形 + 天花四边形 +
//   4 条竖棱。紫红虚线 + 非缩放描边, 与标定输入线层 (emerald 实线 y / brand 实线 x) 区分。
// - CalibrationPreviewPanel: 误差数值 + 评级徽章 + quality.reasons 列表 + 对照说明。
//   「确认保存」按钮不在此组件 —— 宿主按 preview.quality.ok 自行控制禁用 (确认门语义)。

const LEVEL_META: Record<
  'good' | 'suspect' | 'bad',
  { tone: BadgeTone; label: string }
> = {
  good: { tone: 'green', label: '好' },
  suspect: { tone: 'amber', label: '可疑' },
  bad: { tone: 'red', label: '坏' },
};

function toPoints(quad: [number, number][]): string {
  return quad.map(([u, v]) => `${u},${v}`).join(' ');
}

export function CalibrationWireframeOverlay({
  wireframe,
}: {
  wireframe: CalibrationWireframeRoom[];
}) {
  return (
    <g data-testid="calib-wireframe-overlay">
      {wireframe.map((wf) => {
        const edgeCount = Math.min(wf.floor.length, wf.ceiling.length);
        return (
          <g key={wf.room_id}>
            {/* 地面四边形 (z=0) */}
            <polygon
              points={toPoints(wf.floor)}
              fill="none"
              className="text-pink-500"
              stroke="currentColor"
              strokeWidth={2}
              strokeDasharray="7 4"
              vectorEffect="non-scaling-stroke"
            />
            {/* 天花四边形 (z=2700) */}
            <polygon
              points={toPoints(wf.ceiling)}
              fill="none"
              className="text-pink-400"
              stroke="currentColor"
              strokeWidth={1.5}
              strokeDasharray="7 4"
              vectorEffect="non-scaling-stroke"
            />
            {/* 竖棱: 地面角 -> 同序天花角 */}
            {Array.from({ length: edgeCount }, (_, i) => (
              <line
                key={`e${i}`}
                x1={wf.floor[i][0]}
                y1={wf.floor[i][1]}
                x2={wf.ceiling[i][0]}
                y2={wf.ceiling[i][1]}
                className="text-pink-400"
                stroke="currentColor"
                strokeWidth={1.5}
                strokeDasharray="2 4"
                vectorEffect="non-scaling-stroke"
              />
            ))}
          </g>
        );
      })}
    </g>
  );
}

export function CalibrationPreviewPanel({
  preview,
}: {
  preview: CalibrationPreviewResult;
}) {
  const q = preview.quality;
  const meta = LEVEL_META[q.level] ?? LEVEL_META.bad;
  const m = q.metrics;
  return (
    <div
      data-testid="calib-preview-panel"
      className="space-y-2 rounded-xl border border-gray-200 p-3 dark:border-white/10"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={meta.tone} dataTestId="calib-quality-badge">
          标定质量:{meta.label}
        </Badge>
        <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
          重投影误差 {preview.reprojection_error.toFixed(1)}px
        </span>
        {m && (
          <span className="text-xs text-gray-400">
            相机高度 {(m.camera_z_mm / 1000).toFixed(2)}m · 水平视角{' '}
            {Math.round(m.hfov_deg)}°
          </span>
        )}
      </div>
      {q.reasons.length > 0 && (
        <ul className="space-y-1">
          {q.reasons.map((r, i) => (
            <li
              key={`r${i}`}
              className={`text-xs ${
                q.ok
                  ? 'text-amber-600 dark:text-amber-400'
                  : 'text-red-600 dark:text-red-400'
              }`}
            >
              · {r}
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-gray-400">
        照片上的紫红虚线是按本次标定推算的房间轮廓(下方四边形=地面、上方=天花)。
        它与照片里实际墙线越贴合,标定越准;明显歪斜请撤销修正输入后重新预览。
      </p>
    </div>
  );
}
