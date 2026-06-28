'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useState,
} from 'react';
import Card from 'components/card';

// 确认弹窗 (§2.6):替换原生 window.confirm。
// ConfirmProvider 放 studio/layout.tsx,任意子组件:
//   const confirm = useConfirm();
//   if (await confirm({ title, message, danger })) { … }
// 返回 Promise<boolean>,确定=true / 取消=false。

interface ConfirmOptions {
  title: React.ReactNode;
  message?: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
}

type ConfirmFn = (opts: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn | null>(null);

interface PendingState extends ConfirmOptions {
  resolve: (value: boolean) => void;
}

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [pending, setPending] = useState<PendingState | null>(null);

  const confirm = useCallback<ConfirmFn>((opts) => {
    return new Promise<boolean>((resolve) => {
      setPending({ ...opts, resolve });
    });
  }, []);

  const settle = useCallback(
    (value: boolean) => {
      if (pending) pending.resolve(value);
      setPending(null);
    },
    [pending],
  );

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending && (
        <ConfirmDialog
          title={pending.title}
          message={pending.message}
          confirmText={pending.confirmText}
          cancelText={pending.cancelText}
          danger={pending.danger}
          onConfirm={() => settle(true)}
          onCancel={() => settle(false)}
        />
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    // Provider 缺失时退化为原生 confirm(SSR/孤立渲染安全)。
    return async (opts) =>
      typeof window !== 'undefined'
        ? window.confirm(
            `${opts.title}${opts.message ? `\n${opts.message}` : ''}`,
          )
        : false;
  }
  return ctx;
}

// 受控展示组件 (Provider 内部使用,亦可独立使用)。
export function ConfirmDialog({
  title,
  message,
  confirmText = '确定',
  cancelText = '取消',
  danger,
  onConfirm,
  onCancel,
}: ConfirmOptions & {
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={onCancel}
    >
      <Card
        extra="w-full max-w-[420px] gap-4 p-6"
        // 阻止冒泡:点卡片本身不触发遮罩的取消。
      >
        <div onClick={(e) => e.stopPropagation()}>
          <h2 className="text-lg font-bold text-navy-700 dark:text-white">
            {title}
          </h2>
          {message && (
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
              {message}
            </p>
          )}
          <div className="mt-6 flex justify-end gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white dark:hover:bg-navy-700"
            >
              {cancelText}
            </button>
            <button
              type="button"
              onClick={onConfirm}
              className={`rounded-lg px-4 py-2 text-sm font-medium text-white ${
                danger
                  ? 'bg-red-500 hover:bg-red-600'
                  : 'bg-brand-500 hover:bg-brand-600'
              }`}
            >
              {confirmText}
            </button>
          </div>
        </div>
      </Card>
    </div>
  );
}

export default ConfirmDialog;
