import React from 'react';
import { MdGridView } from 'react-icons/md';
import { IRoute } from 'types/navigation';

// Studio (阅天府软装工作台) 导航配置,与 demo `routes.tsx` 隔离。
// Phase 1: 仅顶层「项目台」。后续阶段在此扩展(设置、当前项目分组等)。
// 结构沿用 Horizon IRoute[]:layout('/studio') + path 拼成 href。
const studioRoutes: IRoute[] = [
  {
    name: '项目台',
    layout: '/studio',
    path: '/projects',
    icon: <MdGridView className="text-inherit h-5 w-5" />,
  },
];

export default studioRoutes;
