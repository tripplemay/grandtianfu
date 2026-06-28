'use client';

import React, { useState } from 'react';
import type { Furniture, Orient } from 'lib/floorplan/furniture';
import { FURN_TYPES, furnZh, isCircle } from 'lib/floorplan/furniture';
import { SidePanel, PanelSection } from '../../ui/SidePanel';
import { TextRow, NumberRow, SelectRow, Field } from '../../ui/fields';
import {
  SegmentedControl,
  SaveButton,
  DangerButton,
} from '../../ui/buttons';
import { StatusLines } from '../../ui/status';

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

const ORIENTS: Orient[] = ['N', 'S', 'W', 'E'];

const furnLabel = (t: string) => `${furnZh(t)} · ${t}`;

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
    <SidePanel title="家具编辑">
      {/* 添加 */}
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <SelectRow
            label="添加家具(落当前房)"
            value={addType}
            options={FURN_TYPES}
            onChange={setAddType}
            renderLabel={furnLabel}
          />
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
      <PanelSection>
        {item ? (
          <div>
            <p className="font-semibold">
              选中 #{selectedIndex} · {furnZh(item.t)}
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
              </>
            )}

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
          <p className="text-xs text-gray-400">点画布上的家具选中以编辑。</p>
        )}
      </PanelSection>

      {/* 保存状态 */}
      <PanelSection>
        <StatusLines
          errors={saveState.error ? [saveState.error] : []}
          okText={saveState.savedOk ? '✓ 已保存' : undefined}
          hintText="编辑后点保存写盘。"
        />
      </PanelSection>

      <SaveButton onClick={onSave} disabled={saveState.saving}>
        {saveState.saving ? '保存中…' : '💾 保存家具'}
      </SaveButton>
    </SidePanel>
  );
}
