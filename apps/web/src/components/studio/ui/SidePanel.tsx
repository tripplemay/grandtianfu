'use client';

import React, { useState } from 'react';
import { MdChevronLeft, MdChevronRight } from 'react-icons/md';
import Card from 'components/card';

// 侧栏外壳 + 分区卡 (审查清单 Q2-#2 / Q1-#1)。
// SidePanel 基于 Horizon Card (即 Q1-#1 接模板); 用 extra 覆盖为"描边扁平"观感
// (!shadow-none 关掉 Card 默认阴影), 保持与原手写侧栏一致 —— Card 阴影 vs 描边的
// 微差是审查清单认可的设计取舍。

export function SidePanel({
  title,
  children,
}: {
  title: React.ReactNode;
  children: React.ReactNode;
}) {
  // 折叠态 (P1 画布快赢): 折成细条把宽度让给画布; 仅桌面 (lg) 提供, 移动端保持展开。
  const [collapsed, setCollapsed] = useState(false);
  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        title="展开属性面板"
        data-testid="panel-expand"
        className="hidden w-9 shrink-0 items-start justify-center rounded-2xl border border-gray-200 bg-white py-3 text-gray-500 hover:bg-gray-50 dark:border-white/10 dark:bg-navy-800 dark:text-gray-300 lg:flex"
      >
        <MdChevronLeft className="h-5 w-5" />
      </button>
    );
  }
  return (
    <Card extra="w-full max-w-[340px] shrink-0 gap-3 border border-gray-200 p-4 text-sm !shadow-none dark:border-white/10 lg:max-h-full lg:overflow-y-auto">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-bold text-navy-700 dark:text-white">
          {title}
        </h2>
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          title="折叠面板"
          data-testid="panel-collapse"
          className="hidden rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-navy-700 lg:inline-flex"
        >
          <MdChevronRight className="h-4 w-4" />
        </button>
      </div>
      {children}
    </Card>
  );
}

// 面板内分区卡: rounded-xl border-gray-100 p-3 (此前重复 4 次)。
export function PanelSection({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl border border-gray-100 p-3 dark:border-white/5${
        className ? ` ${className}` : ''
      }`}
    >
      {children}
    </div>
  );
}
