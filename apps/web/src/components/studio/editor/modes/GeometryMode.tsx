'use client';

import React from 'react';
import type { Geometry, DeriveResult } from 'lib/floorplan/types';
import { readViewBox, readOrigin } from 'lib/floorplan/coords';
import { type Furniture } from 'lib/floorplan/furniture';
import EditorStage from '../EditorStage';
import GeometrySidePanel from '../geometry/GeometrySidePanel';
import FurnitureLayer from '../furniture/FurnitureLayer';
import { type GeometryEditor } from '../hooks/useGeometryEditor';

interface Props {
  geometry: Geometry;
  derived: DeriveResult | null;
  furniture: Furniture[];
  geo: GeometryEditor;
}

// 几何模式: EditorStage (含只读家具叠加) + GeometrySidePanel。
export default function GeometryMode({
  geometry,
  derived,
  furniture,
  geo,
}: Props) {
  const viewBox = readViewBox(geometry);
  const origin = readOrigin(geometry);

  return (
    <>
      <div className="min-w-0 flex-1 overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-white/10 dark:bg-navy-800">
        <EditorStage
          svgRef={geo.svgRef}
          viewBox={viewBox}
          origin={origin}
          geometry={geometry}
          derived={derived}
          selection={geo.selection}
          insertMode={geo.insertMode}
          fwPts={geo.fwPts}
          errorRoomIds={geo.errorRoomIds}
          onSvgPointerDown={geo.onSvgPointerDown}
          onSvgPointerMove={geo.onSvgPointerMove}
          onSvgPointerUp={geo.onSvgPointerUp}
          onRoomPointerDown={geo.onRoomPointerDown}
          onHandlePointerDown={geo.onHandlePointerDown}
          onOpeningPointerDown={geo.onOpeningPointerDown}
          onWallPointerDown={geo.onWallPointerDown}
          onFreeWallPointerDown={geo.onFreeWallPointerDown}
          furnitureOverlay={
            furniture.length ? (
              <FurnitureLayer
                furniture={furniture}
                geometry={geometry}
                origin={origin}
                selectedIndex={null}
                readOnly
              />
            ) : null
          }
        />
      </div>

      <GeometrySidePanel
        geometry={geometry}
        derived={derived}
        selection={geo.selection}
        insertMode={geo.insertMode}
        saveState={geo.saveState}
        overlapErrors={geo.overlapMsgs}
        onSetRoom={geo.onSetRoom}
        onSetLabel={geo.onSetLabel}
        onSetRect={geo.onSetRect}
        onSetOp={geo.onSetOp}
        onSetOpWall={geo.onSetOpWall}
        onSetSpan={geo.onSetSpan}
        onDelOp={geo.onDelOp}
        onSetFw={geo.onSetFw}
        onSetFwSpan={geo.onSetFwSpan}
        onDelFw={geo.onDelFw}
        onMerge={geo.onMerge}
        onSplit={geo.onSplit}
        onToggleInsert={geo.onToggleInsert}
        onSave={geo.onSave}
      />
    </>
  );
}
