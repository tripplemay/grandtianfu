'use client';

import React from 'react';
import type { PhotoQuality } from 'lib/studioApi';
import { Badge, type BadgeTone } from '../ui/status';

// 工作流改造 (B5): 照片质量告警中文文案 + 可用性徽标。质量在上传时由后端确定性评分。
const WARNING_LABELS: Record<string, string> = {
  low_res: '分辨率偏低',
  extreme_aspect: '比例异常',
  too_dark: '偏暗',
  too_bright: '过曝',
  blurry: '不够清晰',
};

export function qualityWarningText(warnings: string[]): string {
  return warnings.map((w) => WARNING_LABELS[w] ?? w).join('、');
}

export default function PhotoQualityBadge({
  quality,
}: {
  quality?: PhotoQuality | null;
}) {
  if (!quality) return null;
  const warned = quality.warnings.length > 0;
  const tone: BadgeTone = !warned
    ? 'green'
    : quality.score <= 50
    ? 'red'
    : 'amber';
  return (
    <span
      title={
        warned
          ? `可用性 ${quality.score}/100 · ${qualityWarningText(
              quality.warnings,
            )}`
          : `可用性 ${quality.score}/100`
      }
    >
      <Badge tone={tone} size="xs">
        {warned
          ? `可用性 ${quality.score} · ${qualityWarningText(quality.warnings)}`
          : '质量良好'}
      </Badge>
    </span>
  );
}
