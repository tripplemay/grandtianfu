'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useSearchParams } from 'next/navigation';
import {
  fetchProject,
  listBaselines,
  listSchemes,
  type BaselineMeta,
  type FurnitureSchemeSummary,
  type ProjectMeta,
} from 'lib/studioApi';

export interface ProjectWorkflowValue {
  projectId: string;
  project: ProjectMeta | null;
  currentBaseline: BaselineMeta | null;
  viewingBaseline: BaselineMeta | null;
  baselines: BaselineMeta[];
  currentScheme: FurnitureSchemeSummary | null;
  availableSchemes: FurnitureSchemeSummary[];
  isHistorical: boolean;
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
}

const ProjectWorkflowContext = createContext<ProjectWorkflowValue | null>(null);

export function ProjectWorkflowProvider({
  projectId,
  children,
}: {
  projectId: string;
  children: React.ReactNode;
}) {
  const search = useSearchParams();
  const schemeId = search.get('scheme');
  const baselineParam = search.get('baseline') || search.get('version');

  const [project, setProject] = useState<ProjectMeta | null>(null);
  const [baselines, setBaselines] = useState<BaselineMeta[]>([]);
  const [schemes, setSchemes] = useState<FurnitureSchemeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [projectMeta, baselineList] = await Promise.all([
        fetchProject(projectId),
        listBaselines(projectId),
      ]);
      const currentVersion = projectMeta.current_baseline_version_id;
      const schemeList = await listSchemes(projectId, {
        baselineVersionId: baselineParam || currentVersion,
      });
      setProject(projectMeta);
      setBaselines(baselineList);
      setSchemes(schemeList);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [projectId, baselineParam]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    void (async () => {
      try {
        const [projectMeta, baselineList] = await Promise.all([
          fetchProject(projectId),
          listBaselines(projectId),
        ]);
        if (!alive) return;
        const currentVersion = projectMeta.current_baseline_version_id;
        const schemeList = await listSchemes(projectId, {
          baselineVersionId: baselineParam || currentVersion,
        });
        if (!alive) return;
        setProject(projectMeta);
        setBaselines(baselineList);
        setSchemes(schemeList);
        setError(null);
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId, baselineParam]);

  const value = useMemo<ProjectWorkflowValue>(() => {
    const currentVersion = project?.current_baseline_version_id ?? 'v1';
    const viewingVersion = baselineParam || currentVersion;
    const currentBaseline =
      baselines.find((b) => b.id === currentVersion) ?? null;
    const viewingBaseline =
      baselines.find((b) => b.id === viewingVersion) ?? currentBaseline;
    const currentScheme =
      schemes.find((scheme) => scheme.id === schemeId) ?? null;
    return {
      projectId,
      project,
      currentBaseline,
      viewingBaseline,
      baselines,
      currentScheme,
      availableSchemes: schemes,
      isHistorical: !!viewingBaseline && viewingBaseline.id !== currentVersion,
      loading,
      error,
      reload,
    };
  }, [
    projectId,
    project,
    baselines,
    schemes,
    schemeId,
    baselineParam,
    loading,
    error,
    reload,
  ]);

  return (
    <ProjectWorkflowContext.Provider value={value}>
      {children}
    </ProjectWorkflowContext.Provider>
  );
}

export function useProjectWorkflow(): ProjectWorkflowValue {
  const value = useContext(ProjectWorkflowContext);
  if (!value) {
    throw new Error('useProjectWorkflow must be used within ProjectWorkflowProvider');
  }
  return value;
}
