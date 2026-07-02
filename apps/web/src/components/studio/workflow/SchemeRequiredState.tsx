'use client';

import React from 'react';
import EmptyState from 'components/studio/ui/EmptyState';
import { LinkButton } from 'components/studio/ui/buttons';
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
        <LinkButton
          href={`/studio/projects/${encodeURIComponent(projectId)}/scheme`}
          variant="primary"
        >
          去方案中心选择
        </LinkButton>
      }
    />
  );
}
