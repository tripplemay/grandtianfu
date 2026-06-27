'use client';

import React, { use } from 'react';
import FloorplanPreview from 'components/studio/FloorplanPreview';

// Next 15:client component 中 params 为 Promise,用 React.use 解包。
export default function EditorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-6">
      <header className="mb-4">
        <h1 className="text-2xl font-bold text-navy-700 dark:text-white">
          双模编辑器(骨架)
        </h1>
        <p className="text-sm text-gray-600 dark:text-gray-300">
          实时预览:GET 几何 → POST /api/derive → 受控 inline SVG 线框。
        </p>
      </header>
      <FloorplanPreview projectId={id} />
    </div>
  );
}
