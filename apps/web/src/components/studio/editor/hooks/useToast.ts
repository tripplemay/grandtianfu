'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

// 轻量 toast: 显示 2.2s 后自动消失 (沿用原 FloorplanEditor 内联逻辑)。
export function useToast() {
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2200);
  }, []);

  useEffect(
    () => () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    },
    [],
  );

  return { toast, showToast };
}
