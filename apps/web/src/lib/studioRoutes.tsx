import React from 'react';
import {
  MdGridView,
  MdEdit,
  MdImage,
  MdChair,
  MdAutoAwesome,
  MdSettings,
} from 'react-icons/md';
import { IRoute } from 'types/navigation';

// Studio (阅天府软装工作台) 导航配置,与 demo `routes.tsx` 隔离。
// 顶层全局作用域 + 项目作用域(命中 [id] 时由 StudioSidebar 动态插入「当前项目」分组)。
// 结构沿用 Horizon IRoute[]:layout('/studio') + path 拼成 href。
//
// 「零摩擦接入」配方 (Phase 5):新增一个功能 = 在此注册一条路由 + 新建一个
// 套 <PageShell> 的 page.tsx。外壳/侧栏/面包屑/主题/响应式/留白自动获得。
const studioRoutes: IRoute[] = [
  {
    name: '项目台',
    layout: '/studio',
    path: '/projects',
    icon: <MdGridView className="text-inherit h-5 w-5" />,
  },
  {
    name: '设置',
    layout: '/studio',
    path: '/settings',
    icon: <MdSettings className="text-inherit h-5 w-5" />,
  },
];

// 项目作用域子项 (§2.2):命中 /studio/projects/[id]/* 时在「当前项目」分组下展示。
// comingSoon=true 的项(软装方案 #4 / 效果图 #6)灰显不可点,占位页留待 Phase 5。
export interface ProjectScopedItem {
  // 路由子段 (拼 /studio/projects/[id]/<sub>);亦用于面包屑页名匹配。
  sub: string;
  name: string;
  icon: React.ReactNode;
  comingSoon?: boolean;
}

export const projectScopedItems: ProjectScopedItem[] = [
  { sub: 'editor', name: '编辑器', icon: <MdEdit className="h-4 w-4" /> },
  { sub: 'gallery', name: '画廊', icon: <MdImage className="h-4 w-4" /> },
  {
    sub: 'scheme',
    name: '软装方案',
    icon: <MdChair className="h-4 w-4" />,
    comingSoon: true,
  },
  {
    sub: 'render',
    name: '效果图',
    icon: <MdAutoAwesome className="h-4 w-4" />,
    comingSoon: true,
  },
];

export default studioRoutes;
