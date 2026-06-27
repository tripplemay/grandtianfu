'use client';

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { fetchGeometry, postDerive, saveGeometry } from 'lib/studioApi';
import type {
  Geometry,
  DeriveResult,
  Room,
  Opening,
  FreeWall,
  WallRaw,
  Rect,
} from 'lib/floorplan/types';
import {
  readOrigin,
  readViewBox,
  readGrid,
  FALLBACK_ORIGIN,
  FALLBACK_VIEWBOX,
} from 'lib/floorplan/coords';
import {
  roomById,
  crossSpaceOverlap,
  computeMove,
  computeResize,
  computeOpeningSpan,
  hostExtent,
  buildDefaultDoor,
  buildFreeWall,
  findOverlapErrors,
  overlapErrorMessage,
} from 'lib/floorplan/geometry';
import EditorStage, { type EditorSelection } from './EditorStage';
import GeometrySidePanel, {
  type SaveState,
} from './geometry/GeometrySidePanel';

interface Props {
  projectId: string;
}

type LoadState = 'idle' | 'loading' | 'ready' | 'error';

type Drag =
  | { type: 'move'; roomId: string; orig: Rect; sx: number; sy: number }
  | { type: 'resize'; roomId: string; orig: Rect; handle: string }
  | {
      type: 'op';
      opId: string;
      ospan: [number, number];
      s: number;
      host: [number, number] | null;
    };

const EMPTY_SELECTION: EditorSelection = {
  room: null,
  room2: null,
  opening: null,
  freeWall: null,
};
const EMPTY_SAVE: SaveState = {
  saving: false,
  errors: [],
  warns: [],
  savedOk: false,
};

// 几何编辑器状态容器 (§①-⑨)。受控 inline SVG; 同源 /api; React18.3.1。
export default function FloorplanEditor({ projectId }: Props) {
  const [G, setG] = useState<Geometry | null>(null);
  const [derived, setDerived] = useState<DeriveResult | null>(null);
  const [loadState, setLoadState] = useState<LoadState>('idle');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selection, setSelection] = useState<EditorSelection>(EMPTY_SELECTION);
  const [insertMode, setInsertMode] = useState<'door' | 'freewall' | null>(
    null,
  );
  const [fwPts, setFwPts] = useState<Array<[number, number]>>([]);
  const [saveState, setSaveState] = useState<SaveState>(EMPTY_SAVE);
  const [toast, setToast] = useState<string | null>(null);

  const svgRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef<Drag | null>(null);
  const gRef = useRef<Geometry | null>(null);
  const deriveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---- 不可变 G 更新, 同步 gRef (供拖拽/debounce 读最新值) ---- //
  const updateG = useCallback((updater: (g: Geometry) => Geometry) => {
    setG((prev) => {
      if (!prev) return prev;
      const next = updater(prev);
      gRef.current = next;
      return next;
    });
  }, []);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2200);
  }, []);

  // ---- 派生 (实时内存, §⑧⑨) ---- //
  const deriveNow = useCallback(async (g: Geometry) => {
    try {
      const d = await postDerive(g);
      setDerived(d as unknown as DeriveResult);
    } catch {
      /* 派生失败静默 (保存时会有显式校验) */
    }
  }, []);

  const deriveSoon = useCallback(() => {
    // 编辑后重置上次保存状态, 让状态栏回到实时派生视图。
    setSaveState((s) => (s.savedOk || s.errors.length ? EMPTY_SAVE : s));
    if (deriveTimer.current) clearTimeout(deriveTimer.current);
    deriveTimer.current = setTimeout(() => {
      if (gRef.current) void deriveNow(gRef.current);
    }, 200);
  }, [deriveNow]);

  // ---- 载入 geometry -> derive (§⑧) ---- //
  useEffect(() => {
    let alive = true;
    (async () => {
      setLoadState('loading');
      setLoadError(null);
      try {
        const g = (await fetchGeometry(projectId)) as unknown as Geometry;
        if (!alive) return;
        gRef.current = g;
        setG(g);
        const d = await postDerive(g);
        if (!alive) return;
        setDerived(d as unknown as DeriveResult);
        setLoadState('ready');
      } catch (e) {
        if (!alive) return;
        setLoadError(e instanceof Error ? e.message : String(e));
        setLoadState('error');
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId]);

  useEffect(
    () => () => {
      if (deriveTimer.current) clearTimeout(deriveTimer.current);
      if (toastTimer.current) clearTimeout(toastTimer.current);
    },
    [],
  );

  // ---- 几何坐标换算 (§①) ---- //
  const getGeoPoint = useCallback(
    (e: React.PointerEvent): { gx: number; gy: number } | null => {
      const svg = svgRef.current;
      if (!svg) return null;
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const ctm = svg.getScreenCTM();
      if (!ctm) return null;
      const p = pt.matrixTransform(ctm.inverse());
      const origin = gRef.current ? readOrigin(gRef.current) : FALLBACK_ORIGIN;
      return { gx: p.x - origin[0], gy: p.y - origin[1] };
    },
    [],
  );

  // ===== 指针交互 (§②③④⑤⑥) ===== //
  const onRoomPointerDown = (e: React.PointerEvent, room: Room) => {
    if (insertMode) return; // 插入模式下不拖房, 让事件冒泡到背景 (freewall 落点)
    e.stopPropagation();
    const pt = getGeoPoint(e);
    if (!pt) return;
    if (e.shiftKey) {
      setSelection((s) => ({ ...s, room2: room.id }));
    } else {
      setSelection({
        room: room.id,
        room2: null,
        opening: null,
        freeWall: null,
      });
    }
    dragRef.current = {
      type: 'move',
      roomId: room.id,
      orig: [...room.rect] as Rect,
      sx: pt.gx,
      sy: pt.gy,
    };
    svgRef.current?.setPointerCapture(e.pointerId);
  };

  const onHandlePointerDown = (
    e: React.PointerEvent,
    room: Room,
    handle: string,
  ) => {
    e.stopPropagation();
    setSelection({ room: room.id, room2: null, opening: null, freeWall: null });
    dragRef.current = {
      type: 'resize',
      roomId: room.id,
      orig: [...room.rect] as Rect,
      handle,
    };
    svgRef.current?.setPointerCapture(e.pointerId);
  };

  const onOpeningPointerDown = (e: React.PointerEvent, op: Opening) => {
    e.stopPropagation();
    setSelection({ room: null, room2: null, opening: op.id, freeWall: null });
    const pt = getGeoPoint(e);
    if (!pt) return;
    const s = op.wall.axis === 'v' ? pt.gy : pt.gx;
    const host = hostExtent(op, derived?._walls_raw);
    dragRef.current = {
      type: 'op',
      opId: op.id,
      ospan: [...op.wall.span] as [number, number],
      s,
      host,
    };
    svgRef.current?.setPointerCapture(e.pointerId);
  };

  // 开门模式: 点墙插默认门 (§⑤)
  const onWallPointerDown = (e: React.PointerEvent, wall: WallRaw) => {
    if (insertMode !== 'door') return;
    e.stopPropagation();
    const pt = getGeoPoint(e);
    if (!pt || !gRef.current) return;
    const coord = wall.axis === 'v' ? pt.gy : pt.gx;
    const door = buildDefaultDoor(gRef.current, wall, coord);
    updateG((g) => ({ ...g, openings: [...g.openings, door] }));
    setSelection({ room: null, room2: null, opening: door.id, freeWall: null });
    setInsertMode(null);
    deriveSoon();
  };

  const onFreeWallPointerDown = (e: React.PointerEvent, fw: FreeWall) => {
    e.stopPropagation();
    setSelection({ room: null, room2: null, opening: null, freeWall: fw.id });
  };

  // 背景: 自由墙落点 / 空白清选 (§⑥)
  const onSvgPointerDown = (e: React.PointerEvent) => {
    const target = e.target as Element;
    const isBg =
      target === e.currentTarget || target.getAttribute('data-bg') === '1';
    if (!isBg) return;
    if (insertMode === 'freewall') {
      const pt = getGeoPoint(e);
      if (!pt) return;
      const grid = readGrid(gRef.current);
      const gx = Math.round(pt.gx / grid) * grid;
      const gy = Math.round(pt.gy / grid) * grid;
      setFwPts((prev) => {
        const next: Array<[number, number]> = [...prev, [gx, gy]];
        if (next.length === 2) {
          const fw = buildFreeWall(next[0], next[1]);
          if (fw) {
            updateG((g) => ({
              ...g,
              free_walls: [...(g.free_walls ?? []), fw],
            }));
            setSelection({
              room: null,
              room2: null,
              opening: null,
              freeWall: fw.id,
            });
            deriveSoon();
          } else {
            showToast('自由墙太短,已忽略');
          }
          setInsertMode(null);
          return [];
        }
        return next;
      });
      return;
    }
    setSelection(EMPTY_SELECTION);
  };

  const onSvgPointerMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const pt = getGeoPoint(e);
    if (!pt) return;
    const alt = e.altKey;
    if (d.type === 'move') {
      updateG((g) => {
        const room = roomById(g, d.roomId);
        if (!room) return g;
        const rect = computeMove(
          g,
          room,
          d.orig,
          pt.gx - d.sx,
          pt.gy - d.sy,
          alt,
        );
        return {
          ...g,
          rooms: g.rooms.map((r) => (r.id === d.roomId ? { ...r, rect } : r)),
        };
      });
    } else if (d.type === 'resize') {
      updateG((g) => {
        const room = roomById(g, d.roomId);
        if (!room) return g;
        const rect = computeResize(
          g,
          room,
          d.orig,
          d.handle,
          pt.gx,
          pt.gy,
          alt,
        );
        return {
          ...g,
          rooms: g.rooms.map((r) => (r.id === d.roomId ? { ...r, rect } : r)),
        };
      });
    } else {
      updateG((g) => {
        const op = g.openings.find((o) => o.id === d.opId);
        if (!op) return g;
        const cur = op.wall.axis === 'v' ? pt.gy : pt.gx;
        const span = computeOpeningSpan(op, d.ospan, d.s, cur, d.host);
        return {
          ...g,
          openings: g.openings.map((o) =>
            o.id === d.opId ? { ...o, wall: { ...o.wall, span } } : o,
          ),
        };
      });
    }
  };

  const onSvgPointerUp = () => {
    if (dragRef.current) {
      dragRef.current = null;
      deriveSoon();
    }
  };

  // ===== 侧栏编辑 ===== //
  const onSetRoom = (field: 'type' | 'space', value: string) => {
    if (!selection.room) return;
    updateG((g) => ({
      ...g,
      rooms: g.rooms.map((r) =>
        r.id === selection.room ? { ...r, [field]: value } : r,
      ),
    }));
    deriveSoon();
  };

  const onSetLabel = (value: string) => {
    if (!selection.room) return;
    updateG((g) => ({
      ...g,
      rooms: g.rooms.map((r) =>
        r.id === selection.room
          ? { ...r, label: { ...(r.label ?? {}), zh: value } }
          : r,
      ),
    }));
  };

  const onSetRect = (i: number, value: number) => {
    const g = gRef.current;
    if (!g || !selection.room) return;
    const room = roomById(g, selection.room);
    if (!room) return;
    const nr = [...room.rect] as Rect;
    nr[i] = value;
    if (!crossSpaceOverlap(g, room, nr)) {
      updateG((gg) => ({
        ...gg,
        rooms: gg.rooms.map((r) => (r.id === room.id ? { ...r, rect: nr } : r)),
      }));
      deriveSoon();
    } else {
      showToast('会跨 space 重叠,已拒绝');
    }
  };

  const onSetOp = (field: string, value: string | boolean) => {
    if (!selection.opening) return;
    updateG((g) => ({
      ...g,
      openings: g.openings.map((o) =>
        o.id === selection.opening ? { ...o, [field]: value } : o,
      ),
    }));
    deriveSoon();
  };

  const onSetOpWall = (field: 'axis' | 'at', value: string | number) => {
    if (!selection.opening) return;
    updateG((g) => ({
      ...g,
      openings: g.openings.map((o) =>
        o.id === selection.opening
          ? { ...o, wall: { ...o.wall, [field]: value } }
          : o,
      ),
    }));
    deriveSoon();
  };

  const onSetSpan = (i: number, value: number) => {
    if (!selection.opening) return;
    updateG((g) => ({
      ...g,
      openings: g.openings.map((o) => {
        if (o.id !== selection.opening) return o;
        const span: [number, number] = [...o.wall.span] as [number, number];
        span[i] = value;
        return { ...o, wall: { ...o.wall, span } };
      }),
    }));
    deriveSoon();
  };

  const onDelOp = () => {
    if (!selection.opening) return;
    updateG((g) => ({
      ...g,
      openings: g.openings.filter((o) => o.id !== selection.opening),
    }));
    setSelection((s) => ({ ...s, opening: null }));
    deriveSoon();
  };

  const onSetFw = (field: string, value: string | number) => {
    if (!selection.freeWall) return;
    updateG((g) => ({
      ...g,
      free_walls: (g.free_walls ?? []).map((f) =>
        f.id === selection.freeWall ? { ...f, [field]: value } : f,
      ),
    }));
    deriveSoon();
  };

  const onSetFwSpan = (i: number, value: number) => {
    if (!selection.freeWall) return;
    updateG((g) => ({
      ...g,
      free_walls: (g.free_walls ?? []).map((f) => {
        if (f.id !== selection.freeWall) return f;
        const span: [number, number] = [...f.span] as [number, number];
        span[i] = value;
        return { ...f, span };
      }),
    }));
    deriveSoon();
  };

  const onDelFw = () => {
    if (!selection.freeWall) return;
    updateG((g) => ({
      ...g,
      free_walls: (g.free_walls ?? []).filter(
        (f) => f.id !== selection.freeWall,
      ),
    }));
    setSelection((s) => ({ ...s, freeWall: null }));
    deriveSoon();
  };

  // 打通: 选中两房 -> 标记同一合并组 (intentional merge); 两房 space 也设为同一,
  // 沿用现合并语义 (同 space=开放无墙)。合并组 id 复用首房已有 merge, 否则新建。
  const onMerge = () => {
    if (!selection.room || !selection.room2) {
      showToast('需先选两个房间(Shift+点第二个)');
      return;
    }
    const g = gRef.current;
    if (!g) return;
    const a = roomById(g, selection.room);
    if (!a) return;
    const mid = a.merge || 'm_' + (Date.now() % 100000);
    updateG((gg) => ({
      ...gg,
      rooms: gg.rooms.map((r) =>
        r.id === selection.room || r.id === selection.room2
          ? { ...r, space: a.space, merge: mid }
          : r,
      ),
    }));
    deriveSoon();
    showToast(`已打通 → 合并组 ${mid}`);
  };

  // 分隔: 清除选中房的 merge + 拆到新 space (§⑦)。拆后若仍重叠, 实时校验报 ERROR。
  const onSplit = () => {
    if (!selection.room) {
      showToast('需先选一个房间');
      return;
    }
    const g = gRef.current;
    if (!g) return;
    const r = roomById(g, selection.room);
    if (!r) return;
    const nid = 'sp' + (Date.now() % 100000);
    const old = g.spaces[r.space] ?? { category: 'interior', label: r.id };
    const newSpace = {
      category: old.category,
      label: r.label?.zh || r.id,
      style: (old.style as string) || 'solid',
    };
    updateG((gg) => ({
      ...gg,
      spaces: { ...gg.spaces, [nid]: newSpace },
      rooms: gg.rooms.map((rr) =>
        rr.id === r.id ? { ...rr, space: nid, merge: undefined } : rr,
      ),
    }));
    deriveSoon();
    showToast(`已分隔 → 新 space ${nid}`);
  };

  const onToggleInsert = (mode: 'door' | 'freewall') => {
    setInsertMode((prev) => (prev === mode ? null : mode));
    setFwPts([]);
    showToast(
      mode === 'door'
        ? '开门模式:点一段墙插入默认门'
        : '自由墙:依次点两点(自动正交)',
    );
  };

  // 校验并保存 (§⑨)
  const onSave = async () => {
    const g = gRef.current;
    if (!g) {
      showToast('几何未加载');
      return;
    }
    // 客户端先拦重叠冲突 (后端 /save-geometry 也会 400, 此处给即时反馈)。
    const overlaps = findOverlapErrors(g.rooms);
    if (overlaps.length) {
      const msgs = overlaps.map(overlapErrorMessage);
      setSaveState({ saving: false, errors: msgs, warns: [], savedOk: false });
      showToast('存在重叠冲突,先「打通」标记合并或拖开');
      return;
    }
    setSaveState((s) => ({ ...s, saving: true }));
    try {
      const res = await saveGeometry(projectId, g);
      if (res.ok) {
        setSaveState({
          saving: false,
          errors: [],
          warns: res.warns,
          savedOk: true,
        });
        if (res.derived) setDerived(res.derived as unknown as DeriveResult);
        showToast('几何已保存 ✓');
      } else {
        setSaveState({
          saving: false,
          errors: res.errors ?? ['校验失败'],
          warns: res.warns,
          savedOk: false,
        });
        showToast('校验失败(ERROR),未保存');
      }
    } catch (e) {
      setSaveState({
        saving: false,
        errors: [e instanceof Error ? e.message : String(e)],
        warns: [],
        savedOk: false,
      });
      showToast('保存请求失败(后端未起?)');
    }
  };

  // 客户端实时算重叠冲突 (§④, 与后端 geometry.validate 同口径): 净矩形重叠且未标
  // 记同一合并组 -> ERROR。用于面板红字列出 + 涉及房间红色描边 + 禁用 💾。
  const overlapPairs = useMemo(
    () => (G ? findOverlapErrors(G.rooms) : []),
    [G],
  );
  const overlapMsgs = useMemo(
    () => overlapPairs.map(overlapErrorMessage),
    [overlapPairs],
  );
  const errorRoomIds = useMemo(() => {
    const s = new Set<string>();
    overlapPairs.forEach((p) => {
      s.add(p.a);
      s.add(p.b);
    });
    return s;
  }, [overlapPairs]);

  const viewBox = G ? readViewBox(G) : FALLBACK_VIEWBOX;
  const origin = G ? readOrigin(G) : FALLBACK_ORIGIN;

  return (
    <div className="w-full">
      <div className="mb-3 flex flex-wrap items-center gap-3 text-sm text-gray-600 dark:text-white">
        <span className="font-semibold">户型 {projectId}</span>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            loadState === 'ready'
              ? 'bg-green-200 text-green-800'
              : loadState === 'error'
              ? 'bg-red-200 text-red-800'
              : 'bg-amber-200 text-amber-800'
          }`}
        >
          {loadState === 'ready'
            ? '已就绪'
            : loadState === 'error'
            ? '错误'
            : '加载中'}
        </span>
        {insertMode && (
          <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs text-brand-700">
            {insertMode === 'door' ? '开门模式' : '自由墙模式'}
          </span>
        )}
      </div>

      {loadState === 'error' && (
        <div className="dark:bg-red-950 mb-3 rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:text-red-300">
          <p className="font-semibold">
            无法加载几何 / 派生数据(后端可能未启动)。
          </p>
          <p className="mt-1 break-all opacity-80">{loadError}</p>
        </div>
      )}

      <div className="flex flex-col gap-4 lg:flex-row">
        <div className="min-w-0 flex-1 overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-white/10 dark:bg-navy-800">
          {G ? (
            <EditorStage
              svgRef={svgRef}
              viewBox={viewBox}
              origin={origin}
              geometry={G}
              derived={derived}
              selection={selection}
              insertMode={insertMode}
              fwPts={fwPts}
              errorRoomIds={errorRoomIds}
              onSvgPointerDown={onSvgPointerDown}
              onSvgPointerMove={onSvgPointerMove}
              onSvgPointerUp={onSvgPointerUp}
              onRoomPointerDown={onRoomPointerDown}
              onHandlePointerDown={onHandlePointerDown}
              onOpeningPointerDown={onOpeningPointerDown}
              onWallPointerDown={onWallPointerDown}
              onFreeWallPointerDown={onFreeWallPointerDown}
            />
          ) : (
            <div className="p-8 text-sm text-gray-400">加载中…</div>
          )}
        </div>

        {G && (
          <GeometrySidePanel
            geometry={G}
            derived={derived}
            selection={selection}
            insertMode={insertMode}
            saveState={saveState}
            overlapErrors={overlapMsgs}
            onSetRoom={onSetRoom}
            onSetLabel={onSetLabel}
            onSetRect={onSetRect}
            onSetOp={onSetOp}
            onSetOpWall={onSetOpWall}
            onSetSpan={onSetSpan}
            onDelOp={onDelOp}
            onSetFw={onSetFw}
            onSetFwSpan={onSetFwSpan}
            onDelFw={onDelFw}
            onMerge={onMerge}
            onSplit={onSplit}
            onToggleInsert={onToggleInsert}
            onSave={onSave}
          />
        )}
      </div>

      {toast && (
        <div className="fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-navy-900 px-4 py-2 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}
