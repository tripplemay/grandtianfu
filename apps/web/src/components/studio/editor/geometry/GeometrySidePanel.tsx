'use client';

import React from 'react';
import type { Geometry, DeriveResult } from 'lib/floorplan/types';
import { ROOM_TYPES, FREEWALL_ROLES, roomById } from 'lib/floorplan/geometry';
import type { EditorSelection } from '../EditorStage';

export interface SaveState {
  saving: boolean;
  errors: string[];
  warns: string[];
  savedOk: boolean;
}

interface Props {
  geometry: Geometry;
  derived: DeriveResult | null;
  selection: EditorSelection;
  insertMode: 'door' | 'freewall' | null;
  saveState: SaveState;
  overlapErrors: string[]; // 客户端实时算出的重叠未合并冲突文案 (§④)。
  onSetRoom: (field: 'type' | 'space', value: string) => void;
  onSetLabel: (value: string) => void;
  onSetRect: (i: number, value: number) => void;
  onSetOp: (field: string, value: string | boolean) => void;
  onSetOpWall: (field: 'axis' | 'at', value: string | number) => void;
  onSetSpan: (i: number, value: number) => void;
  onDelOp: () => void;
  onSetFw: (field: string, value: string | number) => void;
  onSetFwSpan: (i: number, value: number) => void;
  onDelFw: () => void;
  onMerge: () => void;
  onSplit: () => void;
  onToggleInsert: (mode: 'door' | 'freewall') => void;
  onSave: () => void;
}

const labelCls = 'mt-2 block text-xs text-gray-500 dark:text-gray-300';
const inputCls =
  'w-full rounded-md border border-gray-300 bg-white px-2 py-1 text-sm text-navy-700 dark:border-white/10 dark:bg-navy-900 dark:text-white';

export default function GeometrySidePanel(props: Props) {
  const { geometry, derived, selection, insertMode, saveState, overlapErrors } =
    props;
  const hasOverlap = overlapErrors.length > 0;
  const room = roomById(geometry, selection.room);
  const opening =
    geometry.openings?.find((o) => o.id === selection.opening) ?? null;
  const freeWall =
    (geometry.free_walls ?? []).find((f) => f.id === selection.freeWall) ??
    null;
  const spaceKeys = Object.keys(geometry.spaces ?? {});

  return (
    <div className="flex w-full max-w-[340px] flex-col gap-3 rounded-2xl border border-gray-200 bg-white p-4 text-sm dark:border-white/10 dark:bg-navy-800 dark:text-white">
      <h2 className="text-base font-bold text-navy-700 dark:text-white">
        几何编辑
      </h2>

      {/* 工具栏 */}
      <div className="flex flex-wrap gap-2">
        <ToolBtn
          active={insertMode === 'door'}
          onClick={() => props.onToggleInsert('door')}
        >
          ＋门(点墙)
        </ToolBtn>
        <ToolBtn
          active={insertMode === 'freewall'}
          onClick={() => props.onToggleInsert('freewall')}
        >
          ＋自由墙
        </ToolBtn>
        <ToolBtn onClick={props.onMerge}>打通</ToolBtn>
        <ToolBtn onClick={props.onSplit}>分隔</ToolBtn>
      </div>
      <p className="text-xs text-gray-400">
        拖房间=移动 · 8 把手=缩放 · Alt 关吸附
      </p>

      {/* 属性区 */}
      <div className="rounded-xl border border-gray-100 p-3 dark:border-white/5">
        {room && (
          <div>
            <p className="font-semibold">房间 {room.id}</p>
            <label className={labelCls}>类型 type</label>
            <select
              className={inputCls}
              value={room.type}
              onChange={(e) => props.onSetRoom('type', e.target.value)}
            >
              {ROOM_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <label className={labelCls}>空间 space(同 space=开放无墙)</label>
            <select
              className={inputCls}
              value={room.space}
              onChange={(e) => props.onSetRoom('space', e.target.value)}
            >
              {spaceKeys.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <label className={labelCls}>标签 label.zh</label>
            <input
              className={inputCls}
              value={room.label?.zh ?? ''}
              onChange={(e) => props.onSetLabel(e.target.value)}
            />
            <div className="mt-2 grid grid-cols-2 gap-2">
              {(['x', 'y', 'w', 'h'] as const).map((k, i) => (
                <div key={k}>
                  <label className={labelCls}>{k}</label>
                  <input
                    type="number"
                    className={inputCls}
                    value={room.rect[i]}
                    onChange={(e) => props.onSetRect(i, Number(e.target.value))}
                  />
                </div>
              ))}
            </div>
            <p className="mt-2 text-xs text-gray-400">
              录入=轴线尺寸(1=10mm)。Shift+点可选第二个房间用于打通。
            </p>
          </div>
        )}

        {!room && opening && (
          <div>
            <p className="font-semibold">开洞 {opening.id}</p>
            <label className={labelCls}>kind</label>
            <select
              className={inputCls}
              value={opening.kind}
              onChange={(e) => props.onSetOp('kind', e.target.value)}
            >
              {['door', 'window', 'passage'].map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
            {opening.kind === 'door' && (
              <>
                <label className={labelCls}>door_type</label>
                <select
                  className={inputCls}
                  value={opening.door_type ?? 'swing'}
                  onChange={(e) => props.onSetOp('door_type', e.target.value)}
                >
                  {['swing', 'sliding', 'double'].map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
                {(opening.door_type ?? 'swing') !== 'sliding' && (
                  <>
                    <label className={labelCls}>hinge</label>
                    <select
                      className={inputCls}
                      value={opening.hinge ?? 'lo'}
                      onChange={(e) => props.onSetOp('hinge', e.target.value)}
                    >
                      {['lo', 'hi'].map((k) => (
                        <option key={k} value={k}>
                          {k}
                        </option>
                      ))}
                    </select>
                    <label className={labelCls}>swing</label>
                    <select
                      className={inputCls}
                      value={opening.swing ?? '+'}
                      onChange={(e) => props.onSetOp('swing', e.target.value)}
                    >
                      {['+', '-'].map((k) => (
                        <option key={k} value={k}>
                          {k}
                        </option>
                      ))}
                    </select>
                  </>
                )}
              </>
            )}
            {opening.kind === 'window' && (
              <>
                <label className={labelCls}>wtype</label>
                <select
                  className={inputCls}
                  value={opening.wtype ?? 'normal'}
                  onChange={(e) => props.onSetOp('wtype', e.target.value)}
                >
                  {['normal', 'full', 'high'].map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </>
            )}
            <label className={labelCls}>cut(断墙)</label>
            <select
              className={inputCls}
              value={opening.cut ? 'true' : 'false'}
              onChange={(e) => props.onSetOp('cut', e.target.value === 'true')}
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <div>
                <label className={labelCls}>axis</label>
                <input
                  className={inputCls}
                  value={opening.wall.axis}
                  onChange={(e) => props.onSetOpWall('axis', e.target.value)}
                />
              </div>
              <div>
                <label className={labelCls}>at</label>
                <input
                  type="number"
                  className={inputCls}
                  value={opening.wall.at}
                  onChange={(e) =>
                    props.onSetOpWall('at', Number(e.target.value))
                  }
                />
              </div>
              <div>
                <label className={labelCls}>span lo</label>
                <input
                  type="number"
                  className={inputCls}
                  value={opening.wall.span[0]}
                  onChange={(e) => props.onSetSpan(0, Number(e.target.value))}
                />
              </div>
              <div>
                <label className={labelCls}>span hi</label>
                <input
                  type="number"
                  className={inputCls}
                  value={opening.wall.span[1]}
                  onChange={(e) => props.onSetSpan(1, Number(e.target.value))}
                />
              </div>
            </div>
            <DangerBtn onClick={props.onDelOp}>🗑 删除开洞</DangerBtn>
          </div>
        )}

        {!room && !opening && freeWall && (
          <div>
            <p className="font-semibold">自由墙 {freeWall.id}</p>
            <label className={labelCls}>role</label>
            <select
              className={inputCls}
              value={freeWall.role}
              onChange={(e) => props.onSetFw('role', e.target.value)}
            >
              {FREEWALL_ROLES.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <div>
                <label className={labelCls}>axis</label>
                <input
                  className={inputCls}
                  value={freeWall.axis}
                  onChange={(e) => props.onSetFw('axis', e.target.value)}
                />
              </div>
              <div>
                <label className={labelCls}>at</label>
                <input
                  type="number"
                  className={inputCls}
                  value={freeWall.at}
                  onChange={(e) => props.onSetFw('at', Number(e.target.value))}
                />
              </div>
              <div>
                <label className={labelCls}>span lo</label>
                <input
                  type="number"
                  className={inputCls}
                  value={freeWall.span[0]}
                  onChange={(e) => props.onSetFwSpan(0, Number(e.target.value))}
                />
              </div>
              <div>
                <label className={labelCls}>span hi</label>
                <input
                  type="number"
                  className={inputCls}
                  value={freeWall.span[1]}
                  onChange={(e) => props.onSetFwSpan(1, Number(e.target.value))}
                />
              </div>
            </div>
            <DangerBtn onClick={props.onDelFw}>🗑 删除自由墙</DangerBtn>
          </div>
        )}

        {!room && !opening && !freeWall && (
          <p className="text-xs text-gray-400">
            点房间选中(可改
            type/space/label);点门窗滑块拖动;点墙(开门模式)插门。
          </p>
        )}
      </div>

      {/* 校验 / 冲突 */}
      <div className="rounded-xl border border-gray-100 p-3 dark:border-white/5">
        <h3 className="mb-1 text-xs font-semibold text-gray-500 dark:text-gray-300">
          校验 / 冲突
        </h3>
        <StatusBlock
          derived={derived}
          saveState={saveState}
          overlapErrors={overlapErrors}
        />
      </div>

      <button
        type="button"
        onClick={props.onSave}
        disabled={saveState.saving || hasOverlap}
        title={
          hasOverlap ? '存在重叠冲突,先用「打通」标记合并或拖开' : undefined
        }
        className="rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
      >
        {saveState.saving
          ? '保存中…'
          : hasOverlap
          ? '⛔ 重叠冲突,无法保存'
          : '💾 校验并保存'}
      </button>
    </div>
  );
}

function ToolBtn({
  active,
  onClick,
  children,
}: {
  active?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg px-3 py-1 text-xs font-medium ${
        active
          ? 'bg-brand-500 text-white'
          : 'bg-gray-100 text-navy-700 hover:bg-gray-200 dark:bg-navy-900 dark:text-white dark:hover:bg-navy-700'
      }`}
    >
      {children}
    </button>
  );
}

function DangerBtn({
  onClick,
  children,
}: {
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mt-3 rounded-lg bg-red-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600"
    >
      {children}
    </button>
  );
}

function StatusBlock({
  derived,
  saveState,
  overlapErrors,
}: {
  derived: DeriveResult | null;
  saveState: SaveState;
  overlapErrors: string[];
}) {
  // 保存后优先展示校验结果 (§⑨); 否则展示实时派生冲突/警告 (§⑧)。
  const errors = saveState.errors;
  const warns =
    saveState.errors.length || saveState.savedOk
      ? saveState.warns
      : derived?.warns ?? [];
  const conflicts =
    saveState.errors.length || saveState.savedOk
      ? []
      : derived?.conflicts ?? [];

  // 重叠未合并冲突 = 客户端实时算 (始终展示, 优先于派生冲突); 与后端 validate 一致。
  const allErrors = [...overlapErrors, ...conflicts, ...errors];
  return (
    <div className="space-y-1">
      {allErrors.map((c, i) => (
        <p key={`e${i}`} className="text-xs text-red-500">
          ⛔ {c}
        </p>
      ))}
      {warns.map((w, i) => (
        <p key={`w${i}`} className="text-xs text-amber-500">
          ⚠ {w}
        </p>
      ))}
      {allErrors.length === 0 && warns.length === 0 && (
        <p className="text-xs text-green-500">
          {saveState.savedOk ? '✓ 已保存 / 校验通过' : '✓ 无冲突'}
        </p>
      )}
      {derived && (
        <p className="mt-1 text-xs text-gray-400">
          墙 {derived.walls.length} · 门 {derived.doors.length} · 窗{' '}
          {derived.windows.length}
        </p>
      )}
    </div>
  );
}
