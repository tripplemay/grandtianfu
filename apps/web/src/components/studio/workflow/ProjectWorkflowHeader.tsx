'use client';

import React from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useProjectWorkflow } from './ProjectWorkflowContext';

const SCHEME_PAGES = new Set(['editor', 'gallery', 'render']);

function projectPage(pathname: string): string | null {
  const parts = pathname.split('/').filter(Boolean);
  if (parts[0] === 'studio' && parts[1] === 'projects' && parts[2]) {
    return parts[3] ?? 'overview';
  }
  return null;
}

export default function ProjectWorkflowHeader() {
  const router = useRouter();
  const pathname = usePathname() || '';
  const search = useSearchParams();
  const page = projectPage(pathname);
  const {
    projectId,
    project,
    viewingBaseline,
    currentScheme,
    availableSchemes,
  } = useProjectWorkflow();
  const showSchemeSelector = !!page && SCHEME_PAGES.has(page);

  const onSchemeChange = (schemeId: string) => {
    if (!schemeId) {
      router.push(`/studio/projects/${encodeURIComponent(projectId)}/scheme`);
      return;
    }
    const params = new URLSearchParams(search.toString());
    params.set('scheme', schemeId);
    router.push(`${pathname}?${params.toString()}`);
  };

  return (
    <div className="sticky top-[96px] z-20 mx-auto mb-2 w-full max-w-[1400px] px-4">
      <div className="flex flex-col gap-2 rounded-2xl border border-gray-200 bg-white/90 px-4 py-3 text-sm shadow-sm backdrop-blur dark:border-white/10 dark:bg-navy-800/90 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-2 text-gray-500 dark:text-gray-300">
          <Link
            href={`/studio/projects/${encodeURIComponent(projectId)}/overview`}
            className="font-medium text-navy-700 hover:underline dark:text-white"
          >
            {project?.name || projectId}
          </Link>
          <span>/</span>
          <Link
            href={`/studio/projects/${encodeURIComponent(projectId)}/baseline${
              viewingBaseline ? `?version=${encodeURIComponent(viewingBaseline.id)}` : ''
            }`}
            className="font-medium text-navy-700 hover:underline dark:text-white"
          >
            户型 {viewingBaseline?.id ?? '未确认'}
          </Link>
          <span>/</span>
          <span className="font-medium text-navy-700 dark:text-white">
            {currentScheme?.name || (showSchemeSelector ? '请选择方案' : page === 'scheme' ? '方案中心' : '项目')}
          </span>
        </div>
        {showSchemeSelector && (
          <select
            value={currentScheme?.id || ''}
            onChange={(e) => onSchemeChange(e.target.value)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-navy-700 outline-none focus:border-brand-500 dark:border-white/10 dark:bg-navy-900 dark:text-white"
          >
            <option value="">选择方案…</option>
            {availableSchemes.map((scheme) => (
              <option key={scheme.id} value={scheme.id}>
                {scheme.name}
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  );
}
