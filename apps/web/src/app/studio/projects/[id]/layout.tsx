import React, { ReactNode, use } from 'react';
import { ProjectWorkflowProvider } from 'components/studio/workflow/ProjectWorkflowContext';

// 路 A(output:'export')下,动态段 [id] 必须由 generateStaticParams 枚举要预渲染的项目。
// 骨架阶段仅 D 户型;接入项目台后从后端列表生成。dev/node 构建 (yarn build) 不导出,
// 动态段在运行时渲染,此函数仅服务 build:export 基线。
export function generateStaticParams() {
  return [{ id: 'D' }];
}

// 服务端组件 (保留 generateStaticParams)。
// 项目内导航已由 壳层侧栏「当前项目」分组 + 顶栏面包屑 接管 (Phase 2),
// 故移除原 ProjectTabs(避免水平 tab 溢出 + 双导航)。项目作用域上下文
// (id/名) 在壳层 ProjectNavProvider 经 usePathname 派生,无需在此注入。
export default function ProjectLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <ProjectWorkflowProvider projectId={id}>{children}</ProjectWorkflowProvider>;
}
