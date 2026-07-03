'use client';

import React, { useCallback, useRef, useState } from 'react';
import { fetchRenderScene, saveFurniture } from 'lib/studioApi';
import type { Geometry } from 'lib/floorplan/types';
import { readOrigin, FALLBACK_ORIGIN } from 'lib/floorplan/coords';
import {
  type Furniture,
  furnAbs,
  isCircle,
  reanchor,
  buildDefaultFurniture,
  buildFurnitureAt,
  duplicateFurniture,
  stripRuntimeFields,
  furnSnapGuides,
  furnGeoBox,
  furnitureSaveWarnings,
  locateFurnInMessage,
  roomAtGeo,
  computeFurnResize,
  computeRotation,
  clampToRoom,
  snapToWall,
  bringToFrontZ,
  sendToBackZ,
  furnInMarquee,
  furnAlignPatches,
  furnDistributePatches,
} from 'lib/floorplan/furniture';
import {
  roomById,
  marqueeRect,
  groupMemberRects,
  nearestPartRect,
  type SnapGuide,
  type AlignMode,
  type DistributeMode,
} from 'lib/floorplan/geometry';
import type { DragHud } from 'lib/floorplan/overlay';
import { type FurnSaveState } from '../furniture/FurnitureSidePanel';
import { type Marquee } from './useGeometryCanvas';
import { isBackgroundTarget } from '../pointerUtils';

const EMPTY_FURN_SAVE: FurnSaveState = {
  saving: false,
  savedOk: false,
  error: null,
  warns: [],
};

// 拖拽以稳定 id 为身份 (阶段 0): 删/重排中间件不会错位。
// 三种拖拽 (阶段 4a): 移动 / 缩放手柄 / 旋转柄。
type FurnDrag =
  | {
      kind: 'move';
      id: string;
      ox: number;
      oy: number;
      // 群组移动 (阶段 5a / P2-7): 多选时随主件同 delta 平移的件 orig 锚点 (绝对几何)。
      group?: Array<{ id: string; ax: number; ay: number }>;
    }
  | { kind: 'resize'; id: string; handle: string }
  | { kind: 'rotate'; id: string };

interface FurnitureEditorParams {
  projectId: string;
  schemeId?: string;
  canSave: boolean;
  gRef: React.MutableRefObject<Geometry | null>;
  furniture: Furniture[];
  setFurniture: React.Dispatch<React.SetStateAction<Furniture[]>>;
  furnRef: React.MutableRefObject<Furniture[]>;
  showToast: (msg: string) => void;
  // 历史栈落点入栈支撑 (阶段 2): 拖拽 down/up 信号 (中间帧不入栈, 结束落一帧)。
  beginDrag: () => void;
  endDrag: () => void;
}

// 家具编辑器 (B2): 指针拖拽 -> 反推 room_id + dx/dy; 侧栏增删改 + 保存。
export function useFurnitureEditor({
  projectId,
  schemeId = 'default',
  canSave,
  gRef,
  furniture,
  setFurniture,
  furnRef,
  showToast,
  beginDrag,
  endDrag,
}: FurnitureEditorParams) {
  // 选中模型 单→多 (阶段 5a / P2-7): selectedIds 为真源; 主选 selId = 最后选中 (供侧栏
  // 单项编辑 / 缩放旋转把手 N=1 兼容)。单选即 N=1 的特例 ([id])。
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const selId =
    selectedIds.length > 0 ? selectedIds[selectedIds.length - 1] : null;
  // 真值 ref (闭包不过期): 拖拽/键盘读最新选择, 使交互句柄 useCallback 引用稳定。
  const selectedIdsRef = useRef<string[]>(selectedIds);
  selectedIdsRef.current = selectedIds;
  // 向后兼容单选 setter: 内部加删/复制后选中单件 (N=1)。
  const setSelId = useCallback(
    (id: string | null) => setSelectedIds(id == null ? [] : [id]),
    [],
  );
  const [furnSave, setFurnSave] = useState<FurnSaveState>(EMPTY_FURN_SAVE);
  // 防丢失 (P1-6): 写入口置脏; 保存成功清脏。
  const [dirty, setDirty] = useState(false);
  const savingRef = useRef(false);
  // 拖拽期可视反馈 (阶段 3 / P1-4): 对齐辅助线 + 实时尺寸 HUD。松手清空。
  const [snapGuides, setSnapGuides] = useState<SnapGuide[]>([]);
  const [dragHud, setDragHud] = useState<DragHud | null>(null);
  // 越界拖动被夹取的件 id (P2-5): FurnitureLayer 据此红描边提示。
  const [blockedId, setBlockedId] = useState<string | null>(null);
  // 框选 marquee (阶段 5a / P2-7): 画布拖拽期镜像矩形 (几何坐标); 松手清空。
  const [marquee, setMarquee] = useState<Marquee | null>(null);
  const marqueeRef = useRef<{
    x0: number;
    y0: number;
    x1: number;
    y1: number;
    moved: boolean;
    additive: boolean;
  } | null>(null);
  // 剪贴板支持多件 (P2-4)。
  const clipboardRef = useRef<Furniture[]>([]);
  // 定位居中请求 (阶段 5b / P2-12): 几何坐标包围盒; FurnitureMode 消费后 clearZoomReq。
  const [zoomReq, setZoomReq] = useState<{
    x: number;
    y: number;
    w: number;
    h: number;
  } | null>(null);
  const clearZoomReq = useCallback(() => setZoomReq(null), []);

  const markDirty = useCallback(() => setDirty(true), []);

  const svgRef = useRef<SVGSVGElement>(null);
  // 视口变换层 <g> 的引用: getScreenCTM 取此 g (含 translate/scale), 使缩放/平移下
  // 命中坐标自动正确 (阶段 1)。
  const contentRef = useRef<SVGGElement>(null);
  const furnDragRef = useRef<FurnDrag | null>(null);

  // ---- 不可变 furniture 更新, 同步 furnRef ---- //
  const updateFurniture = useCallback(
    (updater: (f: Furniture[]) => Furniture[]) => {
      setFurniture((prev) => {
        const next = updater(prev);
        furnRef.current = next;
        return next;
      });
      setFurnSave((s) => (s.savedOk || s.error ? EMPTY_FURN_SAVE : s));
      setDirty(true);
    },
    [setFurniture, furnRef],
  );

  // ---- 几何坐标换算 (§①, 与几何模式同口径) ---- //
  // CTM 取自内层 transform <g> (contentRef): scale≠1 / 平移时仍正确反算。
  const getGeoPoint = useCallback(
    (e: React.PointerEvent): { gx: number; gy: number } | null => {
      const svg = svgRef.current;
      const g = contentRef.current;
      if (!svg || !g) return null;
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const ctm = g.getScreenCTM();
      if (!ctm) return null;
      const p = pt.matrixTransform(ctm.inverse());
      const origin = gRef.current ? readOrigin(gRef.current) : FALLBACK_ORIGIN;
      return { gx: p.x - origin[0], gy: p.y - origin[1] };
    },
    [gRef],
  );

  // 原始 client 坐标 -> 绝对几何坐标 (拖入画布 drop 用, 阶段 5b)。同 getGeoPoint 口径,
  // 但 drop 事件无 React.PointerEvent, 故从 clientX/Y 直接换算。
  const clientToGeo = useCallback(
    (clientX: number, clientY: number): { gx: number; gy: number } | null => {
      const svg = svgRef.current;
      const gNode = contentRef.current;
      if (!svg || !gNode) return null;
      const pt = svg.createSVGPoint();
      pt.x = clientX;
      pt.y = clientY;
      const ctm = gNode.getScreenCTM();
      if (!ctm) return null;
      const p = pt.matrixTransform(ctm.inverse());
      const origin = gRef.current ? readOrigin(gRef.current) : FALLBACK_ORIGIN;
      return { gx: p.x - origin[0], gy: p.y - origin[1] };
    },
    [gRef],
  );

  // 切换 Tab 时清空家具选中 / 拖拽态 (沿用原 onChange 逻辑)。
  const resetSelection = useCallback(() => {
    setSelId(null);
    furnDragRef.current = null;
  }, [setSelId]);

  // ===== 家具交互 (B2): 指针拖拽 -> 反推 room_id + dx/dy ===== //
  // onFurnItemDown useCallback (阶段 3 / P2-1): 透传给 memo 化 FurnitureItem 后引用稳定。
  const onFurnItemDown = useCallback(
    (e: React.PointerEvent, id: string) => {
      e.stopPropagation();
      // Shift+点 加/减选 (阶段 5a / P2-7): 仅改选择, 不起拖拽。
      if (e.shiftKey) {
        setSelectedIds((prev) =>
          prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
        );
        return;
      }
      const pt = getGeoPoint(e);
      const g = gRef.current;
      if (!pt || !g) return;
      const it = furnRef.current.find((f) => f.id === id);
      if (!it) return;
      // 命中已在多选集合内 (N>1) -> 保留集合做群移; 否则单选该件。
      const cur = selectedIdsRef.current;
      const inGroup = cur.length > 1 && cur.includes(id);
      let group: Array<{ id: string; ax: number; ay: number }> | undefined;
      if (inGroup) {
        group = cur
          .map((sid) => {
            const f = furnRef.current.find((x) => x.id === sid);
            if (!f) return null;
            const fa = furnAbs(f, g);
            return {
              id: sid,
              ax: isCircle(f) ? fa.cx : fa.x,
              ay: isCircle(f) ? fa.cy : fa.y,
            };
          })
          .filter(
            (x): x is { id: string; ax: number; ay: number } => x != null,
          );
        // 主选移到末位 (selId=最后选中=被拖件)。
        setSelectedIds((prev) => [...prev.filter((x) => x !== id), id]);
      } else {
        setSelectedIds([id]);
      }
      const a = furnAbs(it, g);
      furnDragRef.current = {
        kind: 'move',
        id,
        ox: isCircle(it) ? pt.gx - a.cx : pt.gx - a.x,
        oy: isCircle(it) ? pt.gy - a.cy : pt.gy - a.y,
        group: inGroup ? group : undefined,
      };
      beginDrag();
      svgRef.current?.setPointerCapture(e.pointerId);
    },
    [getGeoPoint, gRef, furnRef, beginDrag],
  );

  // 缩放手柄按下 (P2-3): 复用 geometry ResizeHandles 模式。
  const onFurnResizeDown = useCallback(
    (e: React.PointerEvent, handle: string) => {
      e.stopPropagation();
      const id = selId;
      if (id === null) return;
      setSelId(id);
      furnDragRef.current = { kind: 'resize', id, handle };
      beginDrag();
      svgRef.current?.setPointerCapture(e.pointerId);
    },
    [selId, setSelId, beginDrag],
  );

  // 旋转柄按下 (P2-2)。
  const onFurnRotateDown = useCallback(
    (e: React.PointerEvent) => {
      e.stopPropagation();
      const id = selId;
      if (id === null) return;
      furnDragRef.current = { kind: 'rotate', id };
      beginDrag();
      svgRef.current?.setPointerCapture(e.pointerId);
    },
    [selId, beginDrag],
  );

  // 空白拖出 marquee 框选 (阶段 5a / P2-7): 起拖记录; 松手按相交选件 (点击=清选)。
  const onFurnSvgDown = (e: React.PointerEvent) => {
    if (!isBackgroundTarget(e)) return;
    const pt = getGeoPoint(e);
    if (!pt) {
      setSelectedIds([]);
      return;
    }
    marqueeRef.current = {
      x0: pt.gx,
      y0: pt.gy,
      x1: pt.gx,
      y1: pt.gy,
      moved: false,
      additive: e.shiftKey,
    };
    setMarquee({ x0: pt.gx, y0: pt.gy, x1: pt.gx, y1: pt.gy });
    svgRef.current?.setPointerCapture(e.pointerId);
  };

  const onFurnSvgMove = useCallback(
    (e: React.PointerEvent) => {
      // 框选 marquee 进行中 (阶段 5a): 仅更新框矩形, 不动数据。
      const m = marqueeRef.current;
      if (m) {
        const p = getGeoPoint(e);
        if (!p) return;
        if (Math.abs(p.gx - m.x0) > 2 || Math.abs(p.gy - m.y0) > 2)
          m.moved = true;
        m.x1 = p.gx;
        m.y1 = p.gy;
        setMarquee({ x0: m.x0, y0: m.y0, x1: p.gx, y1: p.gy });
        return;
      }
      const d = furnDragRef.current;
      const g = gRef.current;
      if (!d || !g) return;
      const pt = getGeoPoint(e);
      if (!pt) return;
      const mpp =
        ((g.meta as { mm_per_px?: number } | undefined)?.mm_per_px ?? 10) || 10;
      const it0 = furnRef.current.find((f) => f.id === d.id);
      if (!it0) return;
      const a0 = furnAbs(it0, g);
      const circle = isCircle(it0);

      // ---- 旋转柄拖拽 (P2-2): 指针角 -> rot, 15° 吸附 (Shift 自由) ---- //
      if (d.kind === 'rotate') {
        const rot = computeRotation(a0.cx, a0.cy, pt.gx, pt.gy, e.shiftKey);
        updateFurniture((f) =>
          f.map((it) => {
            if (it.id !== d.id) return it;
            if (rot === 0) {
              const n = { ...it };
              delete n.rot;
              return n;
            }
            return { ...it, rot };
          }),
        );
        setSnapGuides([]);
        setDragHud({ x: a0.cx, y: a0.y, text: `${Math.round(rot)}°` });
        return;
      }

      // ---- 缩放手柄拖拽 (P2-3): 件本地系内固定对边改 w/h (圆形改 r) ---- //
      if (d.kind === 'resize') {
        const rot = typeof it0.rot === 'number' ? it0.rot : 0;
        const rz = computeFurnResize(a0, circle, d.handle, pt.gx, pt.gy, rot);
        const patch = reanchor(
          it0,
          g,
          rz.anchorX,
          rz.anchorY,
          rz.centerX,
          rz.centerY,
        );
        const nit: Furniture = { ...it0, ...patch };
        if (rz.r != null) nit.r = rz.r;
        if (rz.w != null) nit.w = rz.w;
        if (rz.h != null) nit.h = rz.h;
        updateFurniture((f) => f.map((it) => (it.id === d.id ? nit : it)));
        const a = furnAbs(nit, g);
        setSnapGuides(furnSnapGuides(nit, g, a));
        setDragHud({
          x: a.cx,
          y: a.y,
          text: circle
            ? `R ${Math.round(a.r * mpp)}mm`
            : `${Math.round(a.w * mpp)} × ${Math.round(a.h * mpp)}mm`,
        });
        return;
      }

      // ---- 移动拖拽 (越界 clamp + 贴墙吸附, P2-5) ---- //
      let anchorX = pt.gx - d.ox;
      let anchorY = pt.gy - d.oy;
      let cX = circle ? anchorX : anchorX + a0.w / 2;
      let cY = circle ? anchorY : anchorY + a0.h / 2;
      // 落点中心命中房间 -> 允许跨房; 未命中任何房 -> 夹回当前房并红描边提示。
      const hit = roomAtGeo(g, cX, cY);
      const room = hit ?? roomById(g, it0.room_id ?? null);
      let blocked = false;
      if (room) {
        // 异形 (P3): 属 merge 组时夹取/吸附对准最近一条腿 (件可停在 L 并集任意腿, 不被塞回单腿)。
        const memberRects = groupMemberRects(g, room);
        const legRect =
          memberRects.length > 1
            ? nearestPartRect(memberRects, cX, cY)
            : room.rect;
        if (!hit) {
          const c = clampToRoom(
            legRect,
            anchorX,
            anchorY,
            a0.w,
            a0.h,
            circle,
            a0.r,
          );
          anchorX = c.anchorX;
          anchorY = c.anchorY;
          blocked = c.clamped;
        }
        // 近墙贴墙吸附 (落在的腿内)。
        const s = snapToWall(
          legRect,
          anchorX,
          anchorY,
          a0.w,
          a0.h,
          circle,
          a0.r,
        );
        anchorX = s.anchorX;
        anchorY = s.anchorY;
      }
      cX = circle ? anchorX : anchorX + a0.w / 2;
      cY = circle ? anchorY : anchorY + a0.h / 2;
      // 群组移动 (阶段 5a / P2-7): 主件吸附后的位移 delta 同样作用于其余选中件。
      if (d.group && d.group.length > 1) {
        const primaryOrig = d.group.find((ge) => ge.id === d.id);
        const ddx = primaryOrig ? anchorX - primaryOrig.ax : 0;
        const ddy = primaryOrig ? anchorY - primaryOrig.ay : 0;
        const patches = new Map<string, Furniture>();
        for (const ge of d.group) {
          const itg = furnRef.current.find((f) => f.id === ge.id);
          if (!itg) continue;
          const ag = furnAbs(itg, g);
          if (isCircle(itg)) {
            const ncx = ge.ax + ddx;
            const ncy = ge.ay + ddy;
            patches.set(ge.id, {
              ...itg,
              ...reanchor(itg, g, ncx, ncy, ncx, ncy),
            });
          } else {
            const nax = ge.ax + ddx;
            const nay = ge.ay + ddy;
            patches.set(ge.id, {
              ...itg,
              ...reanchor(itg, g, nax, nay, nax + ag.w / 2, nay + ag.h / 2),
            });
          }
        }
        updateFurniture((f) => f.map((it) => patches.get(it.id ?? '') ?? it));
        setBlockedId(null);
        setSnapGuides([]);
        setDragHud({
          x: cX,
          y: circle ? anchorY - a0.r : anchorY,
          text: `群移 ${d.group.length} 件`,
        });
        return;
      }
      const patch = reanchor(it0, g, anchorX, anchorY, cX, cY);
      const nit: Furniture = { ...it0, ...patch };
      updateFurniture((f) => f.map((it) => (it.id === d.id ? nit : it)));
      setBlockedId(blocked ? d.id : null);
      const a = furnAbs(nit, g);
      setSnapGuides(furnSnapGuides(nit, g, a));
      setDragHud({
        x: a.cx,
        y: a.y,
        text: circle
          ? `R ${Math.round(a.r * mpp)}mm`
          : `${Math.round(a.w * mpp)} × ${Math.round(a.h * mpp)}mm`,
      });
    },
    [getGeoPoint, gRef, furnRef, updateFurniture, setMarquee],
  );

  const onFurnSvgUp = useCallback(() => {
    // 框选 marquee 松手 (阶段 5a): 有位移=按相交选件 (Shift=并入); 无位移=清选。
    const m = marqueeRef.current;
    if (m) {
      marqueeRef.current = null;
      setMarquee(null);
      const g = gRef.current;
      if (m.moved && g) {
        const rect = marqueeRect(m.x0, m.y0, m.x1, m.y1);
        const hit = furnInMarquee(furnRef.current, g, rect);
        setSelectedIds((prev) => {
          if (!m.additive) return hit;
          const set = new Set(prev);
          hit.forEach((id) => set.add(id));
          return [...set];
        });
      } else if (!m.moved) {
        setSelectedIds([]);
      }
      return;
    }
    if (furnDragRef.current) furnDragRef.current = null;
    setSnapGuides([]); // 松手清除可视反馈 (P1-4)。
    setDragHud(null);
    setBlockedId(null); // 清除越界红描边提示 (P2-5)。
    endDrag(); // 落点入栈 (内部自守卫)。
  }, [endDrag, gRef, furnRef, setMarquee]);

  // pointercancel: 复用 up 清理 (阶段 0)。
  const onFurnSvgCancel = onFurnSvgUp;

  // ===== 家具侧栏编辑 ===== //
  const onSetFurnField = (field: keyof Furniture, value: string | number) => {
    if (selId === null) return;
    updateFurniture((f) =>
      f.map((it) => {
        if (it.id !== selId) return it;
        // label/color 清空 -> 删键, 避免落盘空串。
        if ((field === 'label' || field === 'color') && value === '') {
          const next = { ...it };
          delete next[field];
          return next;
        }
        // rot=0 -> 删键, 保盘上格式干净 + 引擎 no-op (P2-2)。
        if (field === 'rot' && Number(value) === 0) {
          const next = { ...it };
          delete next.rot;
          return next;
        }
        return { ...it, [field]: value };
      }),
    );
  };

  // ===== z-order 置顶/置底 (P2-13) ===== //
  const bringToFront = useCallback(() => {
    if (selId === null) return;
    updateFurniture((f) => {
      const zorder = bringToFrontZ(f, selId);
      return f.map((it) => (it.id === selId ? { ...it, zorder } : it));
    });
  }, [selId, updateFurniture]);

  const sendToBack = useCallback(() => {
    if (selId === null) return;
    updateFurniture((f) => {
      const zorder = sendToBackZ(f, selId);
      return f.map((it) => (it.id === selId ? { ...it, zorder } : it));
    });
  }, [selId, updateFurniture]);

  const onAddFurn = (type: string) => {
    const g = gRef.current;
    if (!g || !g.rooms.length) {
      showToast('无房间可放置家具');
      return;
    }
    // 当前房 = 选中件所属房, 否则首个房间。
    let room = g.rooms[0];
    if (selId !== null) {
      const it = furnRef.current.find((f) => f.id === selId);
      const r = it?.room_id ? g.rooms.find((rr) => rr.id === it.room_id) : null;
      if (r) room = r;
    }
    const item = buildDefaultFurniture(type, room);
    updateFurniture((f) => [...f, item]);
    setSelId(item.id ?? null);
    showToast(`已添加 ${type} → ${room.id}`);
  };

  // 从库拖入画布 (阶段 5b / P3): 落点反推 room_id (roomAtGeo); 落点在房外则提示不放置。
  const dropFurniture = useCallback(
    (type: string, clientX: number, clientY: number) => {
      const g = gRef.current;
      if (!g) return;
      const pt = clientToGeo(clientX, clientY);
      if (!pt) return;
      const room = roomAtGeo(g, pt.gx, pt.gy);
      if (!room) {
        showToast('落点在房外,未放置(请拖到房间内)');
        return;
      }
      const item = buildFurnitureAt(type, room, pt.gx, pt.gy);
      updateFurniture((f) => [...f, item]);
      setSelId(item.id ?? null);
      showToast(`已放置 ${type} → ${room.id}`);
    },
    [gRef, clientToGeo, updateFurniture, setSelId, showToast],
  );

  // 定位 (阶段 5b / P2-12): 选中件 + 请求居中。locateFromMsg 从校验文案解析件 id。
  const locate = useCallback(
    (id: string) => {
      const g = gRef.current;
      const it = furnRef.current.find((f) => f.id === id);
      if (!g || !it) return;
      setSelectedIds([id]);
      setZoomReq(furnGeoBox(it, g));
    },
    [gRef, furnRef],
  );
  const locateFromMsg = useCallback(
    (msg: string) => {
      const id = locateFurnInMessage(furnRef.current, msg);
      if (id) locate(id);
    },
    [furnRef, locate],
  );
  const canLocate = useCallback(
    (msg: string) => !!locateFurnInMessage(furnRef.current, msg),
    [furnRef],
  );

  // Delete: 删全部选中件一帧 (P2-7); N=1 即删单件。
  const onDelFurn = () => {
    const ids = selectedIdsRef.current;
    if (!ids.length) return;
    const set = new Set(ids);
    updateFurniture((f) => f.filter((it) => !(it.id && set.has(it.id))));
    setSelectedIds([]);
  };

  // ===== 键盘层操作 (P1-3 / P2-4 / P2-7) ===== //

  const clearSelection = useCallback(() => setSelectedIds([]), []);

  // 全选当前模式可选对象 (Ctrl+A): 家具=全部件。
  const selectAll = useCallback(() => {
    const ids = furnRef.current
      .map((f) => f.id)
      .filter((id): id is string => !!id);
    setSelectedIds(ids);
  }, [furnRef]);

  // 方向键微移 1 单位 (Shift=10): 全部选中件同 delta (P2-7); N=1 即单件。复用 furnAbs/reanchor。
  const nudge = useCallback(
    (dx: number, dy: number) => {
      const g = gRef.current;
      const ids = selectedIdsRef.current;
      if (!g || !ids.length) return;
      const set = new Set(ids);
      updateFurniture((f) =>
        f.map((it) => {
          if (!it.id || !set.has(it.id)) return it;
          const a = furnAbs(it, g);
          const anchorX = (isCircle(it) ? a.cx : a.x) + dx;
          const anchorY = (isCircle(it) ? a.cy : a.y) + dy;
          const centerX = isCircle(it) ? anchorX : anchorX + a.w / 2;
          const centerY = isCircle(it) ? anchorY : anchorY + a.h / 2;
          return {
            ...it,
            ...reanchor(it, g, anchorX, anchorY, centerX, centerY),
          };
        }),
      );
    },
    [gRef, updateFurniture],
  );

  // 复制副本: 深拷贝全部选中 + 偏移 + 新 id + 选中新件 (P2-4 / P2-7)。
  const duplicateSelected = useCallback(() => {
    const ids = selectedIdsRef.current;
    if (!ids.length) return;
    const set = new Set(ids);
    const items = furnRef.current.filter((f) => f.id && set.has(f.id));
    if (!items.length) return;
    const copies = items.map((it) => duplicateFurniture(it, 20, 20));
    updateFurniture((f) => [...f, ...copies]);
    setSelectedIds(copies.map((c) => c.id).filter((id): id is string => !!id));
    showToast(
      copies.length > 1
        ? `已复制 ${copies.length} 件家具副本`
        : '已复制家具副本',
    );
  }, [furnRef, updateFurniture, showToast]);

  const copySelected = useCallback(() => {
    const set = new Set(selectedIdsRef.current);
    clipboardRef.current = furnRef.current.filter((f) => f.id && set.has(f.id));
  }, [furnRef]);

  const paste = useCallback(() => {
    const items = clipboardRef.current;
    if (!items.length) return;
    const copies = items.map((it) => duplicateFurniture(it, 20, 20));
    updateFurniture((f) => [...f, ...copies]);
    setSelectedIds(copies.map((c) => c.id).filter((id): id is string => !!id));
  }, [updateFurniture]);

  // ===== 对齐 / 分布 (P2-7): 纯函数补丁 -> 应用一帧 ===== //
  const alignFurn = useCallback(
    (mode: AlignMode) => {
      const g = gRef.current;
      const ids = selectedIdsRef.current;
      if (!g || ids.length < 2) return;
      const set = new Set(ids);
      const items = furnRef.current.filter((f) => f.id && set.has(f.id));
      const patches = furnAlignPatches(items, g, mode);
      if (!patches.size) return;
      updateFurniture((f) =>
        f.map((it) =>
          it.id && patches.has(it.id) ? { ...it, ...patches.get(it.id) } : it,
        ),
      );
    },
    [gRef, furnRef, updateFurniture],
  );

  const distributeFurn = useCallback(
    (mode: DistributeMode) => {
      const g = gRef.current;
      const ids = selectedIdsRef.current;
      if (!g || ids.length < 3) return;
      const set = new Set(ids);
      const items = furnRef.current.filter((f) => f.id && set.has(f.id));
      const patches = furnDistributePatches(items, g, mode);
      if (!patches.size) return;
      updateFurniture((f) =>
        f.map((it) =>
          it.id && patches.has(it.id) ? { ...it, ...patches.get(it.id) } : it,
        ),
      );
    },
    [gRef, furnRef, updateFurniture],
  );

  const onSaveFurn = async () => {
    if (!canSave) {
      showToast('家具数据尚未成功加载，请先重试');
      return;
    }
    if (savingRef.current) {
      showToast('家具正在保存，请稍候');
      return;
    }
    const snapshot = furnRef.current;
    // 保存前校验 (阶段 5b / P2-12): 件中心出界给 warning (不阻断保存)。
    const g = gRef.current;
    const warns = g ? furnitureSaveWarnings(snapshot, g).map((w) => w.msg) : [];
    // 剥离运行时 id, 保证盘上数据格式 byte 不破。
    const f = stripRuntimeFields(snapshot);
    savingRef.current = true;
    setFurnSave({ saving: true, savedOk: false, error: null, warns });
    try {
      const res = await saveFurniture(
        projectId,
        f as unknown as Record<string, unknown>[],
        schemeId,
      );
      if (res.ok) {
        const unchanged = furnRef.current === snapshot;
        // 校验前置 (升级计划 P1): 保存成功即拉引擎场景校验 (挡门/撞墙/越界/目录外),
        // 出图页才暴露的问题现场就能看到并点击定位。失败静默 (不影响保存反馈)。
        let engineWarns: string[] = [];
        try {
          const scene = await fetchRenderScene(projectId, schemeId);
          engineWarns = (scene.validation?.issues ?? [])
            .filter(
              (i) =>
                (i.level === 'ERROR' || i.level === 'WARN') &&
                !i.code.startsWith('AXON_'),
            )
            .map((i) => {
              const idx = (i as { index?: number }).index;
              const id =
                typeof idx === 'number' ? snapshot[idx]?.id : undefined;
              return `${i.level === 'ERROR' ? '⛔' : '⚠'} ${i.message}${
                id ? `(${id})` : ''
              }`;
            });
        } catch {
          /* 场景校验不可用时不阻断保存 */
        }
        const allWarns = [...warns, ...engineWarns];
        setFurnSave({
          saving: false,
          savedOk: unchanged,
          error: null,
          warns: allWarns,
        });
        // 只允许提交版本清脏；请求期间产生的新版本仍保持未保存。
        if (unchanged) setDirty(false);
        showToast(
          !unchanged
            ? '提交版本已保存，仍有新修改未保存'
            : allWarns.length
            ? `家具已保存 ✓(${allWarns.length} 项校验提示)`
            : '家具已保存 ✓',
        );
      } else {
        setFurnSave({
          saving: false,
          savedOk: false,
          error: '保存失败',
          warns,
        });
      }
    } catch (e) {
      setFurnSave({
        saving: false,
        savedOk: false,
        error: e instanceof Error ? e.message : String(e),
        warns,
      });
      showToast('家具保存请求失败(后端未起?)');
    } finally {
      savingRef.current = false;
    }
  };

  return {
    svgRef,
    contentRef,
    furniture,
    selId,
    setSelId,
    selectedIds,
    setSelectedIds,
    marquee,
    furnSave,
    dirty,
    markDirty,
    snapGuides,
    dragHud,
    blockedId,
    zoomReq,
    clearZoomReq,
    dropFurniture,
    locateFromMsg,
    canLocate,
    resetSelection,
    clearSelection,
    selectAll,
    alignFurn,
    distributeFurn,
    onFurnItemDown,
    onFurnResizeDown,
    onFurnRotateDown,
    onFurnSvgDown,
    onFurnSvgMove,
    onFurnSvgUp,
    onFurnSvgCancel,
    onSetFurnField,
    onAddFurn,
    onDelFurn,
    bringToFront,
    sendToBack,
    nudge,
    duplicateSelected,
    copySelected,
    paste,
    onSaveFurn,
  };
}

export type FurnitureEditor = ReturnType<typeof useFurnitureEditor>;
