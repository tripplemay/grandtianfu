import type React from 'react';

// 背景捕获判定 (审查清单 Q2-#11): 点到 SVG 自身或 data-bg=1 的捕获 rect = 空白。
export function isBackgroundTarget(e: React.PointerEvent): boolean {
  const target = e.target as Element;
  return target === e.currentTarget || target.getAttribute('data-bg') === '1';
}
