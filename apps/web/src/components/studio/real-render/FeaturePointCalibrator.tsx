'use client';

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import LoadingState from 'components/studio/ui/LoadingState';
import { Button } from 'components/studio/ui/buttons';
import { NoticeBanner, Badge } from 'components/studio/ui/status';
import {
  CalibrationPreviewPanel,
  CalibrationWireframeOverlay,
} from 'components/studio/real-render/CalibrationPreview';
import CalibrationMiniMap, {
  type CalibrationMiniMapRoom,
} from 'components/studio/real-render/CalibrationMiniMap';
import {
  fetchBaselineGeometry,
  getCalibrationFeatures,
  previewPhotoCalibration,
  setPhotoCalibration,
  type BaselinePhoto,
  type CalibrationFeature,
  type CalibrationPoint,
  type CalibrationPreviewResult,
  type PointsCalibrationPayload,
} from 'lib/studioApi';
import type { Room } from 'lib/floorplan/types';
// F004 修复(verifying-1): 轮候排序/孪生定位抽到纯模块, 由 scripts/check/feature-queue-order.ts
// 直接执行守门 —— 前端无单测 runner, 这是唯一能钉住"孪生提示不可达"回归的形态。
import {
  isElevated,
  orderFeatureQueue,
  planId,
} from 'lib/calibration/featureQueue';

// calib-cure-b1 F009: 特征点对齐标定 (spec §4 路线一的 UI 面)。范式: 点从平面几何派生、
// 自带世界坐标 (getCalibrationFeatures), 用户只做「在照片上点击它在哪」这一件视觉任务 ——
// 专家模式的罗盘角标/方向线分组心算全部消失, 对应关系由构造保证正确。
//
// 交互状态机: 队列 (后端 id 序) 依次呈现候选特征 -> 照片点击放置当前特征 (或跳过轮到
// 下一个) -> 已放 ≥4 自动 dry-run(points) 解算 -> 放/撤/重来使预览失效并自动重预览
// (epoch 守卫丢弃过期返回, 同 F002) -> 复用 F002 预览确认门 (线框叠照片 + 误差评级,
// quality.ok 才可确认保存)。
//
// V1 边界 (acceptance 钉死): 点击放置 + 逐点撤销/跳过; 不做拖拽持续重解/磁吸。

type Pt = [number, number]; // 照片原始像素坐标

interface PlacedPoint {
  featureId: string;
  px: Pt;
}

const KIND_LABEL: Record<CalibrationFeature['kind'], string> = {
  wall_corner: '墙角',
  door_jamb: '门框×地面',
  window_floor: '落地窗框×地面',
  ceiling_corner: '天花板转角',
  door_head: '门框顶',
  window_head: '落地窗框顶',
};

// calib-cure-b3 F004: 拍摄视角 v0..v3 -> 镜头大致朝向 (展示用)。与后端 _VIEW_FORWARDS
// (main.py, b1 F010 实证: 轴测"从近角看向里角" + _VIEW_TURNS 旋转) 同源: v0=(-1,-1)=西北,
// v1=(-1,1)=西南, v2=(1,1)=东南, v3=(1,-1)=东北 (世界系 X=东+, Y=南+)。
// **粒度诚实**: 后端只用它拦"近乎相反(>135°)"的整组镜像粗差, 相邻象限一律不拦 (D7 宁可
// 不拦不可误拦)。故此处只作朝向锚定文案, 不据此推算画面位置。
const VIEW_FACING: Record<string, string> = {
  v0: '西北',
  v1: '西南',
  v2: '东南',
  v3: '东北',
};

const MIN_POINTS = 4;

export default function FeaturePointCalibrator({
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
  // 特征池 + 平面小窗数据 (features 端点 + baseline 几何并行取, 后者给成员 rect 轮廓)。
  const [features, setFeatures] = useState<CalibrationFeature[]>([]);
  const [rooms, setRooms] = useState<CalibrationMiniMapRoom[]>([]);
  const [mmPerPx, setMmPerPx] = useState(10);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // 原始像素尺寸 (img_wh 与坐标换算基准, 同专家模式)。
  const [natW, setNatW] = useState(0);
  const [natH, setNatH] = useState(0);

  // 放置状态: placed 顺序 = 点击顺序 (照片标 1..n 序号); skipped 仅影响轮候不进 payload。
  const [placed, setPlaced] = useState<PlacedPoint[]>([]);
  const [skippedIds, setSkippedIds] = useState<string[]>([]);

  const [preview, setPreview] = useState<CalibrationPreviewResult | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoadState('loading');
    setLoadError(null);
    void Promise.all([
      getCalibrationFeatures(projectId, baselineId, photo.id),
      fetchBaselineGeometry(projectId, baselineId),
    ])
      .then(([feat, geo]) => {
        if (!alive) return;
        const geoRooms = (geo.rooms as Room[] | undefined) ?? [];
        setRooms(
          geoRooms
            .filter((r) => feat.room_ids.includes(r.id))
            .map((r) => ({ id: r.id, rect: r.rect, labelZh: r.label?.zh })),
        );
        setFeatures(feat.features);
        setMmPerPx(Number(geo.meta?.mm_per_px) || 10);
        setLoadState('ready');
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setLoadError(e instanceof Error ? e.message : String(e));
        setLoadState('error');
      });
    return () => {
      alive = false;
    };
  }, [projectId, baselineId, photo.id, reloadKey]);

  const featureById = useMemo(
    () => new Map(features.map((f): [string, CalibrationFeature] => [f.id, f])),
    [features],
  );
  const placedFeatureIds = useMemo(
    () => placed.map((p) => p.featureId),
    [placed],
  );
  const placedSet = useMemo(
    () => new Set(placedFeatureIds),
    [placedFeatureIds],
  );
  const skippedSet = useMemo(() => new Set(skippedIds), [skippedIds]);
  // F003 分级 + F004 修复: 结构角优先、存疑窗点垫后, 且**地面点先于其异面孪生**
  // (后者是孪生联动提示可达的前提, 见 featureQueue.ts)。不改后端 id 排序契约。
  const queue = useMemo(() => orderFeatureQueue(features), [features]);

  // calib-cure-b3 F004: 异面点 ↔ 地面孪生联动。异面点与其地面孪生**同 (x,y) 只差高度**
  // (F002 构造保证), 故照片里异面点必在孪生点的"正上方"一线。b2 L2 实证的核心错误正是
  // 用户把天花板角点到了窗户半高 —— 有孪生锚点作参照就不必凭空找。
  // 诚实边界: 世界竖直线在照片里只是"近似竖直"(手持相机有 roll/竖直灭点), 故只作参考线,
  // 不做磁吸/不做校验拦截 —— 标定前没有相机参数, 任何"精确"位置提示都是伪精度。
  // 轮候: 队列中第一个未放且未跳过的特征。
  const currentTarget = useMemo(
    () =>
      queue.find((f) => !placedSet.has(f.id) && !skippedSet.has(f.id)) ?? null,
    [queue, placedSet, skippedSet],
  );
  const twinPlaced = useMemo(() => {
    if (!currentTarget || !isElevated(currentTarget)) return null;
    const twinId = planId(currentTarget.id);
    if (twinId === currentTarget.id) return null;
    const idx = placed.findIndex((p) => p.featureId === twinId);
    return idx < 0 ? null : { seq: idx + 1, px: placed[idx].px };
  }, [currentTarget, placed]);

  // 同 F002 的 epoch 守卫: 任何影响 payload 的变更 (放/撤/重来) 使已出预览失效, 飞行中的
  // dry-run 返回按 epoch 丢弃 —— 防旧预览错误打开确认门。跳过不改 payload, 不失效。
  const inputEpoch = useRef(0);
  const invalidatePreview = useCallback(() => {
    inputEpoch.current += 1;
    setPreview(null);
  }, []);

  const buildPayload = useCallback((): PointsCalibrationPayload | null => {
    if (natW === 0 || natH === 0) return null;
    const points: CalibrationPoint[] = [];
    for (const p of placed) {
      const f = featureById.get(p.featureId);
      if (!f) return null;
      points.push({ feature_id: f.id, world: f.world, px: p.px });
    }
    return { mode: 'points', points, img_wh: [natW, natH] };
  }, [placed, featureById, natW, natH]);

  const runPreview = useCallback(async () => {
    const payload = buildPayload();
    if (!payload || payload.points.length < MIN_POINTS) return;
    const epoch = inputEpoch.current;
    setPreviewing(true);
    setError(null);
    try {
      const result = await previewPhotoCalibration(
        projectId,
        baselineId,
        photo.id,
        payload,
      );
      if (inputEpoch.current === epoch) setPreview(result);
    } catch (e) {
      if (inputEpoch.current === epoch) {
        setPreview(null);
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setPreviewing(false);
    }
  }, [buildPayload, projectId, baselineId, photo.id]);

  // ≥4 点自动 dry-run (acceptance): 放置/撤销后 350ms 去抖触发; <4 点不触发只提示。
  useEffect(() => {
    if (placed.length < MIN_POINTS) return;
    const timer = setTimeout(() => {
      void runPreview();
    }, 350);
    return () => clearTimeout(timer);
  }, [placed.length, runPreview]);

  // 点选层坐标 -> 原始像素 (按覆盖层实际显示尺寸等比换算, 同专家模式)。
  const onPickPoint = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (natW === 0 || natH === 0 || currentTarget === null) return;
      const rect = e.currentTarget.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      const fx = (e.clientX - rect.left) / rect.width;
      const fy = (e.clientY - rect.top) / rect.height;
      const px: Pt = [
        Math.round(Math.min(Math.max(fx, 0), 1) * natW),
        Math.round(Math.min(Math.max(fy, 0), 1) * natH),
      ];
      setError(null);
      invalidatePreview();
      setPlaced((prev) => [...prev, { featureId: currentTarget.id, px }]);
    },
    [natW, natH, currentTarget, invalidatePreview],
  );

  const undo = useCallback(() => {
    setError(null);
    invalidatePreview();
    setPlaced((prev) => prev.slice(0, -1));
  }, [invalidatePreview]);

  const skipCurrent = useCallback(() => {
    if (currentTarget === null) return;
    setError(null);
    setSkippedIds((prev) => [...prev, currentTarget.id]);
  }, [currentTarget]);

  const resetAll = useCallback(() => {
    setError(null);
    invalidatePreview();
    setPlaced([]);
    setSkippedIds([]);
  }, [invalidatePreview]);

  const onConfirm = useCallback(async () => {
    if (preview === null) return;
    const payload = buildPayload();
    if (!payload) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await setPhotoCalibration(
        projectId,
        baselineId,
        photo.id,
        payload,
      );
      onCalibrated(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }, [preview, buildPayload, projectId, baselineId, photo.id, onCalibrated]);

  // 确认门 (同 F002 语义): 有当前输入的有效预览且 quality.ok 才可保存; 后端 400 兜底。
  const canConfirm =
    placed.length >= MIN_POINTS &&
    preview !== null &&
    preview.quality.ok &&
    !previewing &&
    !submitting;

  const pctX = (x: number) => (natW ? `${(x / natW) * 100}%` : '0%');
  const pctY = (y: number) => (natH ? `${(y / natH) * 100}%` : '0%');

  if (loadState === 'loading') return <LoadingState rows={3} />;
  if (loadState === 'error')
    return (
      <div className="space-y-3">
        <NoticeBanner
          tone="error"
          title="无法加载特征点(照片可能未标注房间或后端未启动)。"
        >
          {loadError}
        </NoticeBanner>
        <Button
          variant="neutral-outline"
          onClick={() => setReloadKey((k) => k + 1)}
        >
          重试
        </Button>
      </div>
    );

  return (
    <>
      {features.length < MIN_POINTS && (
        <NoticeBanner tone="warn">
          该房间可派生的特征点不足 {MIN_POINTS}{' '}
          个,无法用特征点模式解算。请切换上方「专家(线+角)」模式标定。
        </NoticeBanner>
      )}

      {/* F006 构图引导 (Planner F001 后裁决): 点位铺开到不同墙面 + 不同高度, 解算最稳。 */}
      {features.length >= MIN_POINTS && (
        <NoticeBanner tone="info">
          点位尽量
          <span className="font-semibold">铺开到不同墙面、并覆盖不同高度</span>
          (地面墙角 +
          天花板转角/门窗框顶)——不同高度的点能让解算稳定、避免"歪框"。
          拍摄时也尽量让画面同时拍到地面墙角与天花板转角。
          {/* F003: 结构角优先, 窗特征存疑可跳过 */}
          <span className="mt-1 block">
            候选已按可靠度排序:
            <span className="font-semibold">墙角与天花板转角最可信</span>
            ,优先点它们;标「辅助·可跳过」的窗框点若在照片里找不到对应物(现场是齐腰窗/带护栏),
            直接跳过即可,不必勉强点。
          </span>
        </NoticeBanner>
      )}

      {/* F004 朝向锚定: 标注了视角 -> 点选前先在脑子里对准朝向, 且解算后有镜像交叉校验;
          未标注 -> 非阻断提示去补 (少一道保护, 但不挡标定 —— 门不放宽也不新增门)。 */}
      {features.length >= MIN_POINTS &&
        (VIEW_FACING[photo.direction ?? ''] ? (
          <NoticeBanner tone="info">
            这张照片标注的拍摄视角是{' '}
            <span className="font-semibold">
              {photo.direction}(镜头大致朝{VIEW_FACING[photo.direction ?? '']})
            </span>
            ——点选前先按这个朝向确认画面里的左右关系(如朝东北时,西北角应在画面偏左)。
            解算后系统会自动比对朝向,
            <span className="font-semibold">整组点左右点反会被拦下</span>。
          </NoticeBanner>
        ) : (
          <NoticeBanner tone="warn">
            这张照片<span className="font-semibold">还没标注拍摄视角</span>
            。到「户型基线 ·
            实拍照」卡片为它选一个视角后,解算时能自动检出「整组特征点左右点反」
            的镜像错误(实测高频错误)。不标也能继续标定,只是少一道保护。
          </NoticeBanner>
        ))}

      {/* 引导提示: 当前待放特征 (队列轮候) */}
      <div className="dark:border-brand-400/30 rounded-xl border border-brand-200 bg-brand-100 p-3 text-sm text-brand-700 dark:bg-navy-900 dark:text-brand-300">
        {currentTarget ? (
          <>
            请在右侧照片中点击
            <span className="font-semibold">「{currentTarget.label_zh}」</span>
            <Badge tone="brand" size="xs" className="ml-1">
              {KIND_LABEL[currentTarget.kind]}
            </Badge>
            {/* F003: 存疑特征 (窗) 明示为辅助点, 用户不必为走完队列而瞎点 */}
            {currentTarget.optional && (
              <Badge tone="amber" size="xs" className="ml-1">
                辅助·可跳过
              </Badge>
            )}
            {isElevated(currentTarget) ? (
              <span className="ml-1 font-semibold text-amber-600 dark:text-amber-400">
                ↑ 点画面里的「高处」(天花板转角 / 门窗框顶),不是地面
              </span>
            ) : (
              <span className="ml-1 text-xs">(点落地位置 · 地面墙角)</span>
            )}
            {placed.length < MIN_POINTS && (
              <span className="ml-1">
                · 已放 {placed.length} 点,再放 {MIN_POINTS - placed.length}{' '}
                点自动解算预览
              </span>
            )}
            <span className="ml-1 text-xs">
              (照片里看不到该特征就点「跳过此特征」)
            </span>
            {/* F004: 异面点↔地面孪生联动 —— 有孪生锚点就指出"在第 N 点正上方一线找",
                照片上同时画竖直参考线 (见下方覆盖层)。b2 L2 病灶: 天花板角被点到窗户半高。 */}
            {twinPlaced && (
              <span className="mt-1 block font-semibold text-amber-700 dark:text-amber-400">
                ↑ 它就在你已放的第 {twinPlaced.seq}{' '}
                点(同一墙角的地面点)的正上方——照片上的琥珀色竖线是参考,
                沿它往上找到墙与天花板的交汇处
                <span className="font-normal">
                  (手持拍摄有倾斜,竖线只作大致参照,不必严格贴线)
                </span>
              </span>
            )}
            {/* F003: 存疑说明 —— wtype 为图纸标注, 现场窗型可能失配, 无对应物就跳过 */}
            {currentTarget.caveat_zh && (
              <span className="mt-1 block text-xs text-amber-700 dark:text-amber-400">
                ⚠ {currentTarget.caveat_zh}
              </span>
            )}
          </>
        ) : placed.length >= MIN_POINTS ? (
          '特征点已全部处理。核对下方误差评级与照片上的线框后确认保存。'
        ) : (
          '剩余特征均已跳过,点数不足以解算 —— 请「找回已跳过」或撤销错点重放。'
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-[260px,minmax(0,1fr)]">
        {/* 左: 平面小窗 + 已放列表 */}
        <div className="space-y-2">
          <CalibrationMiniMap
            rooms={rooms}
            mmPerPx={mmPerPx}
            features={features}
            placedIds={placedFeatureIds.map(planId)}
            activeId={currentTarget ? planId(currentTarget.id) : null}
          />
          <p className="text-xs text-gray-400">
            平面小窗(上北下南):闪烁点=当前待点特征,绿勾=已放;琥珀短线=门框,天蓝短线=落地窗。
          </p>
          {placed.length > 0 && (
            <ol className="max-h-32 space-y-1 overflow-y-auto text-xs text-gray-500 dark:text-gray-400">
              {placed.map((p, i) => (
                <li
                  key={`${p.featureId}-${i}`}
                  className="flex items-center gap-2"
                >
                  <span className="bg-emerald-500 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white">
                    {i + 1}
                  </span>
                  <span className="truncate">
                    {featureById.get(p.featureId)?.label_zh ?? p.featureId}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>

        {/* 右: 照片 + 点选覆盖层 (点击 = 放置当前待放特征) */}
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
          <div
            role="presentation"
            onClick={onPickPoint}
            className={`absolute inset-0 ${
              currentTarget ? 'cursor-crosshair' : 'cursor-default'
            }`}
          >
            {/* F002 预览线框 (紫红虚线): dry-run 推算的房间轮廓 */}
            {natW > 0 && natH > 0 && preview && (
              <svg
                viewBox={`0 0 ${natW} ${natH}`}
                preserveAspectRatio="none"
                className="pointer-events-none absolute inset-0 h-full w-full"
              >
                <CalibrationWireframeOverlay wireframe={preview.wireframe} />
              </svg>
            )}
            {/* F004: 孪生竖直参考线 —— 从已放的地面孪生点向上, 引导找同一墙角的高处对应点。
                仅视觉参照 (世界竖直线在照片里近似竖直), 不磁吸、不参与解算。 */}
            {twinPlaced && (
              <div
                className="pointer-events-none absolute border-l-2 border-dashed border-amber-400/80"
                style={{
                  left: pctX(twinPlaced.px[0]),
                  top: 0,
                  height: pctY(twinPlaced.px[1]),
                }}
              />
            )}
            {/* 已放点序号标记 (与左侧列表/小窗绿点对应) */}
            {placed.map((p, i) => (
              <span
                key={`pt${i}`}
                className="bg-emerald-500 pointer-events-none absolute flex h-5 w-5 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full text-[10px] font-bold text-white shadow ring-2 ring-white"
                style={{ left: pctX(p.px[0]), top: pctY(p.px[1]) }}
              >
                {i + 1}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* 进度徽章 */}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone={placed.length >= MIN_POINTS ? 'green' : 'amber'} size="xs">
          特征点 {placed.length}(需 ≥{MIN_POINTS})
        </Badge>
        {skippedIds.length > 0 && (
          <Badge tone="gray" size="xs">
            已跳过 {skippedIds.length}
          </Badge>
        )}
        {previewing && (
          <Badge tone="brand" size="xs">
            解算预览中…
          </Badge>
        )}
      </div>

      {/* F002 预览结果: 误差数值 + 评级徽章 + reasons (复用同一确认门展示件) */}
      {preview && <CalibrationPreviewPanel preview={preview} />}

      {error && (
        <NoticeBanner tone="error" title="标定失败">
          {error}
        </NoticeBanner>
      )}

      {/* 操作 */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-gray-200 pt-3 dark:border-white/10">
        <div className="flex items-center gap-2">
          <Button
            variant="neutral-outline"
            onClick={undo}
            disabled={placed.length === 0}
          >
            撤销上一点
          </Button>
          <Button
            variant="neutral-outline"
            onClick={skipCurrent}
            disabled={currentTarget === null}
          >
            跳过此特征
          </Button>
          {skippedIds.length > 0 && (
            <Button variant="neutral-outline" onClick={() => setSkippedIds([])}>
              找回已跳过
            </Button>
          )}
          <Button
            variant="neutral-outline"
            onClick={resetAll}
            disabled={placed.length === 0 && skippedIds.length === 0}
          >
            重来
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={onClose}>
            取消
          </Button>
          <Button
            variant="neutral-outline"
            onClick={() => void runPreview()}
            disabled={placed.length < MIN_POINTS || previewing || submitting}
            title={
              placed.length < MIN_POINTS
                ? `至少放置 ${MIN_POINTS} 个特征点后可解算`
                : '按当前点位重新解算预览(不保存)'
            }
          >
            {previewing ? '解算中…' : '重新预览'}
          </Button>
          <Button
            variant="primary"
            onClick={() => void onConfirm()}
            disabled={!canConfirm}
            dataTestId="calib-points-confirm"
            title={
              placed.length < MIN_POINTS
                ? `至少放置 ${MIN_POINTS} 个特征点`
                : preview === null
                ? '等待解算预览完成,核对线框与误差后再保存'
                : !preview.quality.ok
                ? '标定质量不合格,请撤销错点重放后重新预览'
                : '保存标定并启用几何锁定精准落位'
            }
          >
            {submitting ? '保存中…' : '确认保存'}
          </Button>
        </div>
      </div>
    </>
  );
}
