'use client';

import React, { use } from 'react';
import { MdAutoAwesome } from 'react-icons/md';
import PageShell from 'components/studio/ui/PageShell';
import EmptyState from 'components/studio/ui/EmptyState';

// AI 效果图 (#6,占位)。项目作用域:/studio/projects/[id]/render。
// Phase 5「零摩擦接入」示范:仅注册 projectScopedItems 一项 + 本 page 套 PageShell。
// 真实 AI 写实效果图生成 (接 gateway) 待后续 (见 §⑥ 不必做)。
// Next 15:client 组件 params 为 Promise,用 use 解包。
// SSG/export:动态段 [id] 由上层 [id]/layout.tsx 的 generateStaticParams 枚举。
export default function RenderPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  return (
    <PageShell
      title="效果图"
      description={`户型 ${id} 的 AI 写实效果图生成(#6)。即将上线。`}
    >
      <EmptyState
        icon={<MdAutoAwesome className="h-6 w-6" />}
        title="AI 效果图 · 即将上线"
        description="未来这里将基于户型几何与软装方案生成写实效果图。框架已就位,业务接入中。"
      />
    </PageShell>
  );
}
