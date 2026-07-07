'use client';

import React from 'react';
import { HiX } from 'react-icons/hi';
import type { CatalogEntry } from 'lib/studioApi';
import FurnitureLibrary from './FurnitureLibrary';

// 家具库侧滑抽屉: 从**左缘**滑出, 非模态 (无遮罩) —— 画布仍是有效 drop 目标, 拖库项到
// 画布不受影响。左出对齐左上角开库按钮的心智, 且让开右侧不再遮住家具编辑面板 (右侧栏);
// 右缘留给 PreviewDrawer。关闭时 translate 出屏 + pointer-events-none, 不拦截画布。
// 始终挂载 -> 保留搜索态 + 平滑 200ms 滑入滑出。
export default function FurnitureLibraryDrawer({
  open,
  onClose,
  onQuickAdd,
  catalog,
}: {
  open: boolean;
  onClose: () => void;
  onQuickAdd: (type: string) => void;
  catalog?: CatalogEntry[];
}) {
  return (
    <div
      data-testid="furniture-library-drawer"
      aria-hidden={!open}
      className={`fixed inset-y-0 left-0 z-[55] flex w-full max-w-xs flex-col border-r border-gray-200 bg-white shadow-2xl transition-transform duration-200 dark:border-white/10 dark:bg-navy-800 ${
        open ? 'translate-x-0' : 'pointer-events-none -translate-x-full'
      }`}
    >
      <div className="flex items-center justify-between gap-2 border-b border-gray-100 p-3 dark:border-white/5">
        <h3 className="text-sm font-bold text-navy-700 dark:text-white">
          家具库
        </h3>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-navy-700"
          aria-label="关闭家具库"
        >
          <HiX className="h-5 w-5" />
        </button>
      </div>
      <div className="min-h-0 flex-1 p-3">
        <FurnitureLibrary onQuickAdd={onQuickAdd} catalog={catalog} fill />
      </div>
    </div>
  );
}
