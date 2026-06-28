'use client';

import React from 'react';

// 各类按钮收编 (审查清单 Q2-#6 / Q2-#7)。

// 单个激活态药丸按钮 (工具栏 ＋门/＋自由墙/打通/分隔)。
export function ToggleButton({
  active,
  onClick,
  children,
}: {
  active?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg px-3 py-1 text-xs font-medium ${
        active
          ? 'bg-brand-500 text-white'
          : 'bg-gray-100 text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white dark:hover:bg-navy-700'
      }`}
    >
      {children}
    </button>
  );
}

// 互斥分段选择器 (Tab=geometry/furniture, orient=N/S/W/E)。
// 两种视觉 variant 各自保留原像素样式。
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  renderLabel,
  variant,
}: {
  options: readonly T[];
  value: T | null | undefined;
  onChange: (value: T) => void;
  renderLabel?: (value: T) => React.ReactNode;
  variant: 'tab' | 'orient';
}) {
  const container =
    variant === 'tab'
      ? 'inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1 dark:border-white/10 dark:bg-navy-900'
      : 'mt-1 flex gap-1';
  // a11y (Phase 4):tab 变体语义为标签页 (tablist/tab/aria-selected);
  // orient 变体语义为单选 (radiogroup/radio/aria-checked)。
  const isTab = variant === 'tab';
  return (
    <div className={container} role={isTab ? 'tablist' : 'radiogroup'}>
      {options.map((o) => {
        const active = value === o;
        const cls =
          variant === 'tab'
            ? `rounded-md px-4 py-1.5 text-sm font-medium transition ${
                active
                  ? 'bg-brand-500 text-white shadow'
                  : 'text-navy-700 hover:bg-gray-200 dark:text-white dark:hover:bg-navy-700'
              }`
            : `flex-1 rounded-md px-0 py-1 text-xs font-medium ${
                active
                  ? 'bg-brand-500 text-white'
                  : 'bg-gray-100 text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white'
              }`;
        const label = renderLabel ? renderLabel(o) : o;
        return (
          <button
            key={o}
            type="button"
            role={isTab ? 'tab' : 'radio'}
            aria-selected={isTab ? active : undefined}
            aria-checked={isTab ? undefined : active}
            aria-label={typeof label === 'string' ? label : String(o)}
            onClick={() => onChange(o)}
            className={cls}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

// 保存按钮 (brand 主按钮)。三态文案由调用方经 children 传入。
export function SaveButton({
  onClick,
  disabled,
  title,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
    >
      {children}
    </button>
  );
}

// 危险删除按钮 (红)。
export function DangerButton({
  onClick,
  children,
}: {
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mt-3 rounded-lg bg-red-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600"
    >
      {children}
    </button>
  );
}
