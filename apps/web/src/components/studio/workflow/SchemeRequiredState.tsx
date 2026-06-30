'use client';

import React from 'react';
import Link from 'next/link';
import EmptyState from 'components/studio/ui/EmptyState';
import { MdChair } from 'react-icons/md';

export default function SchemeRequiredState({
  projectId,
}: {
  projectId: string;
}) {
  return (
    <EmptyState
      icon={<MdChair className="h-6 w-6" />}
      title="请选择一套软装方案"
      description="方案工作页必须通过 URL 显式携带 scheme，不能静默使用初始方案。"
      action={
        <Link
          href={`/studio/projects/${encodeURIComponent(projectId)}/scheme`}
          className="inline-flex rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
        >
          去方案中心选择
        </Link>
      }
    />
  );
}
