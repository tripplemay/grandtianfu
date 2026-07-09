'use client';

import React from 'react';
import Card from 'components/card';
import { relativeTime } from 'lib/time';

// studio 卡片默认修饰(border + 内距 + 无阴影 + 暗色边),统一 17 处逐字复制。
export const CARD_EXTRA =
  'w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10';

// 标准 studio 卡片:默认套 CARD_EXTRA,extra 只传差异(如 'mt-4' / 'flex flex-col')。
// 可选交互态(interactive/selected/onClick):可点选卡片由设计系统统一提供,选中用
// brand 描边+ring 强调(不改底色,保持 Card 的 navy-800/白字, 深浅主题都协调),
// 避免各页手写 div + 硬编码浅底(bg-*-50 在 dark 下突兀、白字对比差)。
export function StudioCard({
  extra = '',
  interactive = false,
  selected = false,
  ariaCurrent = false,
  onClick,
  children,
}: {
  extra?: string;
  interactive?: boolean;
  selected?: boolean;
  ariaCurrent?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
}) {
  const interactiveCls = interactive
    ? 'cursor-pointer transition-colors hover:border-brand-300 dark:hover:border-brand-400/50'
    : '';
  const selectedCls = selected
    ? '!border-brand-500 ring-2 ring-brand-500 dark:!border-brand-400 dark:ring-brand-400'
    : '';
  const interactiveProps = interactive
    ? {
        role: 'button',
        tabIndex: 0,
        onClick,
        onKeyDown: (e: React.KeyboardEvent) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onClick?.();
          }
        },
        'aria-current': ariaCurrent ? ('true' as const) : undefined,
      }
    : {};
  return (
    <Card
      extra={`${CARD_EXTRA} ${interactiveCls} ${selectedCls} ${extra}`.trim()}
      {...interactiveProps}
    >
      {children as JSX.Element}
    </Card>
  );
}

// 发丝分隔线,统一 h-px + 灰/暗色。
export function Hairline({ className = '' }: { className?: string }) {
  return (
    <div className={`h-px bg-gray-200 dark:bg-white/10 ${className}`.trim()} />
  );
}

// 相对时间(带原始时间 tooltip),统一「更新/创建 X 前」展示。
export function TimeAgo({
  at,
  prefix,
  className = 'text-xs text-gray-500',
}: {
  at?: string | null;
  prefix?: string;
  className?: string;
}) {
  return (
    <span title={at ?? undefined} className={className}>
      {prefix ? `${prefix} ` : ''}
      {relativeTime(at)}
    </span>
  );
}

// 只读态侧栏提示块,统一 GeometryMode/FurnitureMode 重复。
export function ReadOnlyNotice({ text }: { text: string }) {
  return (
    <div className="w-full rounded-2xl border border-gray-200 bg-gray-50 p-4 text-sm text-gray-500 dark:border-white/10 dark:bg-navy-900 lg:w-80">
      {text}
    </div>
  );
}
