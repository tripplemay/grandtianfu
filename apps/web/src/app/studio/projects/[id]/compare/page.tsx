'use client';

import React, { use } from 'react';
import PageShell from 'components/studio/ui/PageShell';
import EmptyState from 'components/studio/ui/EmptyState';
import { MdCompare } from 'react-icons/md';

export default function ComparePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  use(params);
  return (
    <PageShell
      title="方案对比"
      description="本入口用于同一户型版本下 2–3 套方案统一视图比较。"
    >
      <EmptyState
        icon={<MdCompare className="h-6 w-6" />}
        title="方案对比将在阶段 5 实现"
        description="当前阶段先完成项目基线、持续上下文和方案内显式 scheme 规则。"
      />
    </PageShell>
  );
}
