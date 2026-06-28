'use client';

import React from 'react';
import type { Geometry, DeriveResult } from 'lib/floorplan/types';
import { readViewBox, readOrigin } from 'lib/floorplan/coords';
import FurnitureStage from '../furniture/FurnitureStage';
import FurnitureSidePanel from '../furniture/FurnitureSidePanel';
import { type FurnitureEditor } from '../hooks/useFurnitureEditor';

interface Props {
  geometry: Geometry;
  derived: DeriveResult | null;
  furn: FurnitureEditor;
}

// 家具模式: FurnitureStage (可拖拽家具) + FurnitureSidePanel。
export default function FurnitureMode({ geometry, derived, furn }: Props) {
  const viewBox = readViewBox(geometry);
  const origin = readOrigin(geometry);

  return (
    <>
      <div className="min-w-0 flex-1 overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-white/10 dark:bg-navy-800">
        <FurnitureStage
          svgRef={furn.svgRef}
          viewBox={viewBox}
          origin={origin}
          geometry={geometry}
          derived={derived}
          furniture={furn.furniture}
          selectedIndex={furn.selFurn}
          onSvgPointerDown={furn.onFurnSvgDown}
          onSvgPointerMove={furn.onFurnSvgMove}
          onSvgPointerUp={furn.onFurnSvgUp}
          onItemPointerDown={furn.onFurnItemDown}
        />
      </div>

      <FurnitureSidePanel
        furniture={furn.furniture}
        selectedIndex={furn.selFurn}
        saveState={furn.furnSave}
        onSetField={furn.onSetFurnField}
        onAdd={furn.onAddFurn}
        onDelete={furn.onDelFurn}
        onSave={furn.onSaveFurn}
      />
    </>
  );
}
