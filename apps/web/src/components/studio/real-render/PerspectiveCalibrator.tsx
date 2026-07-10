'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Modal from 'components/studio/ui/Modal';
import LoadingState from 'components/studio/ui/LoadingState';
import { Button } from 'components/studio/ui/buttons';
import { NoticeBanner, Badge } from 'components/studio/ui/status';
import { inputCls } from 'lib/floorplan/fieldStyles';
import {
  fetchBaselineGeometry,
  setPhotoCalibration,
  type BaselinePhoto,
  type CalibrationLine,
  type CalibrationPayload,
} from 'lib/studioApi';
import type { Room } from 'lib/floorplan/types';

// P2b 透视标定 UI: 用户在空房实拍照上标出「几何锁定」所需输入 —— 两组正交地面墙线 (求 2 个
// 消失点) + >=2 个已知地面墙角 (给绝对定位)。提交后后端反解相机, 实拍生成即走精准落位路径。
//
// 关键简化 (世界锚点不手算 mm): 取该照片房间 (photo.room_id) 的矩形四角, 按
// world_mm = 几何像素 × mm_per_px 换算成世界坐标 (与后端 footprint_mask 的投影完全同源),
// 用户只需「在照片上点一个位置 + 从下拉选它是哪个角」。

type Pt = [number, number]; // 照片原始像素坐标

type CornerKey = 'NW' | 'NE' | 'SW' | 'SE';

interface AnchorDraft {
  px: Pt;
  corner: CornerKey | '';
}

// 世界系 X=东(+)=右, Y=南(+)=下 (北在上)。房间 rect=[x,y,w,h] 几何像素。
const CORNER_ORDER: CornerKey[] = ['NW', 'NE', 'SE', 'SW'];
const CORNER_LABEL: Record<CornerKey, string> = {
  NW: '西北角(左上)',
  NE: '东北角(右上)',
  SE: '东南角(右下)',
  SW: '西南角(左下)',
};

// rect=[rx,ry,rw,rh] 几何像素 -> 某角的世界 mm [X,Y,0]。
function cornerWorldMm(
  rect: [number, number, number, number],
  corner: CornerKey,
  mmPerPx: number,
): [number, number, number] {
  const [rx, ry, rw, rh] = rect;
  const x = corner === 'NE' || corner === 'SE' ? rx + rw : rx;
  const y = corner === 'SW' || corner === 'SE' ? ry + rh : ry;
  return [Math.round(x * mmPerPx), Math.round(y * mmPerPx), 0];
}

type Phase = 'y' | 'x' | 'anchor';

export default function PerspectiveCalibrator({
  projectId,
  baselineId,
  photo,
  onClose,
  onCalibrated,
}: {
  projectId: string;
  baselineId: string;
  photo: BaselinePhoto;
  onClose: () => void;
  onCalibrated: (updated: BaselinePhoto) => void;
}) {
  // 房间矩形 (取世界锚点用) —— 与后端投影同源的 baseline 几何。
  const [room, setRoom] = useState<Room | null>(null);
  const [mmPerPx, setMmPerPx] = useState(10);
  const [geoState, setGeoState] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [geoError, setGeoError] = useState<string | null>(null);

  // 原始像素尺寸 (img_wh 与坐标换算基准)。
  const [natW, setNatW] = useState(0);
  const [natH, setNatH] = useState(0);

  // 标定输入草稿 (均存原始像素)。
  const [yLines, setYLines] = useState<CalibrationLine[]>([]);
  const [xLines, setXLines] = useState<CalibrationLine[]>([]);
  const [anchors, setAnchors] = useState<AnchorDraft[]>([]);
  const [pending, setPending] = useState<Pt | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const roomId = photo.room_id ?? '';

  useEffect(() => {
    let alive = true;
    setGeoState('loading');
    setGeoError(null);
    if (!roomId) {
      setGeoState('ready');
      return;
    }
    void fetchBaselineGeometry(projectId, baselineId)
      .then((geo) => {
        if (!alive) return;
        const rooms = (geo.rooms as Room[] | undefined) ?? [];
        const found = rooms.find((r) => r.id === roomId) ?? null;
        setRoom(found);
        setMmPerPx(Number(geo.meta?.mm_per_px) || 10);
        setGeoState('ready');
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setGeoError(e instanceof Error ? e.message : String(e));
        setGeoState('error');
      });
    return () => {
      alive = false;
    };
  }, [projectId, baselineId, roomId]);

  const phase: Phase = useMemo(
    () => (yLines.length < 2 ? 'y' : xLines.length < 2 ? 'x' : 'anchor'),
    [yLines.length, xLines.length],
  );

  // 已用掉的角 (禁止两锚点选同一角 -> 世界坐标退化)。
  const usedCorners = useMemo(
    () => new Set(anchors.map((a) => a.corner).filter(Boolean)),
    [anchors],
  );

  const addAnchor = useCallback(
    (px: Pt) => {
      const next =
        CORNER_ORDER.find((c) => !usedCorners.has(c)) ?? ('' as const);
      setAnchors((prev) => [...prev, { px, corner: next }]);
    },
    [usedCorners],
  );

  // 点选层坐标 -> 原始像素 (按覆盖层实际显示尺寸等比换算)。
  const onPickPoint = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (natW === 0 || natH === 0) return;
      const rect = e.currentTarget.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      const fx = (e.clientX - rect.left) / rect.width;
      const fy = (e.clientY - rect.top) / rect.height;
      const px: Pt = [
        Math.round(Math.min(Math.max(fx, 0), 1) * natW),
        Math.round(Math.min(Math.max(fy, 0), 1) * natH),
      ];
      if (phase === 'anchor') {
        addAnchor(px);
        return;
      }
      if (pending === null) {
        setPending(px);
        return;
      }
      const line: CalibrationLine = [pending, px];
      if (phase === 'y') setYLines((prev) => [...prev, line]);
      else setXLines((prev) => [...prev, line]);
      setPending(null);
    },
    [natW, natH, phase, pending, addAnchor],
  );

  const undo = useCallback(() => {
    setSubmitError(null);
    if (pending !== null) {
      setPending(null);
      return;
    }
    if (anchors.length > 0) {
      setAnchors((prev) => prev.slice(0, -1));
      return;
    }
    if (xLines.length > 0) {
      setXLines((prev) => prev.slice(0, -1));
      return;
    }
    if (yLines.length > 0) {
      setYLines((prev) => prev.slice(0, -1));
    }
  }, [pending, anchors.length, xLines.length, yLines.length]);

  const resetAll = useCallback(() => {
    setSubmitError(null);
    setPending(null);
    setAnchors([]);
    setXLines([]);
    setYLines([]);
  }, []);

  const setAnchorCorner = useCallback((idx: number, corner: CornerKey | '') => {
    setSubmitError(null);
    setAnchors((prev) =>
      prev.map((a, i) => (i === idx ? { ...a, corner } : a)),
    );
  }, []);

  const anchorsReady =
    anchors.length >= 2 &&
    anchors.every((a) => a.corner !== '') &&
    new Set(anchors.map((a) => a.corner)).size === anchors.length;

  const canSubmit =
    !!room &&
    natW > 0 &&
    natH > 0 &&
    yLines.length >= 2 &&
    xLines.length >= 2 &&
    anchorsReady &&
    !submitting;

  const onSubmit = useCallback(async () => {
    if (!room) return;
    const payload: CalibrationPayload = {
      x_lines: xLines,
      y_lines: yLines,
      anchors: anchors
        .filter((a): a is { px: Pt; corner: CornerKey } => a.corner !== '')
        .map((a) => ({
          world: cornerWorldMm(room.rect, a.corner, mmPerPx),
          px: a.px,
        })),
      img_wh: [natW, natH],
    };
    setSubmitting(true);
    setSubmitError(null);
    try {
      const updated = await setPhotoCalibration(
        projectId,
        baselineId,
        photo.id,
        payload,
      );
      onCalibrated(updated);
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }, [
    room,
    xLines,
    yLines,
    anchors,
    mmPerPx,
    natW,
    natH,
    projectId,
    baselineId,
    photo.id,
    onCalibrated,
  ]);

  // ---- 覆盖层渲染坐标 (原始像素 -> 百分比, 与图片等比、抗缩放) ---- //
  const pctX = (x: number) => (natW ? `${(x / natW) * 100}%` : '0%');
  const pctY = (y: number) => (natH ? `${(y / natH) * 100}%` : '0%');

  const stepHint: Record<Phase, string> = {
    y: '第 1 步 / 共 3 步 · 标东墙(电视墙)两条水平边:每条点 2 个端点(共 4 点 → 2 条线)',
    x: '第 2 步 / 共 3 步 · 标南墙/落地窗两条水平边:每条点 2 个端点(共 4 点 → 2 条线)',
    anchor:
      '第 3 步 / 共 3 步 · 点选 ≥2 个地面墙角,并在右侧下拉里选它是哪个角(不能选同一个角)',
  };

  const roomMissing = !roomId;

  return (
    <Modal
      open
      onClose={onClose}
      title="透视标定 · 启用几何锁定精准落位"
      maxWidthClass="max-w-4xl"
    >
      <div className="max-h-[82vh] space-y-4 overflow-y-auto">
        {roomMissing ? (
          <NoticeBanner tone="warn">
            该照片尚未标注房间,无法取房间墙角作为世界锚点。请先到户型基线页为照片标注房间,再回来标定。
          </NoticeBanner>
        ) : geoState === 'loading' ? (
          <LoadingState rows={2} />
        ) : geoState === 'error' ? (
          <NoticeBanner tone="error" title="无法加载房间几何(后端可能未启动)。">
            {geoError}
          </NoticeBanner>
        ) : !room ? (
          <NoticeBanner tone="warn">
            未在当前户型版本几何里找到房间「{roomId}」——
            该房间可能已被改名或删除。请回基线页重新标注照片房间。
          </NoticeBanner>
        ) : (
          <>
            <div className="dark:border-brand-400/30 rounded-xl border border-brand-200 bg-brand-50 p-3 text-sm text-brand-700 dark:bg-navy-900 dark:text-brand-300">
              {stepHint[phase]}
              {pending && (
                <span className="ml-1 font-medium">
                  · 已点第 1 端点,请点第 2 端点。
                </span>
              )}
            </div>

            {/* 照片 + 点选覆盖层 */}
            <div className="relative inline-block w-full select-none">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={photo.url}
                alt="空房实拍照"
                onLoad={(e) => {
                  setNatW(e.currentTarget.naturalWidth);
                  setNatH(e.currentTarget.naturalHeight);
                }}
                className="block w-full rounded-lg bg-gray-100 dark:bg-navy-900"
                draggable={false}
              />
              {/* 点选层: 捕获点击换算为原始像素 */}
              <div
                role="presentation"
                onClick={onPickPoint}
                className="absolute inset-0 cursor-crosshair"
              >
                {/* 线: SVG viewBox=原始像素, 非缩放描边 */}
                {natW > 0 && natH > 0 && (
                  <svg
                    viewBox={`0 0 ${natW} ${natH}`}
                    preserveAspectRatio="none"
                    className="pointer-events-none absolute inset-0 h-full w-full"
                  >
                    {yLines.map((ln, i) => (
                      <line
                        key={`y${i}`}
                        x1={ln[0][0]}
                        y1={ln[0][1]}
                        x2={ln[1][0]}
                        y2={ln[1][1]}
                        className="text-emerald-500"
                        stroke="currentColor"
                        strokeWidth={2}
                        vectorEffect="non-scaling-stroke"
                      />
                    ))}
                    {xLines.map((ln, i) => (
                      <line
                        key={`x${i}`}
                        x1={ln[0][0]}
                        y1={ln[0][1]}
                        x2={ln[1][0]}
                        y2={ln[1][1]}
                        className="text-brand-500"
                        stroke="currentColor"
                        strokeWidth={2}
                        vectorEffect="non-scaling-stroke"
                      />
                    ))}
                  </svg>
                )}
                {/* 端点/锚点标记 (HTML, 恒定屏幕尺寸) */}
                {[...yLines, ...xLines].flat().map((pt, i) => (
                  <span
                    key={`p${i}`}
                    className="pointer-events-none absolute h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow ring-2 ring-navy-700"
                    style={{ left: pctX(pt[0]), top: pctY(pt[1]) }}
                  />
                ))}
                {pending && (
                  <span
                    className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-amber-400 shadow ring-2 ring-white"
                    style={{ left: pctX(pending[0]), top: pctY(pending[1]) }}
                  />
                )}
                {anchors.map((a, i) => (
                  <span
                    key={`a${i}`}
                    className="pointer-events-none absolute flex h-5 w-5 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-brand-500 text-[10px] font-bold text-white shadow ring-2 ring-white"
                    style={{ left: pctX(a.px[0]), top: pctY(a.px[1]) }}
                  >
                    {i + 1}
                  </span>
                ))}
              </div>
            </div>

            {/* 进度徽章 */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge tone={yLines.length >= 2 ? 'green' : 'amber'} size="xs">
                东墙线 {yLines.length}/2
              </Badge>
              <Badge tone={xLines.length >= 2 ? 'green' : 'amber'} size="xs">
                南墙线 {xLines.length}/2
              </Badge>
              <Badge tone={anchorsReady ? 'green' : 'amber'} size="xs">
                地面角 {anchors.length}(需 ≥2 且各不相同)
              </Badge>
            </div>

            {/* 锚点角选择 */}
            {anchors.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
                  为每个地面角选择它对应房间「{room.label?.zh || room.id}
                  」的哪个角:
                </p>
                {anchors.map((a, i) => {
                  const dup =
                    a.corner !== '' &&
                    anchors.some((b, j) => j !== i && b.corner === a.corner);
                  return (
                    <div key={`ac${i}`} className="flex items-center gap-2">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-500 text-[10px] font-bold text-white">
                        {i + 1}
                      </span>
                      <span className="text-xs text-gray-400">
                        ({a.px[0]}, {a.px[1]})
                      </span>
                      <select
                        aria-label={`地面角 ${i + 1} 对应房间角`}
                        className={`${inputCls} max-w-[13rem] ${
                          dup ? 'border-red-400 dark:border-red-500' : ''
                        }`}
                        value={a.corner}
                        onChange={(e) =>
                          setAnchorCorner(i, e.target.value as CornerKey | '')
                        }
                      >
                        <option value="">选择角…</option>
                        {CORNER_ORDER.map((c) => (
                          <option key={c} value={c}>
                            {CORNER_LABEL[c]}
                          </option>
                        ))}
                      </select>
                      {dup && (
                        <span className="text-xs text-red-500">重复角</span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {submitError && (
              <NoticeBanner tone="error" title="标定失败">
                {submitError}
              </NoticeBanner>
            )}

            {/* 操作 */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-gray-200 pt-3 dark:border-white/10">
              <div className="flex items-center gap-2">
                <Button
                  variant="neutral-outline"
                  onClick={undo}
                  disabled={
                    pending === null &&
                    anchors.length === 0 &&
                    xLines.length === 0 &&
                    yLines.length === 0
                  }
                >
                  撤销
                </Button>
                <Button variant="neutral-outline" onClick={resetAll}>
                  重来
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="secondary" onClick={onClose}>
                  取消
                </Button>
                <Button
                  variant="primary"
                  onClick={() => void onSubmit()}
                  disabled={!canSubmit}
                  title={
                    canSubmit
                      ? '提交标定并反解相机'
                      : '需 2 条东墙线 + 2 条南墙线 + ≥2 个各不相同的地面角'
                  }
                >
                  {submitting ? '提交中…' : '提交标定'}
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
