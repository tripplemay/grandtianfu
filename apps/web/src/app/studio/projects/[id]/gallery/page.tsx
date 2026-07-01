'use client';

import React, { use } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import Card from 'components/card';
import { API_BASE } from 'lib/studioApi';
import PageShell from 'components/studio/ui/PageShell';
import RenderImage from 'components/studio/ui/RenderImage';
import SchemeRequiredState from 'components/studio/workflow/SchemeRequiredState';

// 画廊 (Stage C): 三张 Card 展示 2D平面 / 轴测照片底图 / 轴测空壳。
// 每张 RenderImage (骨架+onError 兜底) + 「下载SVG」。
// AI 写实效果图 (#6/#7) 接入待后续。Next 15: client 组件 params 为 Promise, 用 use 解包。

interface RenderView {
  mode: 'plan2d' | 'photo' | 'shell';
  title: string;
  desc: string;
}

const VIEWS: RenderView[] = [
  {
    mode: 'plan2d',
    title: '2D 平面图',
    desc: '房间/门窗/标注派生平面 (render_plan_2d)',
  },
  {
    mode: 'photo',
    title: '轴测照片底图',
    desc: '写实风轴测底图 (render mode=photo)',
  },
  {
    mode: 'shell',
    title: '轴测空壳',
    desc: '几何空壳轴测 (render mode=shell)',
  },
];

export default function GalleryPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const search = useSearchParams();
  const schemeId = search.get('scheme');
  if (!schemeId) {
    return (
      <PageShell title="方案预览" description="请选择当前要预览的软装方案。">
        <SchemeRequiredState projectId={id} />
      </PageShell>
    );
  }
  const src = (mode: string) =>
    `${API_BASE}/projects/${encodeURIComponent(
      id,
    )}/schemes/${encodeURIComponent(schemeId)}/render?mode=${mode}`;

  return (
    <PageShell
      title="方案预览"
      description={`2D 平面 / 轴测照片底图 / 轴测空壳,均由引擎实时渲染 (SVG)。当前方案:${schemeId}。`}
      actions={
        <div className="flex items-center gap-2">
          {/* 承上启下 CTA:预览确认布局后可直接出图, 或退回编辑器改家具 */}
          <Link
            href={`/studio/projects/${encodeURIComponent(
              id,
            )}/editor?scheme=${encodeURIComponent(schemeId)}&tab=furniture`}
            className="inline-flex items-center rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white"
          >
            回去调整家具
          </Link>
          <Link
            href={`/studio/projects/${encodeURIComponent(
              id,
            )}/render?scheme=${encodeURIComponent(schemeId)}`}
            className="inline-flex items-center rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
          >
            生成 AI 效果图 →
          </Link>
        </div>
      }
    >
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {VIEWS.map((v) => (
          <Card
            key={v.mode}
            extra="flex flex-col w-full !p-4 border border-gray-200 !shadow-none dark:border-white/10"
          >
            <div className="mb-3 w-full overflow-hidden rounded-xl bg-gray-50 dark:bg-navy-900">
              <RenderImage
                src={src(v.mode)}
                alt={`${id} ${v.title}`}
                className="h-72"
                imgClassName="h-72 w-full object-contain"
                fallbackLabel={`${v.title} 加载失败`}
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
              download={`${id}-${schemeId}-${v.mode}.svg`}
              className="mt-auto inline-flex w-fit items-center rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600"
            >
              下载 SVG
            </a>
          </Card>
        ))}
      </div>
    </PageShell>
  );
}
