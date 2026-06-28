'use client';

import React from 'react';

// 载入态 (§2.6):骨架(skeleton)与转圈(spinner)两形态。
// 默认 skeleton:首屏请求期占位,避免整页空白闪烁。
export default function LoadingState({
  variant = 'skeleton',
  label,
  rows = 3,
  className,
}: {
  variant?: 'skeleton' | 'spinner';
  label?: React.ReactNode;
  rows?: number;
  className?: string;
}) {
  if (variant === 'spinner') {
    return (
      <div
        className={`flex flex-col items-center justify-center gap-3 py-12 text-sm text-gray-500 dark:text-gray-400 ${
          className ?? ''
        }`}
      >
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-gray-300 border-t-brand-500" />
        {label && <span>{label}</span>}
      </div>
    );
  }

  return (
    <div className={`w-full animate-pulse space-y-4 ${className ?? ''}`}>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: rows * 2 }).map((_, i) => (
          <div
            key={i}
            className="flex flex-col gap-3 rounded-2xl border border-gray-200 p-4 dark:border-white/10"
          >
            <div className="h-44 w-full rounded-xl bg-gray-200 dark:bg-navy-700" />
            <div className="h-4 w-2/3 rounded bg-gray-200 dark:bg-navy-700" />
            <div className="h-3 w-1/2 rounded bg-gray-100 dark:bg-navy-700/60" />
          </div>
        ))}
      </div>
      {label && (
        <p className="text-center text-sm text-gray-400">{label}</p>
      )}
    </div>
  );
}
