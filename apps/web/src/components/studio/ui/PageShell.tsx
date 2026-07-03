'use client';

import React from 'react';

// 统一页面模板 (§2.4): 容器单一来源 + 标题区 + 工具区 + 内容/aside 两栏。
// 消除三页各自重复的 `mx-auto max-w-[1400px] px-4 py-6` 与「标题贴顶」。
// variant:
//   'default' — 常规内容页 (项目台 / 画廊),内容随高度自适应。
//   'full'    — 编辑器满高变体:内容区 `h-[calc(100vh-…)]`,画布尽量大。
//   'canvas'  — 编辑器全屏变体 (P4):fixed 满视口, 逃出 Studio 壳 (侧栏/导航/页脚/内边距),
//               画布真正 100dvh。children 自带顶栏 (退出按钮/模式), 本壳不再渲染标题区。
export type PageShellVariant = 'default' | 'full' | 'canvas';

interface PageShellProps {
  // canvas 变体不渲染标题区 (编辑器自带顶栏), 故可选。
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  aside?: React.ReactNode;
  // 页面级状态覆盖层 (载入骨架 / 失败 banner)。给出时替换 children 主体。
  state?: React.ReactNode;
  variant?: PageShellVariant;
  children?: React.ReactNode;
}

export default function PageShell({
  title,
  description,
  actions,
  aside,
  state,
  variant = 'default',
  children,
}: PageShellProps) {
  const isFull = variant === 'full';
  // full 变体:外壳 !pt-[100px] 已让位 Navbar,这里给内容区一个尽量大的满高区域。
  const bodyMinH = isFull ? 'min-h-[calc(100vh-220px)]' : '';

  // canvas 变体 (P4 全屏): 固定满视口, 盖住 Studio 壳; children 撑满并自管顶栏。
  // z-[55]: 盖住 Studio 侧栏 (z-50)/导航, 但让 toast(z-60)/确认框·模态(z-70) 仍在其上。
  if (variant === 'canvas') {
    return (
      <div
        data-testid="editor-fullscreen"
        className="fixed inset-0 z-[55] flex h-[100dvh] w-screen flex-col overflow-hidden bg-white dark:bg-navy-900"
      >
        {children}
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-[1400px] px-4 py-6">
      {/* 标题 / 工具区 */}
      <header className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-navy-700 dark:text-white">
            {title}
          </h1>
          {description && (
            <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
              {description}
            </p>
          )}
        </div>
        {actions && (
          <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">
            {actions}
          </div>
        )}
      </header>

      {/* 主体:state 优先 (载/错),否则 内容 + aside 两栏 */}
      {state ? (
        state
      ) : (
        <div className={`flex flex-col gap-4 lg:flex-row ${bodyMinH}`}>
          <div className="min-w-0 flex-1">{children}</div>
          {aside && <div className="w-full lg:w-auto">{aside}</div>}
        </div>
      )}
    </div>
  );
}
