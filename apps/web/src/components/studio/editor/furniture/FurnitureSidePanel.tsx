'use client';

import React, { useState } from 'react';
import type { Furniture } from 'lib/floorplan/furniture';
import { FURN_TYPES, furnZh, isCircle } from 'lib/floorplan/furniture';

export interface FurnSaveState {
  saving: boolean;
  savedOk: boolean;
  error: string | null;
}

interface Props {
  furniture: Furniture[];
  selectedIndex: number | null;
  saveState: FurnSaveState;
  onSetField: (field: keyof Furniture, value: string | number) => void;
  onAdd: (type: string) => void;
  onDelete: () => void;
  onSave: () => void;
}

const labelCls = 'mt-2 block text-xs text-gray-500 dark:text-gray-300';
const inputCls =
  'w-full rounded-md border border-gray-300 bg-white px-2 py-1 text-sm text-navy-700 dark:border-white/10 dark:bg-navy-900 dark:text-white';

const ORIENTS: Array<'N' | 'S' | 'W' | 'E'> = ['N', 'S', 'W', 'E'];

// 家具侧栏: 选中件改 t/w/h/orient/label/color; 添加(选类型→落当前房); 删除; 💾 保存。
export default function FurnitureSidePanel({
  furniture,
  selectedIndex,
  saveState,
  onSetField,
  onAdd,
  onDelete,
  onSave,
}: Props) {
  const [addType, setAddType] = useState<string>(FURN_TYPES[0]);
  const item =
    selectedIndex !== null && selectedIndex >= 0
      ? furniture[selectedIndex]
      : null;

  return (
    <div className="flex w-full max-w-[340px] flex-col gap-3 rounded-2xl border border-gray-200 bg-white p-4 text-sm dark:border-white/10 dark:bg-navy-800 dark:text-white">
      <h2 className="text-base font-bold text-navy-700 dark:text-white">
        家具编辑
      </h2>

      {/* 添加 */}
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <label className={labelCls}>添加家具(落当前房)</label>
          <select
            className={inputCls}
            value={addType}
            onChange={(e) => setAddType(e.target.value)}
          >
            {FURN_TYPES.map((t) => (
              <option key={t} value={t}>
                {furnZh(t)} · {t}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          onClick={() => onAdd(addType)}
          className="rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-600"
        >
          ＋添加
        </button>
      </div>
      <p className="text-xs text-gray-400">
        共 {furniture.length} 件 · 拖动家具改位置(落点反推所属房间)。
      </p>

      {/* 属性区 */}
      <div className="rounded-xl border border-gray-100 p-3 dark:border-white/5">
        {item ? (
          <div>
            <p className="font-semibold">
              选中 #{selectedIndex} · {furnZh(item.t)}
              {item.room_id ? ` · ${item.room_id}` : ''}
            </p>

            <label className={labelCls}>类型 type</label>
            <select
              className={inputCls}
              value={item.t}
              onChange={(e) => onSetField('t', e.target.value)}
            >
              {FURN_TYPES.map((t) => (
                <option key={t} value={t}>
                  {furnZh(t)} · {t}
                </option>
              ))}
            </select>

            {isCircle(item) ? (
              <div className="mt-2">
                <label className={labelCls}>半径 r</label>
                <input
                  type="number"
                  className={inputCls}
                  value={item.r ?? 20}
                  onChange={(e) => onSetField('r', Number(e.target.value))}
                />
              </div>
            ) : (
              <>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <div>
                    <label className={labelCls}>宽 w</label>
                    <input
                      type="number"
                      className={inputCls}
                      value={item.w ?? 0}
                      onChange={(e) => onSetField('w', Number(e.target.value))}
                    />
                  </div>
                  <div>
                    <label className={labelCls}>高 h</label>
                    <input
                      type="number"
                      className={inputCls}
                      value={item.h ?? 0}
                      onChange={(e) => onSetField('h', Number(e.target.value))}
                    />
                  </div>
                </div>
                <label className={labelCls}>朝向 orient(床头/沙发背所在侧)</label>
                <div className="mt-1 flex gap-1">
                  {ORIENTS.map((o) => (
                    <button
                      key={o}
                      type="button"
                      onClick={() => onSetField('orient', o)}
                      className={`flex-1 rounded-md px-0 py-1 text-xs font-medium ${
                        item.orient === o
                          ? 'bg-brand-500 text-white'
                          : 'bg-gray-100 text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white'
                      }`}
                    >
                      {o}
                    </button>
                  ))}
                </div>
              </>
            )}

            <label className={labelCls}>标签 label(空=显示中文名)</label>
            <input
              className={inputCls}
              value={item.label ? String(item.label) : ''}
              onChange={(e) => onSetField('label', e.target.value)}
            />

            <label className={labelCls}>颜色 color(空=按类型默认)</label>
            <input
              className={inputCls}
              value={item.color ? String(item.color) : ''}
              onChange={(e) => onSetField('color', e.target.value)}
              placeholder="#rrggbb"
            />

            <p className="mt-2 text-xs text-gray-400">尺寸单位 1=10mm(w=300 即 3m)。</p>

            <button
              type="button"
              onClick={onDelete}
              className="mt-3 rounded-lg bg-red-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600"
            >
              🗑 删除家具
            </button>
          </div>
        ) : (
          <p className="text-xs text-gray-400">点画布上的家具选中以编辑。</p>
        )}
      </div>

      {/* 保存状态 */}
      <div className="rounded-xl border border-gray-100 p-3 dark:border-white/5">
        {saveState.error ? (
          <p className="text-xs text-red-500">⛔ {saveState.error}</p>
        ) : saveState.savedOk ? (
          <p className="text-xs text-green-500">✓ 已保存</p>
        ) : (
          <p className="text-xs text-gray-400">编辑后点保存写盘。</p>
        )}
      </div>

      <button
        type="button"
        onClick={onSave}
        disabled={saveState.saving}
        className="rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
      >
        {saveState.saving ? '保存中…' : '💾 保存家具'}
      </button>
    </div>
  );
}
