'use client';

import React, { useMemo, useState } from 'react';
import {
  furnCategories,
  furnZh,
  FURN_DND_MIME,
} from 'lib/floorplan/furniture';
import FurnThumb from './FurnThumb';

interface Props {
  // 快速添加到当前房 (兜底): 点击/Enter 库项触发。
  onQuickAdd: (type: string) => void;
}

// 家具库 (阶段 5b / P3): 按类别分组 + 搜索 + 缩略图 + 拖入画布。
// - 点击/Enter 库项 = 快速添加到当前房 (兜底)。
// - 拖动库项 = 拖入画布 (drop 落点反推 room_id, 见 FurnitureMode onDrop)。
// 每项为原生 <button> (role=button) + draggable, 既键盘可达又支持 HTML5 拖拽。
export default function FurnitureLibrary({ onQuickAdd }: Props) {
  const [query, setQuery] = useState('');
  const cats = useMemo(() => furnCategories(), []);
  const q = query.trim().toLowerCase();

  // 搜索过滤: 匹配中文名或类型 key。
  const filtered = useMemo(
    () =>
      cats
        .map((c) => ({
          ...c,
          types: c.types.filter(
            (t) =>
              !q ||
              t.toLowerCase().includes(q) ||
              furnZh(t).toLowerCase().includes(q),
          ),
        }))
        .filter((c) => c.types.length > 0),
    [cats, q],
  );

  const onDragStart = (e: React.DragEvent, type: string) => {
    e.dataTransfer.setData(FURN_DND_MIME, type);
    // 兼容性: 部分浏览器需 text/plain 才允许拖拽。
    e.dataTransfer.setData('text/plain', type);
    e.dataTransfer.effectAllowed = 'copy';
  };

  return (
    <div data-testid="furniture-library">
      <input
        type="search"
        data-testid="furn-lib-search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="搜索家具(名称/类型)…"
        aria-label="搜索家具"
        className="w-full rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-navy-700 outline-none focus:border-brand-400 dark:border-white/10 dark:bg-navy-900 dark:text-white"
      />
      <p className="mt-1 text-xs text-gray-400">
        点击 = 加到当前房 · 拖入画布 = 落点放置
      </p>

      <div className="mt-2 max-h-[320px] space-y-3 overflow-y-auto pr-1">
        {filtered.length === 0 && (
          <p className="text-xs text-gray-400">无匹配家具</p>
        )}
        {filtered.map((c) => (
          <div key={c.key} data-testid={`furn-cat-${c.key}`}>
            <h4 className="mb-1 text-xs font-semibold text-gray-500 dark:text-gray-300">
              {c.label}
            </h4>
            <div className="grid grid-cols-3 gap-1.5">
              {c.types.map((t) => (
                <button
                  key={t}
                  type="button"
                  draggable
                  data-testid={`furn-lib-item-${t}`}
                  data-furn-type={t}
                  onDragStart={(e) => onDragStart(e, t)}
                  onClick={() => onQuickAdd(t)}
                  aria-label={`${furnZh(t)} ${t}`}
                  title={`${furnZh(t)} · ${t}`}
                  className="flex cursor-grab flex-col items-center gap-0.5 rounded-lg border border-gray-200 px-1 py-1.5 text-[10px] text-navy-700 hover:bg-gray-50 active:cursor-grabbing dark:border-white/10 dark:text-white dark:hover:bg-white/5"
                >
                  <FurnThumb type={t} />
                  <span className="max-w-full truncate">{furnZh(t)}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
