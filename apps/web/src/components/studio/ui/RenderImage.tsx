'use client';

import React, { useEffect, useRef, useState } from 'react';

// 图片缓存击穿 = 构建版本 (NEXT_PUBLIC_APP_VERSION, CI 注入 git sha; 本地回退)。
// 背景: /api/uploads·/api/artifacts 的图片带 `Cache-Control: immutable`(一年不再校验),
// 若某次曾拿到坏响应(webp 被当 octet-stream 等), 会被浏览器永久缓存、硬刷都未必绕过, 缩略图恒空白。
// 用【随每次部署变化】的版本号做 URL 参数 -> 部署后图片 URL 即变 -> 浏览器重新拉取 -> 历史坏缓存
// 自动失效。静态串会随 immutable 一起卡死(此前 iv=1 复发即因此), 故必须绑定构建版本。
const IMG_CACHE_BUST = `iv=${process.env.NEXT_PUBLIC_APP_VERSION || 'dev'}`;
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
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>(
    'loading',
  );

  // 根因修复 (缓存图 onLoad 竞态): SPA 重新挂载时, 若图片已在浏览器缓存, <img> 会在 onLoad
  // handler 挂上前就已 complete, load 事件不再触发 -> 永远停在 loading(opacity-0)= 空白。
  // 症状: 生成效果图后切回基线页, 已缓存的空房照全变空白 (首次加载不缓存故正常, 故极具迷惑性)。
  // 修复: 挂载 / src 变化时主动检查 img.complete, 已完成直接置 loaded/error, 不干等事件。
  // React 在跑 effect 前已挂好 ref, 故此处 imgRef.current 可靠。
  useEffect(() => {
    const img = imgRef.current;
    if (img && img.complete) {
      setStatus(img.naturalWidth > 0 ? 'loaded' : 'error');
    } else {
      setStatus('loading');
    }
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
          ref={imgRef}
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
