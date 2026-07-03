'use client';

import { useEffect, useState } from 'react';
import { fetchCatalog, type CatalogEntry } from 'lib/studioApi';
import { setFurnitureCatalog } from 'lib/floorplan/furniture';

// 家具目录 (P2 前后端同源): 全应用拉取一次, 灌入 furniture.ts 模块缓存 (供同步建件函数读
// 真实尺寸), 并把 entries 交给组件用于重渲染 (库分组/类型下拉)。失败静默 —— 前端回退历史
// 本地词表/占位尺寸, 不阻断编辑器。
let _cache: CatalogEntry[] | null = null;
let _inflight: Promise<CatalogEntry[]> | null = null;

function loadOnce(): Promise<CatalogEntry[]> {
  if (_cache) return Promise.resolve(_cache);
  if (!_inflight) {
    _inflight = fetchCatalog()
      .then((r) => {
        _cache = r.types;
        setFurnitureCatalog(r.types);
        return r.types;
      })
      .catch((e) => {
        _inflight = null; // 允许后续挂载重试
        throw e;
      });
  }
  return _inflight;
}

export function useFurnitureCatalog(): CatalogEntry[] {
  const [entries, setEntries] = useState<CatalogEntry[]>(_cache ?? []);
  useEffect(() => {
    let alive = true;
    loadOnce()
      .then((types) => {
        if (alive) setEntries(types);
      })
      .catch(() => {
        /* 静默: 保持回退行为 (占位尺寸 + 本地词表) */
      });
    return () => {
      alive = false;
    };
  }, []);
  return entries;
}
