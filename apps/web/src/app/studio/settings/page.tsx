'use client';

import React from 'react';
import { MdSettings } from 'react-icons/md';
import PageShell from 'components/studio/ui/PageShell';
import EmptyState from 'components/studio/ui/EmptyState';

// 全局设置 (占位)。全局作用域:/studio/settings。
// Phase 5「零摩擦接入」示范:仅在 studioRoutes 注册一条 + 本 page 套 PageShell,
// 外壳/侧栏/面包屑/主题/响应式自动获得。账户/工作区等真实设置待后续 (见 §⑥)。
export default function SettingsPage() {
  return (
    <PageShell
      title="设置"
      description="全局偏好与账户设置。即将上线。"
    >
      <EmptyState
        icon={<MdSettings className="h-6 w-6" />}
        title="设置 · 即将上线"
        description="未来这里将提供账户、工作区与全局偏好设置。框架已就位,业务接入中。"
      />
    </PageShell>
  );
}
