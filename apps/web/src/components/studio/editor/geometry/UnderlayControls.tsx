'use client';

import React, { useRef, useState } from 'react';
import { uploadBaselinePhoto } from 'lib/studioApi';
import type { UnderlayMeta } from 'lib/floorplan/types';

// 底图描摹控件 (P6): 上传参考底图 (户型版本照片, purpose=underlay) -> 写 meta.underlay;
// 透明度滑杆; 「标定比例」进入两点采样; 「清除」删底图。只在户型编辑 (有 baselineVersionId)
// 出现。上传失败静默提示, 不阻断几何编辑。引擎不读 meta.underlay -> 出图字节不受影响。
export default function UnderlayControls({
  projectId,
  baselineVersionId,
  underlay,
  onSetUnderlay,
  onClearUnderlay,
  onStartCalibrate,
}: {
  projectId: string;
  baselineVersionId: string;
  underlay?: UnderlayMeta;
  onSetUnderlay: (patch: Partial<UnderlayMeta>) => void;
  onClearUnderlay: () => void;
  onStartCalibrate: () => void;
}) {
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onUpload = async (file: File) => {
    setBusy(true);
    setErr(null);
    try {
      const p = await uploadBaselinePhoto(projectId, baselineVersionId, file, {
        purpose: 'underlay',
      });
      onSetUnderlay({ url: p.url, photo_id: p.id });
    } catch (e) {
      setErr(e instanceof Error ? e.message : '上传失败');
    } finally {
      setBusy(false);
    }
  };

  const btn =
    'rounded border border-gray-200 px-2 py-0.5 text-[11px] hover:bg-gray-50 disabled:opacity-50 dark:border-white/10 dark:hover:bg-white/5';

  return (
    <div className="mt-2" data-testid="underlay-controls">
      <p className="text-xs font-semibold text-gray-500">
        底图描摹(参考底图){busy ? ' · 上传中…' : ''}
      </p>
      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          disabled={busy}
          className={btn}
          onClick={() => fileRef.current?.click()}
        >
          {underlay?.url ? '换底图' : '上传底图'}
        </button>
        {underlay?.url && (
          <>
            <button type="button" className={btn} onClick={onStartCalibrate}>
              标定比例
            </button>
            <button
              type="button"
              className={`${btn} text-red-500`}
              onClick={onClearUnderlay}
            >
              清除
            </button>
          </>
        )}
      </div>
      {underlay?.url && (
        <label className="mt-1.5 flex items-center gap-2 text-[11px] text-gray-500">
          透明度
          <input
            type="range"
            min={0.1}
            max={0.9}
            step={0.05}
            value={underlay.opacity}
            onChange={(e) =>
              onSetUnderlay({ opacity: parseFloat(e.target.value) })
            }
            className="flex-1"
            aria-label="底图透明度"
          />
        </label>
      )}
      {err && <p className="mt-1 text-[11px] text-red-500">{err}</p>}
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onUpload(f);
          e.target.value = '';
        }}
      />
    </div>
  );
}
