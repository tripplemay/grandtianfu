'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  fetchBaselineGeometry,
  fetchGeometry,
  postDerive,
  fetchFurniture,
} from 'lib/studioApi';
import type { Geometry, DeriveResult } from 'lib/floorplan/types';
import { type Furniture, ensureFurnitureIds } from 'lib/floorplan/furniture';

export type LoadState = 'idle' | 'loading' | 'ready' | 'error';
export type FurnitureLoadState = 'idle' | 'loading' | 'ready' | 'error';

// 项目数据层 (两模式共享): 载入 geometry -> 首次 derive -> 载入 furniture。
// 持有 G/gRef/derived/furniture/furnRef 等核心容器, 供几何/家具编辑器各自挂接。
export function useProjectData(
  projectId: string,
  schemeId = 'default',
  baselineVersionId?: string,
) {
  const [G, setG] = useState<Geometry | null>(null);
  const [derived, setDerived] = useState<DeriveResult | null>(null);
  const [loadState, setLoadState] = useState<LoadState>('idle');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [furniture, setFurniture] = useState<Furniture[]>([]);
  const [furnitureLoadState, setFurnitureLoadState] =
    useState<FurnitureLoadState>('idle');
  const [furnitureLoadError, setFurnitureLoadError] = useState<string | null>(
    null,
  );

  const gRef = useRef<Geometry | null>(null);
  const furnRef = useRef<Furniture[]>([]);
  const furnitureRequest = useRef(0);
  const activeProject = useRef(projectId);
  const activeScheme = useRef(schemeId);
  activeProject.current = projectId;
  activeScheme.current = schemeId;

  const loadFurniture = useCallback(async () => {
    const pid = projectId;
    const sid = schemeId;
    const request = ++furnitureRequest.current;
    setFurnitureLoadState('loading');
    setFurnitureLoadError(null);
    try {
      const raw = (await fetchFurniture(pid, sid)) as unknown as Furniture[];
      if (
        request !== furnitureRequest.current ||
        activeProject.current !== pid ||
        activeScheme.current !== sid
      )
        return false;
      const f = ensureFurnitureIds(raw);
      furnRef.current = f;
      setFurniture(f);
      setFurnitureLoadState('ready');
      return true;
    } catch (e) {
      if (
        request !== furnitureRequest.current ||
        activeProject.current !== pid ||
        activeScheme.current !== sid
      )
        return false;
      // 失败时保留当前内存数据，绝不把远端已有家具解释为空数组。
      setFurnitureLoadError(e instanceof Error ? e.message : String(e));
      setFurnitureLoadState('error');
      return false;
    }
  }, [projectId, schemeId]);

  // ---- 载入 geometry -> derive (§⑧) ---- //
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    // 项目切换必须清空上一项目数据；loading/error 状态会阻止空数组被保存。
    gRef.current = null;
    setG(null);
    setDerived(null);
    furnRef.current = [];
    setFurniture([]);
    setFurnitureLoadState('idle');
    setFurnitureLoadError(null);
    (async () => {
      setLoadState('loading');
      setLoadError(null);
      try {
        const g = (baselineVersionId
          ? await fetchBaselineGeometry(projectId, baselineVersionId)
          : await fetchGeometry(projectId)) as unknown as Geometry;
        if (!alive) return;
        gRef.current = g;
        setG(g);
        const d = await postDerive(g, controller.signal);
        if (!alive) return;
        setDerived(d as unknown as DeriveResult);
        await loadFurniture();
        if (!alive) return;
        // 几何可继续使用；家具失败由独立状态阻断家具编辑和保存，并提供重试。
        setLoadState('ready');
      } catch (e) {
        if (!alive) return;
        if (e instanceof DOMException && e.name === 'AbortError') return;
        setLoadError(e instanceof Error ? e.message : String(e));
        setLoadState('error');
      }
    })();
    return () => {
      alive = false;
      controller.abort();
      furnitureRequest.current += 1;
    };
  }, [projectId, schemeId, baselineVersionId, loadFurniture]);

  return {
    G,
    setG,
    gRef,
    derived,
    setDerived,
    furniture,
    setFurniture,
    furnRef,
    furnitureLoadState,
    furnitureLoadError,
    reloadFurniture: loadFurniture,
    loadState,
    loadError,
  };
}

export type ProjectData = ReturnType<typeof useProjectData>;
