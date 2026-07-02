'use client';

import React, { useEffect } from 'react';
import { HiX } from 'react-icons/hi';

// 统一模态壳:遮罩透明度 / z-index / Esc / 点背板关闭 / aria 单一来源。
// 供快捷键速查、图片灯箱等复用(ConfirmDialog 因是 Promise 门面暂保留自身壳)。
export default function Modal({
  open,
  onClose,
  title,
  maxWidthClass = 'max-w-md',
  padded = true,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  maxWidthClass?: string;
  padded?: boolean;
  children: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-6"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`w-full ${maxWidthClass} rounded-2xl bg-white shadow-2xl dark:bg-navy-800 ${
          padded ? 'p-5' : ''
        }`}
      >
        {title !== undefined && (
          <div
            className={`flex items-center justify-between ${padded ? 'mb-3' : 'p-4'}`}
          >
            <h3 className="text-base font-bold text-navy-700 dark:text-white">
              {title}
            </h3>
            <button
              type="button"
              aria-label="关闭"
              onClick={onClose}
              className="rounded-lg p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-navy-900"
            >
              <HiX className="h-4 w-4" />
            </button>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
