'use client';

import React from 'react';

interface Props {
  zoomPct: number;
  onFit: () => void;
  onReset100: () => void;
  onZoomIn?: () => void;
  onZoomOut?: () => void;
}

// 画布角缩放控件 (阶段 1): 显示缩放% + Fit/100% 按钮。绝对定位于画布容器右下角。
export default function ZoomControls({
  zoomPct,
  onFit,
  onReset100,
  onZoomIn,
  onZoomOut,
}: Props) {
  const btn =
    'rounded-md border border-gray-300 bg-white px-2 py-1 text-xs font-medium text-gray-700 shadow-sm hover:bg-gray-50 dark:border-white/10 dark:bg-navy-700 dark:text-white dark:hover:bg-navy-600';
  return (
    <div className="pointer-events-none absolute bottom-3 right-3 z-10 flex items-center gap-1.5">
      {onZoomOut && (
        <button
          type="button"
          data-testid="zoom-out"
          onClick={onZoomOut}
          className={`pointer-events-auto ${btn}`}
          title="缩小 (Ctrl -)"
        >
          −
        </button>
      )}
      {onZoomIn && (
        <button
          type="button"
          data-testid="zoom-in"
          onClick={onZoomIn}
          className={`pointer-events-auto ${btn}`}
          title="放大 (Ctrl +)"
        >
          ＋
        </button>
      )}
      <span
        data-testid="zoom-pct"
        className="pointer-events-auto rounded-md border border-gray-300 bg-white px-2 py-1 text-xs font-semibold tabular-nums text-gray-700 shadow-sm dark:border-white/10 dark:bg-navy-700 dark:text-white"
      >
        {zoomPct}%
      </span>
      <button
        type="button"
        data-testid="zoom-fit"
        onClick={onFit}
        className={`pointer-events-auto ${btn}`}
      >
        Fit
      </button>
      <button
        type="button"
        data-testid="zoom-100"
        onClick={onReset100}
        className={`pointer-events-auto ${btn}`}
      >
        100%
      </button>
    </div>
  );
}
