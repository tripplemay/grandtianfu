'use client';

import React from 'react';

export type LoadState = 'idle' | 'loading' | 'ready' | 'error';

// 校验/保存状态文本行 红/绿/灰三态 (审查清单 Q2-#8)。
// errors=红(⛔) · warns=琥珀(⚠); 无 error/warn 时优先 okText(绿), 否则 hintText(灰)。
// footer 始终展示 (几何面板的派生计数行)。
export function StatusLines({
  errors = [],
  warns = [],
  okText,
  hintText,
  footer,
  resolveLocate,
  onLocate,
}: {
  errors?: string[];
  warns?: string[];
  okText?: React.ReactNode;
  hintText?: React.ReactNode;
  footer?: React.ReactNode;
  // 定位校验反馈 (阶段 5b / P2-12): resolveLocate(msg)=true 的条目渲染为可点按钮,
  // 点击 -> onLocate(msg) 选中并高亮/居中对应元素。
  resolveLocate?: (msg: string) => boolean;
  onLocate?: (msg: string) => void;
}) {
  const clean = errors.length === 0 && warns.length === 0;
  // 单行渲染: 可定位 -> 按钮 (左对齐, 下划线提示可点); 否则普通段落。
  const renderLine = (
    kind: 'e' | 'w',
    msg: string,
    i: number,
    icon: string,
    cls: string,
  ) => {
    const locatable = !!resolveLocate && !!onLocate && resolveLocate(msg);
    if (locatable) {
      return (
        <button
          key={`${kind}${i}`}
          type="button"
          data-testid={`locate-${kind}-${i}`}
          onClick={() => onLocate?.(msg)}
          title="点击定位到画布元素"
          className={`block w-full text-left text-xs underline decoration-dotted underline-offset-2 hover:opacity-80 ${cls}`}
        >
          {icon} {msg}
        </button>
      );
    }
    return (
      <p key={`${kind}${i}`} className={`text-xs ${cls}`}>
        {icon} {msg}
      </p>
    );
  };
  return (
    <div className="space-y-1">
      {errors.map((e, i) => renderLine('e', e, i, '⛔', 'text-red-500'))}
      {warns.map((w, i) => renderLine('w', w, i, '⚠', 'text-amber-500'))}
      {clean && okText && <p className="text-xs text-green-500">{okText}</p>}
      {clean && !okText && hintText && (
        <p className="text-xs text-gray-400">{hintText}</p>
      )}
      {footer}
    </div>
  );
}

// 后端加载失败红 banner (审查清单 Q2-#9)。
export function BackendErrorBanner({
  message,
  title = '无法加载几何 / 派生数据(后端可能未启动)。',
}: {
  message: string | null;
  title?: string;
}) {
  return (
    <div className="dark:bg-red-950 mb-3 rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:text-red-300">
      <p className="font-semibold">{title}</p>
      <p className="mt-1 break-all opacity-80">{message}</p>
    </div>
  );
}

// 载入状态徽章 (审查清单 Q2-#10)。
const LOAD_STATE_MAP: Record<LoadState, { label: string; cls: string }> = {
  idle: { label: '待加载', cls: 'bg-gray-200 text-gray-700' },
  loading: { label: '加载中', cls: 'bg-amber-200 text-amber-800' },
  ready: { label: '已就绪', cls: 'bg-green-200 text-green-800' },
  error: { label: '错误', cls: 'bg-red-200 text-red-800' },
};

export function LoadStateBadge({ state }: { state: LoadState }) {
  const { label, cls } = LOAD_STATE_MAP[state];
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}

// 业务生命周期状态 → 中文徽章。统一户型版本与软装方案的状态呈现, 不把后端英文枚举
// (draft/confirmed/superseded/archived)暴露给设计师。未知值回落原文兜底。
type StatusKind = 'baseline' | 'scheme';

const BUSINESS_STATUS: Record<
  StatusKind,
  Record<string, { label: string; cls: string }>
> = {
  baseline: {
    draft: {
      label: '草稿',
      cls: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-200',
    },
    confirmed: {
      label: '已确认',
      cls: 'bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-200',
    },
    superseded: {
      label: '已被替代',
      cls: 'bg-gray-200 text-gray-600 dark:bg-navy-700 dark:text-gray-300',
    },
  },
  scheme: {
    draft: {
      label: '草稿',
      cls: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-200',
    },
    confirmed: {
      label: '已确认',
      cls: 'bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-200',
    },
    archived: {
      label: '已归档',
      cls: 'bg-gray-200 text-gray-600 dark:bg-navy-700 dark:text-gray-300',
    },
  },
};

export function statusLabel(kind: StatusKind, status?: string | null): string {
  return (status && BUSINESS_STATUS[kind][status]?.label) || status || '未知';
}

export function StatusBadge({
  kind,
  status,
}: {
  kind: StatusKind;
  status?: string | null;
}) {
  const entry = (status && BUSINESS_STATUS[kind][status]) || {
    label: status || '未知',
    cls: 'bg-gray-100 text-gray-600 dark:bg-navy-700 dark:text-gray-300',
  };
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${entry.cls}`}
    >
      {entry.label}
    </span>
  );
}
