'use client';

import React from 'react';
import type { AlignMode, DistributeMode } from 'lib/floorplan/geometry';

interface Props {
  count: number; // 选中数量。<2 不渲染; 分布需 >=3。
  onAlign: (mode: AlignMode) => void;
  onDistribute: (mode: DistributeMode) => void;
}

const ALIGN_BTNS: Array<{ mode: AlignMode; label: string; testid: string }> = [
  { mode: 'left', label: '左', testid: 'align-left' },
  { mode: 'hcenter', label: '水平中', testid: 'align-hcenter' },
  { mode: 'right', label: '右', testid: 'align-right' },
  { mode: 'top', label: '顶', testid: 'align-top' },
  { mode: 'vcenter', label: '垂直中', testid: 'align-vcenter' },
  { mode: 'bottom', label: '底', testid: 'align-bottom' },
];

// 多选对齐 / 分布工具条 (阶段 5a / P2-7)。选中 >=2 才出现; 分布需 >=3 才可用。
export default function AlignBar({ count, onAlign, onDistribute }: Props) {
  if (count < 2) return null;
  const distDisabled = count < 3;
  const btnCls =
    'rounded-lg border border-gray-200 px-2 py-1 text-xs hover:bg-gray-50 dark:border-white/10 dark:hover:bg-white/5';
  return (
    <div data-testid="align-bar" className="mt-2">
      <p className="mb-1 text-xs font-semibold text-gray-500 dark:text-gray-300">
        已选 {count} 项 · 对齐 / 分布
      </p>
      <div className="grid grid-cols-3 gap-1">
        {ALIGN_BTNS.map((b) => (
          <button
            key={b.mode}
            type="button"
            data-testid={b.testid}
            onClick={() => onAlign(b.mode)}
            className={btnCls}
          >
            {b.label}
          </button>
        ))}
      </div>
      <div className="mt-1 grid grid-cols-2 gap-1">
        <button
          type="button"
          data-testid="distribute-h"
          disabled={distDisabled}
          onClick={() => onDistribute('h')}
          className={`${btnCls} disabled:opacity-40`}
        >
          水平等距
        </button>
        <button
          type="button"
          data-testid="distribute-v"
          disabled={distDisabled}
          onClick={() => onDistribute('v')}
          className={`${btnCls} disabled:opacity-40`}
        >
          垂直等距
        </button>
      </div>
    </div>
  );
}
