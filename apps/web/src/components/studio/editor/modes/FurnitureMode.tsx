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
}

// 家具模式: FurnitureStage (可拖拽家具) + FurnitureSidePanel + 视口缩放/平移。
export default function FurnitureMode({ geometry, derived, furn }: Props) {
  const viewBox = readViewBox(geometry);
  const origin = readOrigin(geometry);
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
          onWheel={vp.onWheel}
          onPointerDownCapture={vp.onTouchCaptureDown}
          onPointerMoveCapture={vp.onTouchCaptureMove}
          onPointerUpCapture={vp.onTouchCaptureUp}
          viewBox={viewBox}
          origin={origin}
          geometry={geometry}
          derived={derived}
          furniture={furn.furniture}
          selectedId={furn.selId}
          onSvgPointerDown={onDown}
          onSvgPointerMove={onMove}
          onSvgPointerUp={onUp}
          onSvgPointerCancel={onCancel}
          onItemPointerDown={furn.onFurnItemDown}
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
        saveState={furn.furnSave}
        onSetField={furn.onSetFurnField}
        onAdd={furn.onAddFurn}
        onDelete={furn.onDelFurn}
        onSave={furn.onSaveFurn}
      />
    </>
  );
}
