import React, { ReactNode } from 'react';
import ProjectTabs from 'components/studio/ui/ProjectTabs';

// 路 A(output:'export')下,动态段 [id] 必须由 generateStaticParams 枚举要预渲染的项目。
// 骨架阶段仅 D 户型;接入项目台后从后端列表生成。dev/node 构建 (yarn build) 不导出,
// 动态段在运行时渲染,此函数仅服务 build:export 基线。
export function generateStaticParams() {
  return [{ id: 'D' }];
}

// 服务端组件 (保留 generateStaticParams)。子导航为独立客户端组件 (usePathname 派生激活态)。
export default function ProjectLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <ProjectTabs />
      {children}
    </>
  );
}
