'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  fetchGeometry,
  postDerive,
  type DeriveResult,
  type Geometry,
  type WallTuple,
} from 'lib/studioApi';

type LoadState = 'idle' | 'loading' | 'ready' | 'error';

interface Props {
  projectId: string;
}

// 默认 viewBox(后端未起时给一个占位,避免 NaN)
const FALLBACK_VIEWBOX: [number, number, number, number] = [0, 0, 2200, 1800];
const FALLBACK_ORIGIN: [number, number] = [150, 250];

export default function FloorplanPreview({ projectId }: Props) {
  const [state, setState] = useState<LoadState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [geometry, setGeometry] = useState<Geometry | null>(null);
  const [derived, setDerived] = useState<DeriveResult | null>(null);

  const load = useCallback(async () => {
    setState('loading');
    setError(null);
    try {
      const g = await fetchGeometry(projectId);
      setGeometry(g);
      const d = await postDerive(g);
      setDerived(d);
      setState('ready');
    } catch (e) {
      // 优雅降级:后端未起 / 网络失败时显示错误,不崩溃。
      setError(e instanceof Error ? e.message : String(e));
      setState('error');
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const viewBox = geometry?.meta?.canvas_viewbox ?? FALLBACK_VIEWBOX;
  const origin = geometry?.meta?.origin ?? FALLBACK_ORIGIN;
  const walls = derived?.walls ?? [];

  return (
    <div className="w-full">
      <div className="mb-3 flex items-center gap-3 text-sm text-gray-600 dark:text-white">
        <span className="font-semibold">户型 {projectId}</span>
        <StatusBadge state={state} />
        {derived && (
          <span className="text-gray-500 dark:text-gray-300">
            墙 {walls.length} · 门 {derived.doors.length} · 窗 {derived.windows.length}
          </span>
        )}
        <button
          type="button"
          onClick={() => void load()}
          className="ml-auto rounded-lg bg-brand-500 px-3 py-1 text-xs font-medium text-white hover:bg-brand-600"
        >
          重新加载
        </button>
      </div>

      {state === 'error' && (
        <div className="mb-3 rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
          <p className="font-semibold">无法加载几何 / 派生数据(后端可能未启动)。</p>
          <p className="mt-1 break-all opacity-80">{error}</p>
          <p className="mt-1 opacity-70">
            预期数据源:<code>GET /api/projects/{projectId}/geometry</code> →{' '}
            <code>POST /api/derive</code>。
          </p>
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-white/10 dark:bg-navy-800">
        <svg
          viewBox={viewBox.join(' ')}
          xmlns="http://www.w3.org/2000/svg"
          className="block h-auto w-full"
          style={{ background: '#0b1437' }}
        >
          {state === 'loading' && (
            <text x="40" y="60" fill="#8f9bba" fontSize="40">
              加载中…
            </text>
          )}
          {walls.map((w, i) => (
            <WallLine key={i} wall={w} origin={origin} />
          ))}
        </svg>
      </div>
    </div>
  );
}

function WallLine({ wall, origin }: { wall: WallTuple; origin: [number, number] }) {
  const [ax, ay, bx, by, ext, style] = wall;
  const x1 = ax + origin[0];
  const y1 = ay + origin[1];
  const x2 = bx + origin[0];
  const y2 = by + origin[1];
  return (
    <line
      x1={x1}
      y1={y1}
      x2={x2}
      y2={y2}
      stroke={ext ? '#e2e8f0' : '#94a3b8'}
      strokeWidth={ext ? 8 : 5}
      strokeLinecap="round"
      strokeDasharray={style === 'dashed' ? '18 12' : undefined}
    />
  );
}

function StatusBadge({ state }: { state: LoadState }) {
  const map: Record<LoadState, { label: string; cls: string }> = {
    idle: { label: '待加载', cls: 'bg-gray-200 text-gray-700' },
    loading: { label: '加载中', cls: 'bg-amber-200 text-amber-800' },
    ready: { label: '已就绪', cls: 'bg-green-200 text-green-800' },
    error: { label: '错误', cls: 'bg-red-200 text-red-800' },
  };
  const { label, cls } = map[state];
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{label}</span>;
}
