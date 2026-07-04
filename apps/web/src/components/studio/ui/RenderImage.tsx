'use client';

import React, { useEffect, useState } from 'react';

// 一次性缓存击穿 (2026-07-04): 图片 Content-Type 修复前, /api/uploads 与 /api/artifacts 的
// webp 缩略图被以 application/octet-stream 提供且带 `Cache-Control: immutable`, 浏览器把这个
// 坏响应缓存一年 (硬刷都未必绕过 immutable), 缩略图恒空白。给图片 URL 追加一个静态版本参数,
// 让浏览器视作新 URL 重新拉取 -> 拿到修正后的 image/webp -> 缓存正确响应。需要再击穿时 +1。
const IMG_CACHE_BUST = 'iv=1';
function bustImageCache(u: string): string {
  if (!u || u.startsWith('data:')) return u;
  return u.includes('?') ? `${u}&${IMG_CACHE_BUST}` : `${u}?${IMG_CACHE_BUST}`;
}

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
          src={bustImageCache(src)}
          alt={alt}
          loading="lazy"
          decoding="async"
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
