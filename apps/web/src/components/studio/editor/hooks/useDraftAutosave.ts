'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { Geometry } from 'lib/floorplan/types';
import { type Furniture, ensureFurnitureIds } from 'lib/floorplan/furniture';
import {
  readDraft,
  writeDraft,
  clearDraft,
  type DraftEnvelope,
} from 'lib/floorplan/draft';

// 自动草稿 (阶段 5b / P3): 编辑(dirty)时 debounce 写 localStorage; 载入时若存在草稿
// 提示恢复 (恢复/丢弃); 保存成功 (dirty true->false) 清草稿。不改变保存语义。

const DEBOUNCE_MS = 600;

interface Params {
  projectId: string;
  schemeId?: string;
  ready: boolean;
  G: Geometry | null;
  geoDirty: boolean;
  setG: React.Dispatch<React.SetStateAction<Geometry | null>>;
  gRef: React.MutableRefObject<Geometry | null>;
  furniture: Furniture[];
  furnDirty: boolean;
  setFurniture: React.Dispatch<React.SetStateAction<Furniture[]>>;
  furnRef: React.MutableRefObject<Furniture[]>;
  // 恢复后按域回调: 几何需重派生 + 置脏; 家具置脏。
  onRecoverGeo: () => void;
  onRecoverFurn: () => void;
}

export interface DraftPending {
  hasGeo: boolean;
  hasFurn: boolean;
}

export function useDraftAutosave({
  projectId,
  schemeId = 'default',
  ready,
  G,
  geoDirty,
  setG,
  gRef,
  furniture,
  furnDirty,
  setFurniture,
  furnRef,
  onRecoverGeo,
  onRecoverFurn,
}: Params) {
  const [pending, setPending] = useState<DraftPending | null>(null);
  const furnitureDraftProjectId = `${projectId}:scheme:${schemeId}`;
  const checkedRef = useRef(false);
  const checkedKeyRef = useRef('');
  // 已发现的草稿信封 (恢复时取用)。
  const geoDraftRef = useRef<DraftEnvelope<Geometry> | null>(null);
  const furnDraftRef = useRef<DraftEnvelope<Furniture[]> | null>(null);

  // ---- 载入就绪后检查一次草稿 -> 提示恢复 ---- //
  useEffect(() => {
    const key = `${projectId}|${furnitureDraftProjectId}`;
    if (checkedKeyRef.current !== key) {
      checkedRef.current = false;
      checkedKeyRef.current = key;
      setPending(null);
    }
    if (!ready || checkedRef.current) return;
    checkedRef.current = true;
    const gd = readDraft<Geometry>(projectId, 'geometry');
    const fd = readDraft<Furniture[]>(furnitureDraftProjectId, 'furniture');
    geoDraftRef.current = gd;
    furnDraftRef.current = fd;
    if (gd || fd) setPending({ hasGeo: !!gd, hasFurn: !!fd });
  }, [ready, projectId, furnitureDraftProjectId]);

  // ---- 几何草稿 debounce 写 ---- //
  useEffect(() => {
    if (!ready || !geoDirty || !G) return;
    const t = setTimeout(() => writeDraft(projectId, 'geometry', G), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [ready, geoDirty, G, projectId]);

  // ---- 家具草稿 debounce 写 ---- //
  useEffect(() => {
    if (!ready || !furnDirty) return;
    const t = setTimeout(
      () => writeDraft(furnitureDraftProjectId, 'furniture', furniture),
      DEBOUNCE_MS,
    );
    return () => clearTimeout(t);
  }, [ready, furnDirty, furniture, furnitureDraftProjectId]);

  // ---- 保存成功 (dirty true->false) 清对应域草稿 ---- //
  const prevGeoDirty = useRef(geoDirty);
  useEffect(() => {
    if (prevGeoDirty.current && !geoDirty) clearDraft(projectId, 'geometry');
    prevGeoDirty.current = geoDirty;
  }, [geoDirty, projectId]);

  const prevFurnDirty = useRef(furnDirty);
  useEffect(() => {
    if (prevFurnDirty.current && !furnDirty)
      clearDraft(furnitureDraftProjectId, 'furniture');
    prevFurnDirty.current = furnDirty;
  }, [furnDirty, furnitureDraftProjectId]);

  // ---- 恢复: 把草稿写回 state/ref + 触发重派生/置脏 ---- //
  const recover = useCallback(() => {
    const gd = geoDraftRef.current;
    const fd = furnDraftRef.current;
    if (gd?.data) {
      gRef.current = gd.data;
      setG(gd.data);
      onRecoverGeo();
    }
    if (fd?.data) {
      // 恢复的家具补齐运行时 id (草稿可能来自更早版本)。
      const f = ensureFurnitureIds(fd.data);
      furnRef.current = f;
      setFurniture(f);
      onRecoverFurn();
    }
    setPending(null);
  }, [gRef, setG, furnRef, setFurniture, onRecoverGeo, onRecoverFurn]);

  // ---- 丢弃: 清两域草稿, 用远端 ---- //
  const discard = useCallback(() => {
    clearDraft(projectId, 'geometry');
    clearDraft(furnitureDraftProjectId, 'furniture');
    setPending(null);
  }, [projectId, furnitureDraftProjectId]);

  return { pending, recover, discard };
}

export type DraftAutosave = ReturnType<typeof useDraftAutosave>;
