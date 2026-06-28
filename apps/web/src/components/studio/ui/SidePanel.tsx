'use client';

import React from 'react';
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
  return (
    <Card extra="w-full max-w-[340px] gap-3 border border-gray-200 p-4 text-sm !shadow-none dark:border-white/10">
      <h2 className="text-base font-bold text-navy-700 dark:text-white">
        {title}
      </h2>
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
