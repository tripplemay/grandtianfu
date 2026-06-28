'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';

// 壳级 toast (§2.6):提升原编辑器内联 useToast 为全局单例。
// ToastProvider 放 studio/layout.tsx,任意子组件 useToastContext().showToast(msg)。
// 统一所有 studio 通知反馈,避免编辑器/项目台各自一套。

type ToastTone = 'info' | 'success' | 'error';

interface ToastState {
  msg: string;
  tone: ToastTone;
}

interface ToastContextValue {
  showToast: (msg: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((msg: string, tone: ToastTone = 'info') => {
    setToast({ msg, tone });
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(null), 2400);
  }, []);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const toneCls =
    toast?.tone === 'success'
      ? 'bg-green-600'
      : toast?.tone === 'error'
      ? 'bg-red-600'
      : 'bg-navy-900';

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {toast && (
        <div
          role="status"
          aria-live="polite"
          className={`fixed bottom-5 left-1/2 z-[60] -translate-x-1/2 rounded-lg px-4 py-2 text-sm text-white shadow-lg ${toneCls}`}
        >
          {toast.msg}
        </div>
      )}
    </ToastContext.Provider>
  );
}

// 全局消费;Provider 缺失时退化为 no-op(SSR/孤立渲染安全)。
export function useToastContext(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    return { showToast: () => undefined };
  }
  return ctx;
}
