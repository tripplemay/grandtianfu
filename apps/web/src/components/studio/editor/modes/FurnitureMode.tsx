'use client';

import React, { useMemo } from 'react';
import type { Geometry, DeriveResult } from 'lib/floorplan/types';
import { readViewBox, readOrigin } from 'lib/floorplan/coords';
import { roomsContentBBox } from 'lib/floorplan/geometry';
import FurnitureStage from '../furniture/FurnitureStage';
import FurnitureSidePanel from '../furniture/FurnitureSidePanel';
import ZoomControls from '../../ui/ZoomControls';
import { useViewport } from '../hooks/useViewport';
import { type FurnitureEditor } from '../hooks/useFurnitureEditor';

interface Props {
  geometry: Geometry;
  derived: DeriveResult | null;
  furn: FurnitureEditor;
  dragging?: boolean; // 拖拽态 (阶段 3 / P2-6): cursor=grabbing。
}

// 家具模式: FurnitureStage (可拖拽家具) + FurnitureSidePanel + 视口缩放/平移。
export default function FurnitureMode({
  geometry,
  derived,
  furn,
  dragging = false,
}: Props) {
  const viewBox = readViewBox(geometry);
  // origin 引用稳定 (阶段 3 / P2-1): 见 GeometryMode 同注。
  const [ox, oy] = readOrigin(geometry);
  const origin = useMemo<[number, number]>(() => [ox, oy], [ox, oy]);
  const vp = useViewport(furn.svgRef);

  const bbox = useMemo(
    () => roomsContentBBox(geometry, origin),
    [geometry, origin],
  );

  const onDown = (e: React.PointerEvent) => {
    if (vp.onPointerDown(e)) return;
    furn.onFurnSvgDown(e);
  };
  const onMove = (e: React.PointerEvent) => {
    if (vp.onPointerMove(e)) return;
    furn.onFurnSvgMove(e);
  };
  const onUp = (e: React.PointerEvent) => {
    vp.onPointerUp(e);
    furn.onFurnSvgUp();
  };
  const onCancel = (e: React.PointerEvent) => {
    vp.onPointerUp(e);
    furn.onFurnSvgCancel();
  };

  return (
    <>
      <div className="relative min-w-0 flex-1 overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-white/10 dark:bg-navy-800">
        <FurnitureStage
          svgRef={furn.svgRef}
          contentRef={furn.contentRef}
          contentTransform={vp.transform}
          scale={vp.scale}
          dragging={dragging}
          snapGuides={furn.snapGuides}
          dragHud={furn.dragHud}
          onWheel={vp.onWheel}
          onPointerDownCapture={vp.onTouchCaptureDown}
          onPointerMoveCapture={vp.onTouchCaptureMove}
          onPointerUpCapture={vp.onTouchCaptureUp}
          viewBox={viewBox}
          origin={origin}
          geometry={geometry}
          derived={derived}
          furniture={furn.furniture}
          selectedIds={furn.selectedIds}
          marquee={furn.marquee}
          blockedId={furn.blockedId}
          onSvgPointerDown={onDown}
          onSvgPointerMove={onMove}
          onSvgPointerUp={onUp}
          onSvgPointerCancel={onCancel}
          onItemPointerDown={furn.onFurnItemDown}
          onResizeDown={furn.onFurnResizeDown}
          onRotateDown={furn.onFurnRotateDown}
        />
        <ZoomControls
          zoomPct={vp.zoomPct}
          onFit={() => vp.fitBox(viewBox, bbox)}
          onReset100={vp.reset100}
        />
      </div>

      <FurnitureSidePanel
        furniture={furn.furniture}
        selectedId={furn.selId}
        selectedCount={furn.selectedIds.length}
        saveState={furn.furnSave}
        dirty={furn.dirty}
        onSetField={furn.onSetFurnField}
        onAdd={furn.onAddFurn}
        onDelete={furn.onDelFurn}
        onBringToFront={furn.bringToFront}
        onSendToBack={furn.sendToBack}
        onAlign={furn.alignFurn}
        onDistribute={furn.distributeFurn}
        onSave={furn.onSaveFurn}
      />
    </>
  );
}
