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
  listBaselinePhotos,
  listSchemes,
  type BaselineMeta,
  type BaselinePhoto,
  type FurnitureSchemeSummary,
  type ProjectMeta,
} from 'lib/studioApi';

const _VIEWS = ['v0', 'v1', 'v2', 'v3'];

// 空房照可用于实拍生成的判定 (与后端 readiness gate 对齐): 用途空房 (empty/null) 且已标注
// 房间与合法拍摄视角。stepper 第 5 步「上传标注空房照」据此判 done。
function _isReadyPhoto(p: BaselinePhoto): boolean {
  const emptyPurpose = p.purpose == null || p.purpose === 'empty';
  return (
    emptyPurpose && !!p.room_id && !!p.direction && _VIEWS.includes(p.direction)
  );
}

export interface ProjectWorkflowValue {
  projectId: string;
  project: ProjectMeta | null;
  currentBaseline: BaselineMeta | null;
  viewingBaseline: BaselineMeta | null;
  baselines: BaselineMeta[];
  currentScheme: FurnitureSchemeSummary | null;
  availableSchemes: FurnitureSchemeSummary[];
  // 工作流改造 (B1): 当前(所看)户型版本的空房照统计, 供 stepper 第 5 步判定。
  emptyPhotoCount: number;
  readyPhotoCount: number;
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
  const [photos, setPhotos] = useState<BaselinePhoto[]>([]);
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
      const targetVersion = baselineParam || currentVersion;
      let schemeList: FurnitureSchemeSummary[] = [];
      let photoList: BaselinePhoto[] = [];
      if (targetVersion) {
        [schemeList, photoList] = await Promise.all([
          listSchemes(projectId, { baselineVersionId: targetVersion }),
          // 照片缺失不应毒化整个工作流上下文, 失败降级为空。
          listBaselinePhotos(projectId, targetVersion).catch(
            () => [] as BaselinePhoto[],
          ),
        ]);
      }
      setProject(projectMeta);
      setBaselines(baselineList);
      setSchemes(schemeList);
      setPhotos(photoList);
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
        const targetVersion = baselineParam || currentVersion;
        let schemeList: FurnitureSchemeSummary[] = [];
        let photoList: BaselinePhoto[] = [];
        if (targetVersion) {
          [schemeList, photoList] = await Promise.all([
            listSchemes(projectId, { baselineVersionId: targetVersion }),
            listBaselinePhotos(projectId, targetVersion).catch(
              () => [] as BaselinePhoto[],
            ),
          ]);
        }
        if (!alive) return;
        setProject(projectMeta);
        setBaselines(baselineList);
        setSchemes(schemeList);
        setPhotos(photoList);
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
    const currentVersion = project?.current_baseline_version_id ?? null;
    const viewingVersion = baselineParam || currentVersion;
    const currentBaseline = currentVersion
      ? baselines.find((b) => b.id === currentVersion) ?? null
      : null;
    const viewingBaseline = viewingVersion
      ? baselines.find((b) => b.id === viewingVersion) ?? currentBaseline
      : baselines.find((b) => b.status === 'draft') ?? currentBaseline;
    const currentScheme =
      schemes.find((scheme) => scheme.id === schemeId) ?? null;
    const emptyPhotos = photos.filter(
      (p) => p.purpose == null || p.purpose === 'empty',
    );
    return {
      projectId,
      project,
      currentBaseline,
      viewingBaseline,
      baselines,
      currentScheme,
      availableSchemes: schemes,
      emptyPhotoCount: emptyPhotos.length,
      readyPhotoCount: emptyPhotos.filter(_isReadyPhoto).length,
      isHistorical:
        !!currentVersion &&
        !!viewingBaseline &&
        viewingBaseline.id !== currentVersion,
      loading,
      error,
      reload,
    };
  }, [
    projectId,
    project,
    baselines,
    schemes,
    photos,
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
    throw new Error(
      'useProjectWorkflow must be used within ProjectWorkflowProvider',
    );
  }
  return value;
}
