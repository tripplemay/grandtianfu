'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { MdPhotoCamera, MdUpload } from 'react-icons/md';
import RenderImage from 'components/studio/ui/RenderImage';
import { Button } from 'components/studio/ui/buttons';
import { StudioCard, TimeAgo, Hairline } from 'components/studio/ui/primitives';
import { useToastContext } from 'components/studio/ui/ToastHost';
import { useConfirm } from 'components/studio/ui/ConfirmDialog';
import {
  deleteBaselinePhoto,
  fetchBaselineGeometry,
  listBaselinePhotos,
  patchBaselinePhoto,
  uploadBaselinePhoto,
  type BaselinePhoto,
} from 'lib/studioApi';

// 第6步: 空房实拍照管理 (绑定户型版本, 不绑定方案 — 规格 §8.3)。
// 上传 / 房间与拍摄方向标注 / 备注 / 删除(二次确认, 历史成果不受影响)。
// 照片供第7步 (空房照 + 轴测参考 → 实拍效果图) 使用。

const DIRECTIONS = ['N', 'S', 'E', 'W'] as const;

interface RoomOption {
  id: string;
  name: string;
}

export default function BaselinePhotosCard({
  projectId,
  versionId,
  readOnly = false,
}: {
  projectId: string;
  versionId: string;
  readOnly?: boolean;
}) {
  const { showToast } = useToastContext();
  const confirm = useConfirm();
  const fileRef = useRef<HTMLInputElement | null>(null);

  const [photos, setPhotos] = useState<BaselinePhoto[]>([]);
  const [rooms, setRooms] = useState<RoomOption[]>([]);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      const list = await listBaselinePhotos(projectId, versionId);
      setPhotos(list);
      setError(null);
      setLoadState('ready');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLoadState('error');
    }
  }, [projectId, versionId]);

  useEffect(() => {
    setLoadState('loading');
    void reload();
  }, [reload]);

  // 房间选项 (标注用): 取该版本几何的非公共区房间。失败不阻断照片功能。
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const G = await fetchBaselineGeometry(projectId, versionId);
        if (!alive) return;
        const raw = (G as { rooms?: unknown }).rooms;
        const opts = (Array.isArray(raw) ? raw : [])
          .filter((r: any) => r?.id && r?.type !== 'public')
          .map((r: any) => ({
            id: String(r.id),
            name: r?.label?.zh || String(r.id),
          }));
        setRooms(opts);
      } catch {
        if (alive) setRooms([]);
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId, versionId]);

  const onUpload = useCallback(
    async (file: File) => {
      setBusy(true);
      try {
        await uploadBaselinePhoto(projectId, versionId, file);
        showToast('照片已上传', 'success');
        await reload();
      } catch (e) {
        showToast(
          `上传失败:${e instanceof Error ? e.message : String(e)}`,
          'error',
        );
      } finally {
        setBusy(false);
        if (fileRef.current) fileRef.current.value = '';
      }
    },
    [projectId, versionId, showToast, reload],
  );

  const onAnnotate = useCallback(
    async (
      photo: BaselinePhoto,
      fields: {
        room_id?: string | null;
        direction?: string | null;
        note?: string | null;
      },
    ) => {
      // 乐观更新: 本地先改, 失败回滚重载。
      setPhotos((prev) =>
        prev.map((p) => (p.id === photo.id ? { ...p, ...fields } : p)),
      );
      try {
        await patchBaselinePhoto(projectId, versionId, photo.id, fields);
      } catch (e) {
        showToast(
          `标注失败:${e instanceof Error ? e.message : String(e)}`,
          'error',
        );
        await reload();
      }
    },
    [projectId, versionId, showToast, reload],
  );

  const onDelete = useCallback(
    async (photo: BaselinePhoto) => {
      const ok = await confirm({
        title: '删除这张空房照片？',
        message:
          '仅移除照片引用；已用它生成的历史效果图不会被删除。原图文件保留,可随时重新上传。',
        confirmText: '删除照片',
        danger: true,
      });
      if (!ok) return;
      try {
        await deleteBaselinePhoto(projectId, versionId, photo.id);
        showToast('照片已删除', 'success');
        await reload();
      } catch (e) {
        showToast(
          `删除失败:${e instanceof Error ? e.message : String(e)}`,
          'error',
        );
      }
    },
    [projectId, versionId, confirm, showToast, reload],
  );

  const selectCls =
    'rounded-lg border border-gray-200 bg-white px-2 py-1 text-xs text-navy-700 outline-none focus:border-brand-500 dark:border-white/10 dark:bg-navy-900 dark:text-white';

  return (
    <StudioCard>
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <MdPhotoCamera className="h-5 w-5 text-brand-500" />
          <h2 className="text-base font-bold text-navy-700 dark:text-white">
            空房照片
          </h2>
        </div>
        {!readOnly && (
          <>
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void onUpload(f);
              }}
            />
            <Button
              variant="primary"
              size="sm"
              disabled={busy}
              onClick={() => fileRef.current?.click()}
            >
              <MdUpload className="h-4 w-4" />
              {busy ? '上传中…' : '上传照片'}
            </Button>
          </>
        )}
      </div>

      {loadState === 'error' && (
        <p className="text-sm text-red-500">照片加载失败:{error}</p>
      )}
      {loadState === 'ready' && photos.length === 0 && (
        <p className="text-sm text-gray-500">
          {readOnly
            ? '该户型版本没有空房照片。'
            : '上传空房实拍照,标注房间与拍摄方向,即可用于生成实拍效果图(第7步)。'}
        </p>
      )}

      {photos.length > 0 && (
        <ul className="space-y-3">
          {photos.map((photo) => (
            <li key={photo.id} className="flex gap-3">
              <div className="w-28 shrink-0 overflow-hidden rounded-lg bg-gray-50 dark:bg-navy-900">
                <RenderImage
                  src={photo.thumb_url ?? photo.url}
                  alt={photo.note || '空房照片'}
                  className="h-20"
                  imgClassName="h-20 w-full object-cover"
                  fallbackLabel="照片加载失败"
                />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={photo.room_id ?? ''}
                    disabled={readOnly}
                    onChange={(e) =>
                      void onAnnotate(photo, {
                        room_id: e.target.value || null,
                      })
                    }
                    className={selectCls}
                    aria-label="标注房间"
                  >
                    <option value="">未标注房间</option>
                    {rooms.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name}
                      </option>
                    ))}
                  </select>
                  <select
                    value={photo.direction ?? ''}
                    disabled={readOnly}
                    onChange={(e) =>
                      void onAnnotate(photo, {
                        direction: e.target.value || null,
                      })
                    }
                    className={selectCls}
                    aria-label="拍摄方向"
                  >
                    <option value="">方向</option>
                    {DIRECTIONS.map((d) => (
                      <option key={d} value={d}>
                        朝{{ N: '北', S: '南', E: '东', W: '西' }[d]}
                      </option>
                    ))}
                  </select>
                  {!readOnly && (
                    <Button
                      variant="danger-soft"
                      size="sm"
                      onClick={() => void onDelete(photo)}
                    >
                      删除
                    </Button>
                  )}
                </div>
                <input
                  defaultValue={photo.note ?? ''}
                  disabled={readOnly}
                  placeholder="备注(可选),回车保存"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      // 只触发 blur, 由 onBlur 统一提交一次 (避免 Enter+blur 双 PATCH)。
                      e.currentTarget.blur();
                    }
                  }}
                  onBlur={(e) => {
                    if ((e.target.value || null) !== (photo.note ?? null)) {
                      void onAnnotate(photo, { note: e.target.value || null });
                    }
                  }}
                  className="mt-2 w-full rounded-lg border border-gray-200 px-2 py-1 text-xs text-navy-700 outline-none focus:border-brand-500 dark:border-white/10 dark:bg-navy-900 dark:text-white"
                />
                <div className="mt-1">
                  <TimeAgo at={photo.created_at} prefix="上传" />
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Hairline className="my-3" />
      <p className="text-xs text-gray-400">
        上传即确认已获得业主授权;照片仅用于本项目效果图生成,可随时删除。
      </p>
    </StudioCard>
  );
}
