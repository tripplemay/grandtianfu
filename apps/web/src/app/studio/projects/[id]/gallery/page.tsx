'use client';

import React, { use } from 'react';
import Card from 'components/card';
import { API_BASE } from 'lib/studioApi';

// 画廊 (Stage C): 三张 Card 展示 2D平面 / 轴测照片底图 / 轴测空壳。
// 每张 <img src=/api/projects/{id}/render?mode=...> + 「下载SVG」。
// AI 写实效果图 (#6/#7) 接入待后续。Next 15: client 组件 params 为 Promise, 用 use 解包。

interface RenderView {
  mode: 'plan2d' | 'photo' | 'shell';
  title: string;
  desc: string;
}

const VIEWS: RenderView[] = [
  { mode: 'plan2d', title: '2D 平面图', desc: '房间/门窗/标注派生平面 (render_plan_2d)' },
  { mode: 'photo', title: '轴测照片底图', desc: '写实风轴测底图 (render mode=photo)' },
  { mode: 'shell', title: '轴测空壳', desc: '几何空壳轴测 (render mode=shell)' },
];

export default function GalleryPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const src = (mode: string) =>
    `${API_BASE}/projects/${encodeURIComponent(id)}/render?mode=${mode}`;

  return (
    <div className="mx-auto w-full max-w-[1400px] px-4 py-6">
      <header className="mb-4">
        <h1 className="text-2xl font-bold text-navy-700 dark:text-white">
          效果图画廊 · {id}
        </h1>
        <p className="text-sm text-gray-600 dark:text-gray-300">
          2D 平面 / 轴测照片底图 / 轴测空壳,均由引擎实时渲染 (SVG)。
          AI 写实效果图(#6/#7)接入待后续。
        </p>
      </header>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {VIEWS.map((v) => (
          <Card
            key={v.mode}
            extra="flex flex-col w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10"
          >
            <div className="mb-3 w-full overflow-hidden rounded-xl bg-gray-50 dark:bg-navy-900">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={src(v.mode)}
                alt={`${id} ${v.title}`}
                className="h-72 w-full object-contain"
              />
            </div>
            <div className="mb-3">
              <p className="text-lg font-bold text-navy-700 dark:text-white">
                {v.title}
              </p>
              <p className="mt-1 text-sm font-medium text-gray-600 dark:text-gray-300">
                {v.desc}
              </p>
            </div>
            <a
              href={src(v.mode)}
              download={`${id}-${v.mode}.svg`}
              className="mt-auto inline-flex w-fit items-center rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
            >
              下载 SVG
            </a>
          </Card>
        ))}
      </div>
    </div>
  );
}
