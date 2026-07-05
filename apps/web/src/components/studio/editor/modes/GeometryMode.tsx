'use client';

import React, { useEffect, useMemo, useState, useCallback } from 'react';
import type { Geometry, DeriveResult } from 'lib/floorplan/types';
import { readViewBox, readOrigin } from 'lib/floorplan/coords';
import { roomsContentBBox } from 'lib/floorplan/geometry';
import { type Furniture } from 'lib/floorplan/furniture';
import EditorStage from '../EditorStage';
import GeometrySidePanel from '../geometry/GeometrySidePanel';
import FurnitureLayer from '../furniture/FurnitureLayer';
import ZoomControls from '../../ui/ZoomControls';
import { ReadOnlyNotice } from 'components/studio/ui/primitives';
import { useViewport, type ViewportStatePair } from '../hooks/useViewport';
import { type GeometryEditor } from '../hooks/useGeometryEditor';

interface Props {
  geometry: Geometry;
  derived: DeriveResult | null;
  furniture: Furniture[];
  geo: GeometryEditor;
  dragging?: boolean; // 拖拽态 (阶段 3 / P2-6): cursor=grabbing。
  readOnly?: boolean;
  readOnlyReason?: string; // 只读原因 (CP5v3): 版本管理项目的方案几何页给指引文案。
  viewportState?: ViewportStatePair; // P1 共享视口: 几何/家具两 Tab 同一缩放平移 // 只读查看(已确认/历史户型): 隐藏编辑侧栏, 只留画布查看。
  projectId?: string; // 材质C 上传/挂载: 户型编辑上下文
  baselineVersionId?: string;
}

// 几何模式: EditorStage (含只读家具叠加) + GeometrySidePanel + 视口缩放/平移。
export default function GeometryMode({
  geometry,
  derived,
  furniture,
  geo,
  dragging = false,
  readOnly = false,
  readOnlyReason,
  viewportState,
  projectId,
  baselineVersionId,
}: Props) {
  const viewBox = readViewBox(geometry);
  // origin 引用稳定 (阶段 3 / P2-1): meta.origin 在拖拽期不变, 故据其分量记忆,
  // 避免每帧 readOrigin 产生新数组而击穿 RoomRect/FurnitureItem 的 React.memo。
  const [ox, oy] = readOrigin(geometry);
  const origin = useMemo<[number, number]>(() => [ox, oy], [ox, oy]);
  const vp = useViewport(geo.svgRef, viewportState);

  // 底图比例标定 (P6): 采集画布上两点 (几何坐标) -> 询问实际 mm -> 反算 underlay.scale,
  // 保持首点固定。calibPts=null 未标定; []=进入标定采点中。
  const [calibPts, setCalibPts] = useState<[number, number][] | null>(null);
  const underlay = geometry.meta.underlay;

  // 屏幕点 -> 几何坐标 (复用 useGeometryCanvas 同一 contentRef CTM 反算)。
  const toGeo = useCallback(
    (clientX: number, clientY: number): [number, number] | null => {
      const svg = geo.svgRef.current;
      const g = geo.contentRef.current;
      if (!svg || !g) return null;
      const pt = svg.createSVGPoint();
      pt.x = clientX;
      pt.y = clientY;
      const ctm = g.getScreenCTM();
      if (!ctm) return null;
      const p = pt.matrixTransform(ctm.inverse());
      return [p.x - origin[0], p.y - origin[1]];
    },
    [geo.svgRef, geo.contentRef, origin],
  );

  const onCalibDown = (e: React.PointerEvent) => {
    const p = toGeo(e.clientX, e.clientY);
    if (!p) return;
    const pts = [...(calibPts ?? []), p];
    if (pts.length < 2) {
      setCalibPts(pts);
      return;
    }
    const [a, b] = pts;
    const dist = Math.hypot(b[0] - a[0], b[1] - a[1]); // 当前显示几何 px
    setCalibPts(null);
    if (dist < 1e-3) return;
    const mmStr = window.prompt('这两点的实际距离(mm)?', '3000');
    const realMm = mmStr ? parseFloat(mmStr) : NaN;
    if (!isFinite(realMm) || realMm <= 0) return;
    const target = realMm / 10; // 目标几何 px (1px=10mm)
    const curScale = underlay?.scale ?? 1;
    const curDx = underlay?.dx ?? 0;
    const curDy = underlay?.dy ?? 0;
    const newScale = (curScale * target) / dist;
    // 保持首点 a 固定: img_px = (a - dxCur)/scaleCur; newDx = a - newScale*img_px
    const newDx = a[0] - (newScale * (a[0] - curDx)) / curScale;
    const newDy = a[1] - (newScale * (a[1] - curDy)) / curScale;
    geo.onSetUnderlay({ scale: newScale, dx: newDx, dy: newDy });
  };

  const bbox = useMemo(
    () => roomsContentBBox(geometry, origin),
    [geometry, origin],
  );

  // 定位居中 (阶段 5b / P2-12): 校验条点击后 geo.zoomReq 置位 -> Fit 到该元素 -> 清请求。
  useEffect(() => {
    const z = geo.zoomReq;
    if (!z) return;
    vp.fitBox(viewBox, { x: z.x + ox, y: z.y + oy, w: z.w, h: z.h }, 0.55);
    geo.clearZoomReq();
  }, [geo, viewBox, ox, oy, vp]);

  // 视口手势优先: 平移/捏合消费事件则跳过几何拖拽 (坐标层零改)。
  // 只读 (CP5v3): 几何交互 (拖房/落点/框选/门窗/自由墙) 全部旁路, 仅留视口缩放平移
  // —— 否则可产生永远保存不了的本地几何改动 (脏标死锁 beforeunload)。
  const noopPtr = useCallback(() => undefined, []);
  const onDown = (e: React.PointerEvent) => {
    if (vp.onPointerDown(e)) return;
    if (!readOnly) geo.onSvgPointerDown(e);
  };
  const onMove = (e: React.PointerEvent) => {
    if (vp.onPointerMove(e)) return;
    if (!readOnly) geo.onSvgPointerMove(e);
  };
  const onUp = (e: React.PointerEvent) => {
    vp.onPointerUp(e);
    if (!readOnly) geo.onSvgPointerUp();
  };
  const onCancel = (e: React.PointerEvent) => {
    vp.onPointerUp(e);
    if (!readOnly) geo.onSvgPointerCancel?.();
  };

  return (
    <>
      <div className="relative min-w-0 flex-1 overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-white/10 dark:bg-navy-800 lg:h-full">
        <EditorStage
          svgRef={geo.svgRef}
          contentRef={geo.contentRef}
          contentTransform={vp.transform}
          scale={vp.scale}
          dragging={dragging}
          snapGuides={geo.snapGuides}
          dragHud={geo.dragHud}
          onWheel={vp.onWheel}
          onPointerDownCapture={vp.onTouchCaptureDown}
          onPointerMoveCapture={vp.onTouchCaptureMove}
          onPointerUpCapture={vp.onTouchCaptureUp}
          onPointerCancelCapture={vp.onTouchCaptureUp}
          viewBox={viewBox}
          origin={origin}
          geometry={geometry}
          derived={derived}
          underlay={underlay}
          selection={geo.selection}
          marquee={geo.marquee}
          insertMode={geo.insertMode}
          mergePick={geo.mergePick}
          fwPts={geo.fwPts}
          errorRoomIds={geo.errorRoomIds}
          onSvgPointerDown={onDown}
          onSvgPointerMove={onMove}
          onSvgPointerUp={onUp}
          onSvgPointerCancel={onCancel}
          onRoomPointerDown={readOnly ? noopPtr : geo.onRoomPointerDown}
          onHandlePointerDown={readOnly ? noopPtr : geo.onHandlePointerDown}
          onOpeningPointerDown={readOnly ? noopPtr : geo.onOpeningPointerDown}
          onOpeningHandlePointerDown={
            readOnly ? noopPtr : geo.onOpeningHandlePointerDown
          }
          onOpeningFlip={readOnly ? noopPtr : geo.onOpeningFlip}
          onWallPointerDown={readOnly ? noopPtr : geo.onWallPointerDown}
          onFreeWallPointerDown={readOnly ? noopPtr : geo.onFreeWallPointerDown}
          furnitureOverlay={
            furniture.length ? (
              <FurnitureLayer
                furniture={furniture}
                geometry={geometry}
                origin={origin}
                scale={vp.scale}
                readOnly
              />
            ) : null
          }
        />
        <ZoomControls
          zoomPct={vp.zoomPct}
          onFit={() => vp.fitBox(viewBox, bbox)}
          onReset100={vp.reset100}
          onZoomIn={() => vp.zoomStep(1.25, viewBox)}
          onZoomOut={() => vp.zoomStep(1 / 1.25, viewBox)}
        />
        {/* 底图比例标定 (P6): 采点覆盖层 —— 拦截画布点击采两点, 不干扰几何交互 */}
        {calibPts !== null && (
          <div
            className="absolute inset-0 z-30 cursor-crosshair"
            onPointerDown={onCalibDown}
            data-testid="underlay-calibrate-overlay"
          >
            <div className="pointer-events-none absolute left-1/2 top-3 -translate-x-1/2 rounded-lg bg-navy-800/90 px-3 py-1.5 text-xs text-white shadow">
              标定比例:点击底图上两个已知实际距离的端点 ({calibPts.length}/2)
              <button
                type="button"
                className="pointer-events-auto ml-2 underline"
                onClick={(e) => {
                  e.stopPropagation();
                  setCalibPts(null);
                }}
              >
                取消
              </button>
            </div>
          </div>
        )}
      </div>

      {readOnly ? (
        <ReadOnlyNotice
          text={
            readOnlyReason ||
            '只读查看，编辑工具已隐藏。如需调整，请从户型基线页创建新版本。'
          }
        />
      ) : (
        <GeometrySidePanel
          geometry={geometry}
          derived={derived}
          selection={geo.selection}
          insertMode={geo.insertMode}
          mergePickActive={geo.mergePick != null}
          saveState={geo.saveState}
          dirty={geo.dirty}
          overlapErrors={geo.overlapMsgs}
          onSetRoom={geo.onSetRoom}
          onSetLabel={geo.onSetLabel}
          onSetRect={geo.onSetRect}
          onSetWallFinish={geo.onSetWallFinish}
          onSetWallPhoto={geo.onSetWallPhoto}
          projectId={projectId}
          baselineVersionId={baselineVersionId}
          underlay={underlay}
          onSetUnderlay={geo.onSetUnderlay}
          onClearUnderlay={geo.onClearUnderlay}
          onStartCalibrate={() => setCalibPts([])}
          onDelRoom={geo.onDelRoom}
          onSetOp={geo.onSetOp}
          onSetOpWall={geo.onSetOpWall}
          onSetSpan={geo.onSetSpan}
          onDelOp={geo.onDelOp}
          onSetFw={geo.onSetFw}
          onSetFwSpan={geo.onSetFwSpan}
          onDelFw={geo.onDelFw}
          onMerge={geo.onMerge}
          onSuggestMerge={geo.onSuggestMerge}
          onSplit={geo.onSplit}
          onSetGroupType={geo.onSetGroupType}
          onSetGroupLabel={geo.onSetGroupLabel}
          onSelectMember={(id) =>
            geo.setSelection((s) => ({
              ...s,
              room: id,
              room2: null,
              opening: null,
              freeWall: null,
            }))
          }
          onAlign={geo.alignRooms}
          onDistribute={geo.distributeRooms}
          onToggleInsert={geo.onToggleInsert}
          onSave={geo.onSave}
          canLocate={geo.canLocate}
          onLocate={geo.locateFromMsg}
        />
      )}
    </>
  );
}
