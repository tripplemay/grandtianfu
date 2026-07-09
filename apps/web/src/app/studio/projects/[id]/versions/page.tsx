'use client';

import React, { use, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import PageShell from 'components/studio/ui/PageShell';
import LoadingState from 'components/studio/ui/LoadingState';

// 「版本记录」已并入「户型基线」页(左栏版本时间线)。此路由保留为兼容旧深链接的
// 客户端重定向壳 —— 静态导出(output:export)不支持服务端重定向, 故用 router.replace;
// 保留该路由以避免旧链接在导出产物中 404。透传 ?version= 定位到具体版本。
export default function VersionsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const search = useSearchParams();

  useEffect(() => {
    const version = search.get('version') || search.get('baseline');
    const qs = version ? `?version=${encodeURIComponent(version)}` : '';
    router.replace(`/studio/projects/${encodeURIComponent(id)}/baseline${qs}`);
  }, [id, search, router]);

  return (
    <PageShell
      title="版本记录"
      description="已并入「户型基线」，正在跳转…"
      state={<LoadingState rows={1} />}
    />
  );
}
