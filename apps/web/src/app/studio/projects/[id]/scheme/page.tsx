'use client';

import React, { use } from 'react';
import { MdChair } from 'react-icons/md';
import PageShell from 'components/studio/ui/PageShell';
import EmptyState from 'components/studio/ui/EmptyState';

// 软装方案 (#4,占位)。项目作用域:/studio/projects/[id]/scheme。
// Phase 5「零摩擦接入」示范:仅注册 projectScopedItems 一项 + 本 page 套 PageShell。
// 真实「软装风格对话/方案生成」业务待后续接入 (见 §⑥ 不必做)。
// Next 15:client 组件 params 为 Promise,用 use 解包。
// SSG/export:动态段 [id] 由上层 [id]/layout.tsx 的 generateStaticParams 枚举。
export default function SchemePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  return (
    <PageShell
      title="软装方案"
      description={`户型 ${id} 的软装风格对话与方案生成(#4)。即将上线。`}
    >
      <EmptyState
        icon={<MdChair className="h-6 w-6" />}
        title="软装方案 · 即将上线"
        description="未来这里将提供软装风格对话、配色与家具方案生成。框架已就位,业务接入中。"
      />
    </PageShell>
  );
}
