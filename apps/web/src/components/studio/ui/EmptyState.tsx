'use client';

import React from 'react';

// 空态引导 (§2.6):icon / title / desc / action。
// 用于「无项目」「家具未选中」等空白处,替代裸灰字提示。
export default function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`flex flex-col items-center justify-center rounded-2xl border border-dashed border-gray-200 bg-gray-50/60 px-6 py-10 text-center dark:border-white/10 dark:bg-navy-900/40 ${
        className ?? ''
      }`}
    >
      {icon && (
        <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-white text-2xl text-gray-400 shadow-sm dark:bg-navy-800 dark:text-gray-300">
          {icon}
        </div>
      )}
      <p className="text-base font-bold text-navy-700 dark:text-white">
        {title}
      </p>
      {description && (
        <p className="mt-1 max-w-sm text-sm text-gray-500 dark:text-gray-400">
          {description}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
