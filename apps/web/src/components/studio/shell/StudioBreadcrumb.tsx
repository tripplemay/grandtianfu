'use client';

import React from 'react';
import NavLink from 'components/link/NavLink';
import {
  useProjectNav,
  projectPageLabel,
} from './ProjectNavContext';

// 面包屑 (§2.2):阅天府软装 / {项目名} / {页名}。
// 接入 StudioNavbar 替换原 brandRoot/brandText 两段式。
// 非项目作用域(项目台/设置)时只显示「阅天府软装 / {顶层页名}」。
export default function StudioBreadcrumb({
  rootLabel = '阅天府软装',
  topName,
}: {
  rootLabel?: string;
  // 非项目作用域时的顶层页名(由 getActiveRoute 提供,如「项目台」)。
  topName?: string;
}) {
  const { inProject, id, name, page } = useProjectNav();

  const sep = (
    <span className="mx-1.5 text-gray-400 dark:text-gray-500">/</span>
  );

  return (
    <div className="flex flex-wrap items-center text-sm">
      <NavLink
        href="/studio/projects"
        className="font-normal text-gray-600 hover:underline dark:text-gray-300"
      >
        {rootLabel}
      </NavLink>
      {inProject ? (
        <>
          {sep}
          <NavLink
            href={`/studio/projects/${encodeURIComponent(id ?? '')}/overview`}
            className="font-normal text-gray-600 hover:underline dark:text-gray-300"
          >
            {name}
          </NavLink>
          {sep}
          <span className="font-medium text-navy-700 dark:text-white">
            {projectPageLabel(page)}
          </span>
        </>
      ) : (
        topName && (
          <>
            {sep}
            <span className="font-medium text-navy-700 dark:text-white">
              {topName}
            </span>
          </>
        )
      )}
    </div>
  );
}

// 顶栏大标题文字(页名):项目内取页名,否则取顶层页名。
export function useActivePageTitle(topName: string): string {
  const { inProject, page } = useProjectNav();
  if (inProject) return projectPageLabel(page);
  return topName;
}
