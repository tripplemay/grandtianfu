'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import NavLink from 'components/link/NavLink';

// 项目内子导航 (Stage C): 编辑 / 画廊 / 返回项目台。
// SegmentedControl 视觉风格 (互斥药丸), 但承载路由跳转故用 NavLink (而非按钮)。
// 客户端组件: 经 usePathname 派生当前项目 id 与激活分段, 不阻断 layout 的 SSG。
export function ProjectTabs() {
  const pathname = usePathname() || '';
  // /studio/projects/<id>/<tab?> -> 取第三段为 id, 第四段为当前 tab。
  const parts = pathname.split('/').filter(Boolean);
  const id = parts[2] ?? '';
  const current = parts[3] ?? 'editor';

  const base = `/studio/projects/${encodeURIComponent(id)}`;
  const tabs: { key: string; label: string; href: string }[] = [
    { key: 'editor', label: '编辑', href: `${base}/editor` },
    { key: 'gallery', label: '画廊', href: `${base}/gallery` },
    { key: 'back', label: '返回项目台', href: '/studio/projects' },
  ];

  return (
    <nav className="mx-auto w-full max-w-[1400px] px-4 pt-6">
      <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1 dark:border-white/10 dark:bg-navy-900">
        {tabs.map((t) => {
          const active = t.key === current && t.key !== 'back';
          const cls = active
            ? 'rounded-md px-4 py-1.5 text-sm font-medium bg-brand-500 text-white shadow'
            : 'rounded-md px-4 py-1.5 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:text-white dark:hover:bg-navy-700';
          return (
            <NavLink key={t.key} href={t.href} className={cls}>
              {t.label}
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
}

export default ProjectTabs;
