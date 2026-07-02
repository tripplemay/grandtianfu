'use client';

import React, { useEffect, useMemo } from 'react';
import type { Geometry, DeriveResult } from 'lib/floorplan/types';
import { readViewBox, readOrigin } from 'lib/floorplan/coords';
import { roomsContentBBox } from 'lib/floorplan/geometry';
import { type Furniture } from 'lib/floorplan/furniture';
import EditorStage from '../EditorStage';
import GeometrySidePanel from '../geometry/GeometrySidePanel';
import FurnitureLayer from '../furniture/FurnitureLayer';
import ZoomControls from '../../ui/ZoomControls';
import { ReadOnlyNotice } from 'components/studio/ui/primitives';
import { useViewport } from '../hooks/useViewport';
import { type GeometryEditor } from '../hooks/useGeometryEditor';

interface Props {
  geometry: Geometry;
  derived: DeriveResult | null;
  furniture: Furniture[];
  geo: GeometryEditor;
  dragging?: boolean; // 拖拽态 (阶段 3 / P2-6): cursor=grabbing。
  readOnly?: boolean; // 只读查看(已确认/历史户型): 隐藏编辑侧栏, 只留画布查看。
}

// 几何模式: EditorStage (含只读家具叠加) + GeometrySidePanel + 视口缩放/平移。
export default function GeometryMode({
  geometry,
  derived,
  furniture,
  geo,
  dragging = false,
  readOnly = false,
}: Props) {
  const viewBox = readViewBox(geometry);
  // origin 引用稳定 (阶段 3 / P2-1): meta.origin 在拖拽期不变, 故据其分量记忆,
  // 避免每帧 readOrigin 产生新数组而击穿 RoomRect/FurnitureItem 的 React.memo。
  const [ox, oy] = readOrigin(geometry);
  const origin = useMemo<[number, number]>(() => [ox, oy], [ox, oy]);
  const vp = useViewport(geo.svgRef);

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
  const onDown = (e: React.PointerEvent) => {
    if (vp.onPointerDown(e)) return;
    geo.onSvgPointerDown(e);
  };
  const onMove = (e: React.PointerEvent) => {
    if (vp.onPointerMove(e)) return;
    geo.onSvgPointerMove(e);
  };
  const onUp = (e: React.PointerEvent) => {
    vp.onPointerUp(e);
    geo.onSvgPointerUp();
  };
  const onCancel = (e: React.PointerEvent) => {
    vp.onPointerUp(e);
    geo.onSvgPointerCancel?.();
  };

  return (
    <>
      <div className="relative min-w-0 flex-1 overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-white/10 dark:bg-navy-800">
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
          viewBox={viewBox}
          origin={origin}
          geometry={geometry}
          derived={derived}
          selection={geo.selection}
          marquee={geo.marquee}
          insertMode={geo.insertMode}
          fwPts={geo.fwPts}
          errorRoomIds={geo.errorRoomIds}
          onSvgPointerDown={onDown}
          onSvgPointerMove={onMove}
          onSvgPointerUp={onUp}
          onSvgPointerCancel={onCancel}
          onRoomPointerDown={geo.onRoomPointerDown}
          onHandlePointerDown={geo.onHandlePointerDown}
          onOpeningPointerDown={geo.onOpeningPointerDown}
          onOpeningHandlePointerDown={geo.onOpeningHandlePointerDown}
          onOpeningFlip={geo.onOpeningFlip}
          onWallPointerDown={geo.onWallPointerDown}
          onFreeWallPointerDown={geo.onFreeWallPointerDown}
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
        />
      </div>

      {readOnly ? (
        <ReadOnlyNotice text="只读查看，编辑工具已隐藏。如需调整，请从户型基线页创建新版本。" />
      ) : (
        <GeometrySidePanel
          geometry={geometry}
          derived={derived}
          selection={geo.selection}
          insertMode={geo.insertMode}
          saveState={geo.saveState}
          dirty={geo.dirty}
          overlapErrors={geo.overlapMsgs}
          onSetRoom={geo.onSetRoom}
          onSetLabel={geo.onSetLabel}
          onSetRect={geo.onSetRect}
          onDelRoom={geo.onDelRoom}
          onSetOp={geo.onSetOp}
          onSetOpWall={geo.onSetOpWall}
          onSetSpan={geo.onSetSpan}
          onDelOp={geo.onDelOp}
          onSetFw={geo.onSetFw}
          onSetFwSpan={geo.onSetFwSpan}
          onDelFw={geo.onDelFw}
          onMerge={geo.onMerge}
          onSplit={geo.onSplit}
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
