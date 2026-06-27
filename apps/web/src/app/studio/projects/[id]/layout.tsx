import React, { ReactNode } from 'react';

// 路 A(output:'export')下,动态段 [id] 必须由 generateStaticParams 枚举要预渲染的项目。
// 骨架阶段仅 D 户型;接入项目台后从后端列表生成。
export function generateStaticParams() {
  return [{ id: 'D' }];
}

export default function ProjectLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
