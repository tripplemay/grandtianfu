'use client';

import React, { useEffect, useRef, useState } from 'react';
import {
  listBaselinePhotos,
  uploadBaselinePhoto,
  type BaselinePhoto,
} from 'lib/studioApi';
import { WALL_SIDES } from 'lib/floorplan/units';

type WallSide = 'N' | 'S' | 'E' | 'W';

interface Props {
  projectId: string;
  baselineVersionId: string;
  // 当前房间的 walls (读每面已贴 photo_id)。
  walls?: Record<string, { material?: string; photo_id?: string }>;
  onSetWallPhoto: (side: WallSide, photoId: string) => void;
}

// 墙面实拍材质 (P2 材质C): 逐面挂一张实拍参考图 (photo_id -> 注入 img2img edits, 上限4)。
// 自取本户型版本的 purpose=wall_material 照片; 可选已有 / 上传新图 / 清除。只在户型编辑
// (有 baselineVersionId) 时出现。上传失败/拉取失败静默 (不阻断几何编辑)。
export default function WallPhotoControls({
  projectId,
  baselineVersionId,
  walls,
  onSetWallPhoto,
}: Props) {
  const [photos, setPhotos] = useState<BaselinePhoto[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const pendingSide = useRef<WallSide | null>(null);

  const reload = React.useCallback(() => {
    return listBaselinePhotos(projectId, baselineVersionId)
      .then((all) =>
        setPhotos(all.filter((p) => p.purpose === 'wall_material')),
      )
      .catch(() => {
        /* 静默: 保持空列表, 仍可上传 */
      });
  }, [projectId, baselineVersionId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const onUpload = async (side: WallSide, file: File) => {
    setBusy(true);
    setErr(null);
    try {
      const p = await uploadBaselinePhoto(projectId, baselineVersionId, file, {
        purpose: 'wall_material',
      });
      await reload();
      onSetWallPhoto(side, p.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '上传失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2">
      <p className="text-xs font-semibold text-gray-500">
        墙面实拍材质(材质C · 作参考图){busy ? ' · 上传中…' : ''}
      </p>
      <div className="grid grid-cols-2 gap-2">
        {(WALL_SIDES as ReadonlyArray<{ side: WallSide; zh: string }>).map(
          ({ side, zh }) => {
            const pid = walls?.[side]?.photo_id ?? '';
            const attached = pid
              ? photos.find((p) => p.id === pid)
              : undefined;
            return (
              <div
                key={side}
                className="flex flex-col gap-1 rounded-lg border border-gray-200 p-1.5 dark:border-white/10"
                data-testid={`wall-photo-${side}`}
              >
                <div className="flex items-center gap-1.5">
                  <span className="w-8 shrink-0 text-xs text-gray-500">
                    {zh}
                  </span>
                  <select
                    className="min-w-0 flex-1 rounded border border-gray-200 bg-white px-1 py-0.5 text-[11px] dark:border-white/10 dark:bg-navy-900 dark:text-white"
                    value={pid}
                    aria-label={`${zh}墙实拍材质`}
                    onChange={(e) => onSetWallPhoto(side, e.target.value)}
                  >
                    <option value="">无</option>
                    {photos.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.note || p.id.slice(0, 6)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-1.5">
                  {attached?.thumb_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={attached.thumb_url}
                      alt=""
                      className="h-7 w-7 shrink-0 rounded object-cover"
                    />
                  ) : (
                    <span className="h-7 w-7 shrink-0 rounded bg-gray-100 dark:bg-white/5" />
                  )}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      pendingSide.current = side;
                      fileRef.current?.click();
                    }}
                    className="rounded border border-gray-200 px-1.5 py-0.5 text-[11px] hover:bg-gray-50 disabled:opacity-50 dark:border-white/10 dark:hover:bg-white/5"
                  >
                    上传
                  </button>
                  {pid && (
                    <button
                      type="button"
                      onClick={() => onSetWallPhoto(side, '')}
                      className="text-[11px] text-gray-400 hover:text-red-500"
                    >
                      清除
                    </button>
                  )}
                </div>
              </div>
            );
          },
        )}
      </div>
      {err && <p className="mt-1 text-[11px] text-red-500">{err}</p>}
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          const side = pendingSide.current;
          if (f && side) onUpload(side, f);
          e.target.value = '';
        }}
      />
    </div>
  );
}
