'use client';

import React from 'react';
import type { Furniture, Orient } from 'lib/floorplan/furniture';
import { FURN_TYPES, furnZh, isCircle } from 'lib/floorplan/furniture';
import type { AlignMode, DistributeMode } from 'lib/floorplan/geometry';
import { SidePanel, PanelSection } from '../../ui/SidePanel';
import { TextRow, NumberRow, SelectRow, Field } from '../../ui/fields';
import { SegmentedControl, SaveButton, DangerButton } from '../../ui/buttons';
import { StatusLines } from '../../ui/status';
import EmptyState from '../../ui/EmptyState';
import AlignBar from '../AlignBar';
import FurnitureLibrary from './FurnitureLibrary';

export interface FurnSaveState {
  saving: boolean;
  savedOk: boolean;
  error: string | null;
  // 出界等保存校验警告 (阶段 5b / P2-12): 不阻断保存, 可点击定位。
  warns: string[];
}

interface Props {
  furniture: Furniture[];
  selectedId: string | null;
  selectedCount: number; // 多选数量 (阶段 5a / P2-7): >=2 显示对齐/分布工具条。
  saveState: FurnSaveState;
  dirty: boolean; // 防丢失 (P1-6): 有未保存改动。
  onSetField: (field: keyof Furniture, value: string | number) => void;
  onAdd: (type: string) => void;
  onDelete: () => void;
  onBringToFront: () => void;
  onSendToBack: () => void;
  onAlign: (mode: AlignMode) => void;
  onDistribute: (mode: DistributeMode) => void;
  onSave: () => void;
  // 定位校验反馈 (阶段 5b / P2-12): 出界警告可点 -> 选中并居中对应家具。
  canLocate: (msg: string) => boolean;
  onLocate: (msg: string) => void;
}

const ORIENTS: Orient[] = ['N', 'S', 'W', 'E'];

const furnLabel = (t: string) => `${furnZh(t)} · ${t}`;

// 家具侧栏: 选中件改 t/w/h/orient/label/color; 添加(选类型→落当前房); 删除; 💾 保存。
export default function FurnitureSidePanel({
  furniture,
  selectedId,
  selectedCount,
  saveState,
  dirty,
  onSetField,
  onAdd,
  onDelete,
  onBringToFront,
  onSendToBack,
  onAlign,
  onDistribute,
  onSave,
  canLocate,
  onLocate,
}: Props) {
  const idx =
    selectedId !== null ? furniture.findIndex((f) => f.id === selectedId) : -1;
  const item = idx >= 0 ? furniture[idx] : null;

  return (
    <SidePanel title="家具编辑">
      {/* 家具库 (阶段 5b / P3): 分类 + 搜索 + 缩略图; 点击=加当前房, 拖入画布=落点放置 */}
      <FurnitureLibrary onQuickAdd={onAdd} />
      <p className="text-xs text-gray-400">
        共 {furniture.length} 件 · 拖动家具改位置(落点反推所属房间)。Shift+点
        多选 · 空白拖框选 · Ctrl+A 全选。
      </p>

      {/* 多选对齐 / 分布 (阶段 5a / P2-7) */}
      <AlignBar
        count={selectedCount}
        onAlign={onAlign}
        onDistribute={onDistribute}
      />

      {/* 属性区 */}
      <PanelSection>
        {item ? (
          <div>
            <p className="font-semibold">
              选中 #{idx} · {furnZh(item.t)}
              {item.room_id ? ` · ${item.room_id}` : ''}
            </p>

            <SelectRow
              label="类型 type"
              value={item.t}
              options={FURN_TYPES}
              onChange={(v) => onSetField('t', v)}
              renderLabel={furnLabel}
            />

            {isCircle(item) ? (
              <NumberRow
                label="半径 r"
                value={item.r ?? 20}
                onChange={(v) => onSetField('r', v)}
              />
            ) : (
              <>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <NumberRow
                    label="宽 w"
                    value={item.w ?? 0}
                    onChange={(v) => onSetField('w', v)}
                  />
                  <NumberRow
                    label="高 h"
                    value={item.h ?? 0}
                    onChange={(v) => onSetField('h', v)}
                  />
                </div>
                <Field label="朝向 orient(床头/沙发背所在侧)">
                  <SegmentedControl
                    variant="orient"
                    options={ORIENTS}
                    value={item.orient}
                    onChange={(o) => onSetField('orient', o)}
                  />
                </Field>
                <NumberRow
                  label="旋转 rot(度, 0=不旋转)"
                  value={typeof item.rot === 'number' ? item.rot : 0}
                  onChange={(v) => onSetField('rot', v)}
                />
              </>
            )}

            {/* z-order 叠放 (P2-13) */}
            <Field label={`叠放次序 zorder(当前 ${item.zorder ?? 0})`}>
              <div className="flex gap-2">
                <button
                  type="button"
                  data-testid="furn-bring-front"
                  onClick={onBringToFront}
                  className="flex-1 rounded-lg border border-gray-200 px-2 py-1 text-xs hover:bg-gray-50 dark:border-white/10 dark:hover:bg-white/5"
                >
                  ⬆ 置顶
                </button>
                <button
                  type="button"
                  data-testid="furn-send-back"
                  onClick={onSendToBack}
                  className="flex-1 rounded-lg border border-gray-200 px-2 py-1 text-xs hover:bg-gray-50 dark:border-white/10 dark:hover:bg-white/5"
                >
                  ⬇ 置底
                </button>
              </div>
            </Field>

            <TextRow
              label="标签 label(空=显示中文名)"
              value={item.label ? String(item.label) : ''}
              onChange={(v) => onSetField('label', v)}
            />

            <TextRow
              label="颜色 color(空=按类型默认)"
              value={item.color ? String(item.color) : ''}
              onChange={(v) => onSetField('color', v)}
              placeholder="#rrggbb"
            />

            <p className="mt-2 text-xs text-gray-400">
              尺寸单位 1=10mm(w=300 即 3m)。
            </p>

            <DangerButton onClick={onDelete}>🗑 删除家具</DangerButton>
          </div>
        ) : (
          <EmptyState
            className="!py-6"
            icon={<span>🛋️</span>}
            title="未选中家具"
            description="点击画布上的家具进行编辑,或用上方「＋添加」在当前房间放置新家具。"
          />
        )}
      </PanelSection>

      {/* 保存状态 */}
      <PanelSection>
        <StatusLines
          errors={saveState.error ? [saveState.error] : []}
          warns={saveState.warns}
          resolveLocate={canLocate}
          onLocate={onLocate}
          okText={saveState.savedOk ? '✓ 已保存' : undefined}
          hintText="编辑后点保存写盘。"
        />
      </PanelSection>

      <div className="flex items-center gap-2">
        <SaveButton onClick={onSave} disabled={saveState.saving}>
          {saveState.saving ? '保存中…' : '💾 保存家具'}
        </SaveButton>
        <span
          data-testid="furn-save-status"
          className={`text-xs font-medium ${
            dirty ? 'text-amber-500' : 'text-green-500'
          }`}
        >
          {dirty ? '● 未保存' : '✓ 已保存'}
        </span>
      </div>
    </SidePanel>
  );
}
