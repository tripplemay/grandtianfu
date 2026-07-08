'use client';

import React from 'react';
import Link from 'next/link';

// 各类按钮收编 (审查清单 Q2-#6 / Q2-#7)。

// ---- 统一按钮/链接按钮 (设计系统单一来源) ---- //
// variant 承载语义配色(含成对 dark:),size 承载 padding/字号。页面不再手写按钮 class。
export type ButtonVariant =
  | 'primary' // brand 实心主操作
  | 'secondary' // 灰底次级
  | 'success' // 浅绿确认(对齐 StatusBadge confirmed)
  | 'success-solid' // 实心绿(里程碑级「确认」强调 CTA)
  | 'soft-brand' // 浅 brand 强调
  | 'soft-amber' // 浅琥珀(设为首选等)
  | 'danger' // 红实心破坏
  | 'danger-soft'; // 浅红破坏(菜单内)

export type ButtonSize = 'sm' | 'md';

const VARIANT_CLS: Record<ButtonVariant, string> = {
  primary: 'bg-brand-500 text-white hover:bg-brand-600',
  secondary:
    'bg-gray-100 text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white dark:hover:bg-navy-700',
  success:
    'bg-green-50 text-green-700 hover:bg-green-100 dark:bg-green-900 dark:text-green-200',
  'success-solid': 'bg-green-600 text-white hover:bg-green-700',
  'soft-brand':
    'bg-brand-50 text-brand-600 hover:bg-brand-100 dark:bg-navy-900 dark:text-brand-400 dark:hover:bg-navy-700',
  'soft-amber':
    'bg-amber-50 text-amber-700 hover:bg-amber-100 dark:bg-amber-900 dark:text-amber-200',
  danger: 'bg-red-500 text-white hover:bg-red-600',
  'danger-soft':
    'bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-900 dark:text-red-300',
};

const SIZE_CLS: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-3 py-2 text-sm',
};

const BUTTON_BASE =
  'inline-flex items-center justify-center gap-1 rounded-lg font-medium transition disabled:opacity-50 disabled:pointer-events-none';

export function buttonClasses(
  variant: ButtonVariant = 'primary',
  size: ButtonSize = 'md',
  className = '',
): string {
  return `${BUTTON_BASE} ${VARIANT_CLS[variant]} ${SIZE_CLS[size]} ${className}`.trim();
}

export function Button({
  variant = 'primary',
  size = 'md',
  onClick,
  disabled,
  title,
  ariaPressed,
  ariaLabel,
  type = 'button',
  className,
  children,
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  onClick?: () => void;
  disabled?: boolean;
  title?: string;
  ariaPressed?: boolean;
  ariaLabel?: string;
  type?: 'button' | 'submit';
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-pressed={ariaPressed}
      aria-label={ariaLabel}
      className={buttonClasses(variant, size, className)}
    >
      {children}
    </button>
  );
}

// 与 Button 同样式的导航链接(主操作大多是跳转,统一 padding/hover/dark:)。
export function LinkButton({
  href,
  variant = 'primary',
  size = 'md',
  title,
  download,
  className,
  children,
}: {
  href: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  title?: string;
  download?: string;
  className?: string;
  children: React.ReactNode;
}) {
  // 下载(download 属性)必须用原生 <a>;普通导航用 next/link。
  if (download !== undefined) {
    return (
      <a
        href={href}
        download={download}
        title={title}
        className={buttonClasses(variant, size, className)}
      >
        {children}
      </a>
    );
  }
  return (
    <Link
      href={href}
      title={title}
      className={buttonClasses(variant, size, className)}
    >
      {children}
    </Link>
  );
}

// 图标方钮(编辑器工具条:撤销/重做/帮助等),尺寸统一。
export function IconButton({
  onClick,
  disabled,
  title,
  ariaLabel,
  className,
  children,
}: {
  onClick?: () => void;
  disabled?: boolean;
  title?: string;
  ariaLabel?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={ariaLabel}
      className={`rounded-lg bg-gray-100 p-1.5 text-gray-600 hover:bg-gray-200 disabled:opacity-50 dark:bg-navy-900 dark:text-white dark:hover:bg-navy-700 ${
        className ?? ''
      }`.trim()}
    >
      {children}
    </button>
  );
}

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
