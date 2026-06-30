'use client';

import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { usePathname } from 'next/navigation';
import { listProjects } from 'lib/studioApi';

// 项目作用域上下文 (§2.2):命中 /studio/projects/[id]/* 时提供 { id, name, page }。
// 供 StudioSidebar「当前项目」动态分组 与 StudioBreadcrumb 面包屑消费。
//
// 注:React context 只能向下流动,而侧栏/顶栏在 studio/layout.tsx(壳)中、位于
// [id]/layout.tsx 之上,故 Provider 必须挂在壳层。这里从 usePathname 派生 id,
// name 经 listProjects 解析(id 兜底),实现「在项目作用域注入 id+名」的等效效果;
// [id]/layout.tsx 仍保留 generateStaticParams(SSG 路 A 基线)。

export interface ProjectNavValue {
  // 是否处于项目作用域 (/studio/projects/[id]/*)。
  inProject: boolean;
  id: string | null;
  name: string | null; // 解析中或失败时回退到 id。
  // 当前项目内页:editor / gallery / 其它 (占位)。
  page: string | null;
}

const ProjectNavContext = createContext<ProjectNavValue>({
  inProject: false,
  id: null,
  name: null,
  page: null,
});

// 从 pathname 派生项目 id 与子页。/studio/projects/<id>/<page?>
function parsePath(pathname: string): { id: string | null; page: string | null } {
  const parts = (pathname || '').split('/').filter(Boolean);
  // ['studio','projects', id, page?]
  if (parts[0] === 'studio' && parts[1] === 'projects' && parts[2]) {
    return { id: decodeURIComponent(parts[2]), page: parts[3] ?? null };
  }
  return { id: null, page: null };
}

export function ProjectNavProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname() || '';
  const { id, page } = parsePath(pathname);
  const [nameMap, setNameMap] = useState<Record<string, string>>({});

  // 解析项目名:仅当处于项目作用域且尚未缓存该 id 时拉一次列表。
  useEffect(() => {
    if (!id || nameMap[id] !== undefined) return;
    let alive = true;
    void (async () => {
      try {
        const list = await listProjects();
        if (!alive) return;
        const next: Record<string, string> = {};
        for (const p of list) next[p.id] = p.name;
        setNameMap((prev) => ({ ...prev, ...next }));
      } catch {
        // 失败:不缓存,name 走 id 兜底。
      }
    })();
    return () => {
      alive = false;
    };
  }, [id, nameMap]);

  const value = useMemo<ProjectNavValue>(() => {
    if (!id) {
      return { inProject: false, id: null, name: null, page: null };
    }
    return {
      inProject: true,
      id,
      name: nameMap[id] ?? id,
      page,
    };
  }, [id, page, nameMap]);

  return (
    <ProjectNavContext.Provider value={value}>
      {children}
    </ProjectNavContext.Provider>
  );
}

export function useProjectNav(): ProjectNavValue {
  return useContext(ProjectNavContext);
}

// 项目内页 → 中文页名 (面包屑 / 顶栏大标题)。
export const PROJECT_PAGE_LABELS: Record<string, string> = {
  overview: '项目概览',
  baseline: '户型基线',
  versions: '版本记录',
  scheme: '方案中心',
  compare: '方案对比',
  editor: '家具布置',
  gallery: '方案预览',
  render: 'AI 效果图',
  'real-render': '实拍效果图',
};

export function projectPageLabel(page: string | null): string {
  if (!page) return '项目概览';
  return PROJECT_PAGE_LABELS[page] ?? page;
}
