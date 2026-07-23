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


export function CalibrationWireframeOverlay({
  wireframe,
}: {
  wireframe: CalibrationWireframeRoom[];
}) {
  return (
    <g data-testid="calib-wireframe-overlay">
      {wireframe.map((wf) => {
        // F009(用户 L2-2): 后端**逐角**剔除相机后方的点(该角为 null)。这里只在两端都有效时
        // 连线 —— 背后点的裸投影会落在画面内形成假轮廓, 而 UI 又要求用户按线框贴合度判断
        // 标定质量, 等于判据掺假。**宁可画残, 不可画假**; 整房不可见时由 Panel 明文告知。
        const seg = (
          ring: (readonly [number, number] | null)[],
          i: number,
        ): [number, number, number, number] | null => {
          const a = ring[i];
          const b = ring[(i + 1) % ring.length];
          return a && b ? [a[0], a[1], b[0], b[1]] : null;
        };
        const ringLines = (
          ring: (readonly [number, number] | null)[],
          cls: string,
          w: number,
        ) =>
          ring.map((_, i) => {
            const s2 = seg(ring, i);
            return s2 === null ? null : (
              <line
                key={`${cls}${i}`}
                x1={s2[0]}
                y1={s2[1]}
                x2={s2[2]}
                y2={s2[3]}
                className={cls}
                stroke="currentColor"
                strokeWidth={w}
                strokeDasharray="7 4"
                vectorEffect="non-scaling-stroke"
              />
            );
          });
        const edgeCount = Math.min(wf.floor.length, wf.ceiling.length);
        return (
          <g key={wf.room_id}>
            {/* 地面环 (z=0) —— 逐边画, 跳过含背后点的边 */}
            {ringLines(wf.floor, 'text-pink-500', 2)}
            {/* 天花环 (z=2700) */}
            {ringLines(wf.ceiling, 'text-pink-400', 1.5)}
            {/* 竖棱: 地面角 -> 同序天花角 (两端都有效才画) */}
            {Array.from({ length: edgeCount }, (_, i) => {
              const a = wf.floor[i];
              const b = wf.ceiling[i];
              return a && b ? (
                <line
                  key={`e${i}`}
                  x1={a[0]}
                  y1={a[1]}
                  x2={b[0]}
                  y2={b[1]}
                  className="text-pink-400"
                  stroke="currentColor"
                  strokeWidth={1.5}
                  strokeDasharray="2 4"
                  vectorEffect="non-scaling-stroke"
                />
              ) : null;
            })}
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
  const skipped = (preview.wireframe ?? []).filter((w) => w.skipped_reason);
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
      {/* F009(用户 L2-2): 被剔除的成员必须明说 —— 静默少画会让用户以为线框本该如此。 */}
      {skipped.length > 0 && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          ⚠ 有 {skipped.length} 个相连房间未绘制线框:
          {skipped.map((w) => ` ${w.room_id}`).join('、')}
          ——{skipped[0].skipped_reason}。
          <span className="font-semibold">
            这不代表标定有问题
          </span>
          ,只是它们不在这张照片的取景范围内。
        </p>
      )}
      <p className="text-xs text-gray-400">
        照片上的紫红虚线是按本次标定推算的房间轮廓(下方四边形=地面、上方=天花)。
        它与照片里实际墙线越贴合,标定越准;明显歪斜请撤销修正输入后重新预览。
      </p>
    </div>
  );
}
