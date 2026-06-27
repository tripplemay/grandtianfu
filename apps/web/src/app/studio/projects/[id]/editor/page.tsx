'use client';

import React, { use } from 'react';
import FloorplanEditor from 'components/studio/editor/FloorplanEditor';

// Next 15:client component 中 params 为 Promise,用 React.use 解包。
export default function EditorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  return (
    <div className="mx-auto w-full max-w-[1400px] px-4 py-6">
      <header className="mb-4">
        <h1 className="text-2xl font-bold text-navy-700 dark:text-white">
          几何编辑器
        </h1>
        <p className="text-sm text-gray-600 dark:text-gray-300">
          拖房间/把手缩放 · 沿墙滑门窗 · 实时派生预览 ·
          校验保存(/save-geometry)。
        </p>
      </header>
      <FloorplanEditor projectId={id} />
    </div>
  );
}
