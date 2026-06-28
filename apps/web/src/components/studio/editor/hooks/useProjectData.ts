'use client';

import { useEffect, useRef, useState } from 'react';
import { fetchGeometry, postDerive, fetchFurniture } from 'lib/studioApi';
import type { Geometry, DeriveResult } from 'lib/floorplan/types';
import { type Furniture, ensureFurnitureIds } from 'lib/floorplan/furniture';

export type LoadState = 'idle' | 'loading' | 'ready' | 'error';

// 项目数据层 (两模式共享): 载入 geometry -> 首次 derive -> 并行载入 furniture。
// 持有 G/gRef/derived/furniture/furnRef 等核心容器, 供几何/家具编辑器各自挂接。
export function useProjectData(projectId: string) {
  const [G, setG] = useState<Geometry | null>(null);
  const [derived, setDerived] = useState<DeriveResult | null>(null);
  const [loadState, setLoadState] = useState<LoadState>('idle');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [furniture, setFurniture] = useState<Furniture[]>([]);

  const gRef = useRef<Geometry | null>(null);
  const furnRef = useRef<Furniture[]>([]);

  // ---- 载入 geometry -> derive (§⑧) ---- //
  useEffect(() => {
    let alive = true;
    (async () => {
      setLoadState('loading');
      setLoadError(null);
      try {
        const g = (await fetchGeometry(projectId)) as unknown as Geometry;
        if (!alive) return;
        gRef.current = g;
        setG(g);
        const d = await postDerive(g);
        if (!alive) return;
        setDerived(d as unknown as DeriveResult);
        // 家具并行载入 (B2): 失败不阻塞几何就绪, 仅置空家具。
        try {
          const raw = (await fetchFurniture(
            projectId,
          )) as unknown as Furniture[];
          if (!alive) return;
          // 阶段 0: 载入时为旧件补稳定 id (运行时迁移, 不改盘上格式)。
          const f = ensureFurnitureIds(raw);
          furnRef.current = f;
          setFurniture(f);
        } catch {
          furnRef.current = [];
          setFurniture([]);
        }
        setLoadState('ready');
      } catch (e) {
        if (!alive) return;
        setLoadError(e instanceof Error ? e.message : String(e));
        setLoadState('error');
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId]);

  return {
    G,
    setG,
    gRef,
    derived,
    setDerived,
    furniture,
    setFurniture,
    furnRef,
    loadState,
    loadError,
  };
}

export type ProjectData = ReturnType<typeof useProjectData>;
