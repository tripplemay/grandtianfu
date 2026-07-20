'use client';

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import Modal from 'components/studio/ui/Modal';
import LoadingState from 'components/studio/ui/LoadingState';
import { Button } from 'components/studio/ui/buttons';
import { NoticeBanner, Badge } from 'components/studio/ui/status';
import { inputCls } from 'lib/floorplan/fieldStyles';
import {
  CalibrationPreviewPanel,
  CalibrationWireframeOverlay,
} from 'components/studio/real-render/CalibrationPreview';
import FeaturePointCalibrator from 'components/studio/real-render/FeaturePointCalibrator';
import CalibrationMiniMap from 'components/studio/real-render/CalibrationMiniMap';
import {
  fetchBaselineGeometry,
  previewPhotoCalibration,
  setPhotoCalibration,
  type BaselinePhoto,
  type CalibrationFeature,
  type CalibrationLine,
  type CalibrationPayload,
  type CalibrationPreviewResult,
} from 'lib/studioApi';
import type { Room } from 'lib/floorplan/types';

// P2b 透视标定 UI: 用户在空房实拍照上标出「几何锁定」所需输入 —— 两组正交地面墙线 (求 2 个
// 消失点) + >=2 个已知地面墙角 (给绝对定位)。提交后后端反解相机, 实拍生成即走精准落位路径。
//
// 关键简化 (世界锚点不手算 mm): 取该照片房间 (photo.room_id) 的矩形四角, 按
// world_mm = 几何像素 × mm_per_px 换算成世界坐标 (与后端 footprint_mask 的投影完全同源),
// 用户只需「在照片上点一个位置 + 从下拉选它是哪个角」。
//
// calib-cure-b1 F009: 本组件升格为模式路由 —— 「特征点(默认)」走 FeaturePointCalibrator
// (点选对齐, ≥4 点自动解算预览), 「专家(线+角)」保留本文件既有 F002 两步提交流程 (行为
// 不变)。两模式共用 F002 的预览确认门 (CalibrationPreview 展示件 + quality.ok 语义)。

type Pt = [number, number]; // 照片原始像素坐标

type CornerKey = 'NW' | 'NE' | 'SW' | 'SE';

interface AnchorDraft {
  px: Pt;
  corner: CornerKey | '';
}

// 世界系 X=东(+)=右, Y=南(+)=下 (北在上)。房间 rect=[x,y,w,h] 几何像素。
// F010: 角标不再带 "(左上)" 类平面图视角注释 —— 在照片点击 UI 下极易被读成照片方位
// (缺陷 A9); 方位对照改由平面小窗的角点高亮承担 (所见即所指)。
const CORNER_ORDER: CornerKey[] = ['NW', 'NE', 'SE', 'SW'];
const CORNER_LABEL: Record<CornerKey, string> = {
  NW: '西北角',
  NE: '东北角',
  SE: '东南角',
  SW: '西南角',
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
  // F009 模式路由: 特征点(默认, 点选对齐) / 专家(线+角, 以下 F002 流程逐字保留)。
  // 专家态 hooks 常驻本组件 —— 切到特征点再切回, 专家输入不丢。
  const [mode, setMode] = useState<'features' | 'expert'>('features');

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

  // F002 两步提交: 先 dry-run 预览 (线框叠照片 + 误差评级), 确认后才真保存。
  // preview 非空 = 当前输入的有效预览; 任何输入变更都必须失效它 (见 invalidatePreview)。
  const [preview, setPreview] = useState<CalibrationPreviewResult | null>(null);
  const [previewing, setPreviewing] = useState(false);

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

  // F002: 任何标定输入变更 (加线/加锚点/改角标/撤销/重来) -> 已出预览作废,
  // 须重新预览才能确认保存 (线框/评级基于旧输入, 留着会误导确认)。
  // inputEpoch 防竞态: 预览请求飞行中输入又变了 -> 返回的旧结果必须丢弃,
  // 否则旧预览会把确认门错误打开。
  const inputEpoch = useRef(0);
  const invalidatePreview = useCallback(() => {
    inputEpoch.current += 1;
    setPreview(null);
  }, []);

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
      invalidatePreview();
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
    [natW, natH, phase, pending, addAnchor, invalidatePreview],
  );

  const undo = useCallback(() => {
    setSubmitError(null);
    invalidatePreview();
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
  }, [
    pending,
    anchors.length,
    xLines.length,
    yLines.length,
    invalidatePreview,
  ]);

  const resetAll = useCallback(() => {
    setSubmitError(null);
    invalidatePreview();
    setPending(null);
    setAnchors([]);
    setXLines([]);
    setYLines([]);
  }, [invalidatePreview]);

  const setAnchorCorner = useCallback(
    (idx: number, corner: CornerKey | '') => {
      setSubmitError(null);
      invalidatePreview();
      setAnchors((prev) =>
        prev.map((a, i) => (i === idx ? { ...a, corner } : a)),
      );
    },
    [invalidatePreview],
  );

  // F002: 收紧为 >=3 个各不相同角 (后端 F004 即将对新保存强制 >=3, 前端先行一致;
  // n=2 时第三行约束缺失, 病例库三例坏标定全部源于此)。
  const anchorsReady =
    anchors.length >= 3 &&
    anchors.every((a) => a.corner !== '') &&
    new Set(anchors.map((a) => a.corner)).size === anchors.length;

  const inputsReady =
    !!room &&
    natW > 0 &&
    natH > 0 &&
    yLines.length >= 2 &&
    xLines.length >= 2 &&
    anchorsReady;

  const canPreview = inputsReady && !previewing && !submitting;
  // 确认门: 必须有当前输入的有效预览, 且质量非 bad (后端 400 BAD_CALIBRATION 兜底,
  // 前端不做后端没有的放行)。
  const canConfirm =
    inputsReady &&
    preview !== null &&
    preview.quality.ok &&
    !previewing &&
    !submitting;

  const buildPayload = useCallback((): CalibrationPayload | null => {
    if (!room) return null;
    return {
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
  }, [room, xLines, yLines, anchors, mmPerPx, natW, natH]);

  // 第一步: dry-run 预览 —— 只解算不落盘, 拿线框/误差/评级叠回照片供核对。
  const onPreview = useCallback(async () => {
    const payload = buildPayload();
    if (!payload) return;
    const epoch = inputEpoch.current;
    setPreviewing(true);
    setSubmitError(null);
    try {
      const result = await previewPhotoCalibration(
        projectId,
        baselineId,
        photo.id,
        payload,
      );
      // 飞行期间输入未变才采纳; 变了则结果对应旧输入, 丢弃 (须重新预览)。
      if (inputEpoch.current === epoch) setPreview(result);
    } catch (e) {
      if (inputEpoch.current === epoch) {
        setPreview(null);
        setSubmitError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setPreviewing(false);
    }
  }, [buildPayload, projectId, baselineId, photo.id]);

  // 第二步: 确认保存 —— 预览通过后才真提交。若后端仍 400 (BAD_CALIBRATION 等),
  // unwrap 抛的 error 文案已含 reasons, 原样进 submitError banner。
  const onConfirm = useCallback(async () => {
    if (preview === null) return;
    const payload = buildPayload();
    if (!payload) return;
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
  }, [preview, buildPayload, projectId, baselineId, photo.id, onCalibrated]);

  // ---- 覆盖层渲染坐标 (原始像素 -> 百分比, 与图片等比、抗缩放) ---- //
  const pctX = (x: number) => (natW ? `${(x / natW) * 100}%` : '0%');
  const pctY = (y: number) => (natH ? `${(y / natH) * 100}%` : '0%');

  // F010: 文案按方向语义写, 不再假设"东墙=电视墙/南墙=落地窗" (那只对客厅成立, 对书房等
  // 房间是系统性误导 —— 798 病灶; 用户 2026-07-17 复报的 A3 缺陷闭环)。当前步该画哪个走向
  // 的墙由右侧平面小窗高亮直接指出。
  const stepHint: Record<Phase, string> = {
    y: '第 1 步 / 共 3 步 · 标两条沿【南北】走向墙体(如东墙/西墙)的水平上下沿:每条点 2 个端点。小窗中已高亮该走向的墙。',
    x: '第 2 步 / 共 3 步 · 标两条沿【东西】走向墙体(如南墙/北墙)的水平上下沿:每条点 2 个端点。小窗中已高亮该走向的墙。',
    anchor:
      '第 3 步 / 共 3 步 · 点选 ≥3 个地面墙角,并为每个选择对应的角 —— 小窗会高亮角的实际方位,不必心算罗盘。',
  };

  // F010: 房间四角作伪特征点进平面小窗 —— 角标下拉的视觉对照 (替代 "(左上)" 字面)。
  const cornerFeatures = useMemo<CalibrationFeature[]>(() => {
    if (!room) return [];
    return CORNER_ORDER.map((c) => ({
      id: c,
      world: cornerWorldMm(room.rect, c, mmPerPx),
      label_zh: CORNER_LABEL[c],
      kind: 'wall_corner' as const,
      // F003 分级字段: 伪特征点恒为结构角 (专家模式只用房间四角, 无窗特征存疑问题)。
      tier: 'structural' as const,
      priority: 0,
      optional: false,
      caveat_zh: null,
    }));
  }, [room, mmPerPx]);
  const nextCorner =
    phase === 'anchor'
      ? CORNER_ORDER.find((c) => !usedCorners.has(c)) ?? null
      : null;

  const roomMissing = !roomId;

  return (
    <Modal
      open
      onClose={onClose}
      title="透视标定 · 启用几何锁定精准落位"
      maxWidthClass="max-w-4xl"
    >
      <div className="max-h-[82vh] space-y-4 overflow-y-auto">
        {/* F009 模式切换: 特征点(默认) / 专家(线+角) */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
            标定方式
          </span>
          <Button
            size="sm"
            variant={mode === 'features' ? 'primary' : 'neutral-outline'}
            onClick={() => setMode('features')}
            ariaPressed={mode === 'features'}
            dataTestId="calib-mode-features"
          >
            特征点(默认)
          </Button>
          <Button
            size="sm"
            variant={mode === 'expert' ? 'primary' : 'neutral-outline'}
            onClick={() => setMode('expert')}
            ariaPressed={mode === 'expert'}
            dataTestId="calib-mode-expert"
          >
            专家(线+角·高级)
          </Button>
        </div>
        {/* F007: 专家(线+角)模式数学上对手画线误差病态敏感(轻微手抖即撞质量门), 降级为高级选项 +
            明确警告; 既有两步提交流程逐字保留(可回退)。默认与推荐一律用特征点模式。 */}
        {mode === 'expert' && (
          <NoticeBanner tone="warn" title="专家模式（不推荐，仅高级用户）">
            手画墙线法靠两组线的消失点反解焦距,对画线精度
            <span className="font-semibold">病态敏感</span>
            ——轻微手抖就可能让解算相机"歪掉"而撞质量门。除非你清楚在做什么,
            建议改用上方「特征点(默认)」:从平面图选点、在照片上点对应位置,更稳。
          </NoticeBanner>
        )}
        {roomMissing ? (
          <NoticeBanner tone="warn">
            该照片尚未标注房间,无法取房间墙角作为世界锚点。请先到户型基线页为照片标注房间,再回来标定。
          </NoticeBanner>
        ) : mode === 'features' ? (
          <FeaturePointCalibrator
            projectId={projectId}
            baselineId={baselineId}
            photo={photo}
            onClose={onClose}
            onCalibrated={onCalibrated}
          />
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
            <div className="flex flex-wrap items-stretch gap-3">
              <div className="dark:border-brand-400/30 min-w-[16rem] flex-1 rounded-xl border border-brand-200 bg-brand-50 p-3 text-sm text-brand-700 dark:bg-navy-900 dark:text-brand-300">
                {stepHint[phase]}
                {pending && (
                  <span className="ml-1 font-medium">
                    · 已点第 1 端点,请点第 2 端点。
                  </span>
                )}
              </div>
              {/* F010: 平面小窗 —— 高亮当前步的墙走向 / 待选角点 (A3/A9 缺陷闭环) */}
              <CalibrationMiniMap
                rooms={[
                  { id: room.id, rect: room.rect, labelZh: room.label?.zh },
                ]}
                mmPerPx={mmPerPx}
                features={cornerFeatures}
                placedIds={[...usedCorners] as string[]}
                activeId={nextCorner}
                highlightAxis={
                  phase === 'y' ? 'ns' : phase === 'x' ? 'ew' : undefined
                }
                className="w-40 shrink-0 self-center"
              />
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
                    {/* F002 预览线框 (紫红虚线): dry-run 推算的房间轮廓, 与输入线层共存 */}
                    {preview && (
                      <CalibrationWireframeOverlay
                        wireframe={preview.wireframe}
                      />
                    )}
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
                南北向墙线 {yLines.length}/2
              </Badge>
              <Badge tone={xLines.length >= 2 ? 'green' : 'amber'} size="xs">
                东西向墙线 {xLines.length}/2
              </Badge>
              <Badge tone={anchorsReady ? 'green' : 'amber'} size="xs">
                地面角 {anchors.length}(需 ≥3 且各不相同)
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

            {/* F002 预览结果: 误差数值 + 评级徽章 + reasons (子组件, F009 复用同一确认门) */}
            {preview && <CalibrationPreviewPanel preview={preview} />}

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
                {/* F002 两步提交: 预览 (dry-run, 不保存) -> 确认保存 */}
                <Button
                  variant={preview ? 'neutral-outline' : 'primary'}
                  onClick={() => void onPreview()}
                  disabled={!canPreview}
                  title={
                    canPreview
                      ? '按当前输入反解相机并预览线框(不保存)'
                      : '需 2 条南北向墙线 + 2 条东西向墙线 + ≥3 个各不相同的地面角'
                  }
                >
                  {previewing ? '预览中…' : preview ? '重新预览' : '预览标定'}
                </Button>
                <Button
                  variant="primary"
                  onClick={() => void onConfirm()}
                  disabled={!canConfirm}
                  title={
                    preview === null
                      ? '请先预览标定,核对线框与误差后再保存'
                      : !preview.quality.ok
                      ? '标定质量不合格,请按上方原因修正输入后重新预览'
                      : '保存标定并启用几何锁定精准落位'
                  }
                >
                  {submitting ? '保存中…' : '确认保存'}
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
