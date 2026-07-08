'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { MdChair } from 'react-icons/md';
import type { Geometry, DeriveResult } from 'lib/floorplan/types';
import { readViewBox, readOrigin } from 'lib/floorplan/coords';
import { roomsContentBBox } from 'lib/floorplan/geometry';
import { FURN_DND_MIME } from 'lib/floorplan/furniture';
import FurnitureStage from '../furniture/FurnitureStage';
import FurnitureSidePanel from '../furniture/FurnitureSidePanel';
import FurnitureLibraryDrawer from '../furniture/FurnitureLibraryDrawer';
import ZoomControls from '../../ui/ZoomControls';
import { ReadOnlyNotice } from '../../ui/primitives';
import { useViewport, type ViewportStatePair } from '../hooks/useViewport';
import { type FurnitureEditor } from '../hooks/useFurnitureEditor';
import { useFurnitureCatalog } from '../hooks/useFurnitureCatalog';

interface Props {
  geometry: Geometry;
  derived: DeriveResult | null;
  furn: FurnitureEditor;
  dragging?: boolean; // 拖拽态 (阶段 3 / P2-6): cursor=grabbing。
  readOnly?: boolean;
  viewportState?: ViewportStatePair; // P1 共享视口: 几何/家具两 Tab 同一缩放平移 // 只读查看: 隐藏家具库/编辑侧栏, 只留画布查看。
}

// 家具模式: FurnitureStage (可拖拽家具) + FurnitureSidePanel + 视口缩放/平移。
export default function FurnitureMode({
  geometry,
  derived,
  furn,
  dragging = false,
  readOnly = false,
  viewportState,
}: Props) {
  const viewBox = readViewBox(geometry);
  // origin 引用稳定 (阶段 3 / P2-1): 见 GeometryMode 同注。
  const [ox, oy] = readOrigin(geometry);
  const origin = useMemo<[number, number]>(() => [ox, oy], [ox, oy]);
  const vp = useViewport(furn.svgRef, viewportState);
  // 家具目录 (P2 前后端同源): 拉取一次灌入建件缓存, entries 驱动库分组/类型下拉重渲染。
  const catalog = useFurnitureCatalog();
  // 家具库侧滑抽屉 (P2 抽屉化): 库从侧栏移入右缘抽屉, 由画布悬浮按钮开合。
  const [libOpen, setLibOpen] = useState(false);

  const bbox = useMemo(
    () => roomsContentBBox(geometry, origin),
    [geometry, origin],
  );

  // 定位居中 (阶段 5b / P2-12): 出界警告点击后 furn.zoomReq 置位 -> Fit 到该件 -> 清请求。
  useEffect(() => {
    const z = furn.zoomReq;
    if (!z) return;
    vp.fitBox(viewBox, { x: z.x + ox, y: z.y + oy, w: z.w, h: z.h }, 0.55);
    furn.clearZoomReq();
  }, [furn, viewBox, ox, oy, vp]);

  // 库项拖入画布 (阶段 5b / P3): dragover 必须 preventDefault 才能触发 drop。
  const onDragOver = (e: React.DragEvent) => {
    if (e.dataTransfer.types.includes(FURN_DND_MIME)) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
    }
  };
  const onDrop = (e: React.DragEvent) => {
    const type =
      e.dataTransfer.getData(FURN_DND_MIME) ||
      e.dataTransfer.getData('text/plain');
    if (!type) return;
    e.preventDefault();
    furn.dropFurniture(type, e.clientX, e.clientY);
  };

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
      <div
        className="relative min-w-0 flex-1 overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-white/10 dark:bg-navy-800 lg:h-full"
        data-testid="furn-canvas-dropzone"
        onDragOver={onDragOver}
        onDrop={onDrop}
      >
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
          onPointerCancelCapture={vp.onTouchCaptureUp}
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
          onZoomIn={() => vp.zoomStep(1.25, viewBox)}
          onZoomOut={() => vp.zoomStep(1 / 1.25, viewBox)}
        />
        {/* 家具库触发: 悬浮画布左上, 开**左缘**侧滑抽屉 (抽屉打开时盖住本按钮, 由抽屉自带
            X 关闭)。左出让开右侧家具编辑面板。只读态不出。 */}
        {!readOnly && (
          <button
            type="button"
            onClick={() => setLibOpen(true)}
            data-testid="open-furniture-library"
            className="absolute left-3 top-3 z-10 flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white/95 px-3 py-1.5 text-xs font-medium text-navy-700 shadow-sm backdrop-blur hover:bg-gray-50 dark:border-white/10 dark:bg-navy-800/95 dark:text-white dark:hover:bg-navy-700"
          >
            <MdChair className="h-4 w-4" /> 家具库
          </button>
        )}
      </div>

      {readOnly ? (
        <ReadOnlyNotice text="只读查看，家具库与编辑工具已隐藏。如需调整，请在方案中心创建调整副本。" />
      ) : (
        <FurnitureSidePanel
          geometry={geometry}
          catalog={catalog}
          furniture={furn.furniture}
          selectedId={furn.selId}
          selectedCount={furn.selectedIds.length}
          saveState={furn.furnSave}
          dirty={furn.dirty}
          onSetField={furn.onSetFurnField}
          onDelete={furn.onDelFurn}
          onBringToFront={furn.bringToFront}
          onSendToBack={furn.sendToBack}
          onAlign={furn.alignFurn}
          onDistribute={furn.distributeFurn}
          onSave={furn.onSaveFurn}
          canLocate={furn.canLocate}
          onLocate={furn.locateFromMsg}
        />
      )}

      {!readOnly && (
        <FurnitureLibraryDrawer
          open={libOpen}
          onClose={() => setLibOpen(false)}
          onQuickAdd={furn.onAddFurn}
          catalog={catalog}
        />
      )}
    </>
  );
}
