'use client';

import React, { useEffect, useState } from 'react';

// 渲染图封装 (§2.6 / P1):<img> 之上加 加载骨架 + onError 兜底占位。
// 用于 projects 缩略图 / gallery 三图 / 任何 /api/.../render 派生图;
// 后端挂掉或单图失败时显示占位而非碎图。
export default function RenderImage({
  src,
  alt,
  className,
  imgClassName,
  fallbackLabel = '图片加载失败',
}: {
  src: string;
  alt: string;
  className?: string;
  imgClassName?: string;
  fallbackLabel?: React.ReactNode;
}) {
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>(
    'loading',
  );

  // src 变化时重置状态 (例如切换项目)。
  useEffect(() => {
    setStatus('loading');
  }, [src]);

  return (
    <div
      className={`relative h-full w-full overflow-hidden ${className ?? ''}`}
    >
      {status === 'loading' && (
        <div className="absolute inset-0 animate-pulse bg-gray-200 dark:bg-navy-700" />
      )}
      {status === 'error' ? (
        <div className="flex h-full w-full flex-col items-center justify-center gap-1 bg-gray-100 text-gray-400 dark:bg-navy-900 dark:text-gray-500">
          <span className="text-2xl">🖼️</span>
          <span className="px-2 text-center text-xs">{fallbackLabel}</span>
        </div>
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={alt}
          onLoad={() => setStatus('loaded')}
          onError={() => setStatus('error')}
          className={`${imgClassName ?? ''} ${
            status === 'loaded' ? 'opacity-100' : 'opacity-0'
          } transition-opacity duration-200`}
        />
      )}
    </div>
  );
}
