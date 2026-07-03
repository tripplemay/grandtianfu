'use client';

import React, { useId } from 'react';
import type { Geometry, DeriveResult } from 'lib/floorplan/types';
import {
  ROOM_TYPES,
  FREEWALL_ROLES,
  roomById,
  type AlignMode,
  type DistributeMode,
} from 'lib/floorplan/geometry';
import type { EditorSelection } from '../EditorStage';
import { SidePanel, PanelSection } from '../../ui/SidePanel';
import { TextRow, NumberRow, SelectRow, Field } from '../../ui/fields';
import { fmtMm, WALL_MATERIALS, WALL_SIDES } from 'lib/floorplan/units';
import { ToggleButton, SaveButton, DangerButton } from '../../ui/buttons';
import { StatusLines } from '../../ui/status';
import AlignBar from '../AlignBar';
import Switch from 'components/switch';
import WallPhotoControls from './WallPhotoControls';

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
  insertMode: 'door' | 'freewall' | 'room' | null;
  saveState: SaveState;
  dirty: boolean; // 防丢失 (P1-6): 有未保存改动。
  overlapErrors: string[]; // 客户端实时算出的重叠未合并冲突文案 (§④)。
  onSetRoom: (field: 'type' | 'space', value: string) => void;
  onSetLabel: (value: string) => void;
  onSetRect: (i: number, value: number) => void;
  onSetWallFinish: (side: 'N' | 'S' | 'E' | 'W', material: string) => void;
  onSetWallPhoto: (side: 'N' | 'S' | 'E' | 'W', photoId: string) => void; // 材质C
  // 材质C 上传/挂载所需上下文 (户型编辑时才有 baselineVersionId)。
  projectId?: string;
  baselineVersionId?: string;
  onDelRoom: () => void; // 删选中房 (P1-7): 与 Delete 键复用同一 onDelRoom。
  onSetOp: (field: string, value: string | boolean) => void;
  onSetOpWall: (field: 'axis' | 'at', value: string | number) => void;
  onSetSpan: (i: number, value: number) => void;
  onDelOp: () => void;
  onSetFw: (field: string, value: string | number) => void;
  onSetFwSpan: (i: number, value: number) => void;
  onDelFw: () => void;
  onMerge: () => void;
  onSplit: () => void;
  onAlign: (mode: AlignMode) => void;
  onDistribute: (mode: DistributeMode) => void;
  onToggleInsert: (mode: 'door' | 'freewall' | 'room') => void;
  onSave: () => void;
  // 定位校验反馈 (阶段 5b / P2-12): 校验条可点 -> 选中并高亮对应元素。
  canLocate: (msg: string) => boolean;
  onLocate: (msg: string) => void;
}

export default function GeometrySidePanel(props: Props) {
  const {
    geometry,
    derived,
    selection,
    insertMode,
    saveState,
    dirty,
    overlapErrors,
  } = props;
  const hasOverlap = overlapErrors.length > 0;
  const room = roomById(geometry, selection.room);
  const opening =
    geometry.openings?.find((o) => o.id === selection.opening) ?? null;
  const freeWall =
    (geometry.free_walls ?? []).find((f) => f.id === selection.freeWall) ??
    null;
  const spaceKeys = Object.keys(geometry.spaces ?? {});
  const cutId = useId();

  // 保存后优先展示校验结果 (§⑨); 否则展示实时派生冲突/警告 (§⑧)。
  const stErrors = saveState.errors;
  const stWarns =
    saveState.errors.length || saveState.savedOk
      ? saveState.warns
      : derived?.warns ?? [];
  const stConflicts =
    saveState.errors.length || saveState.savedOk
      ? []
      : derived?.conflicts ?? [];
  // 重叠未合并冲突 = 客户端实时算 (始终展示, 优先于派生冲突); 与后端 validate 一致。
  const allErrors = [...overlapErrors, ...stConflicts, ...stErrors];

  return (
    <SidePanel title="几何编辑">
      {/* 工具栏 */}
      <div className="flex flex-wrap gap-2">
        <ToggleButton
          active={insertMode === 'room'}
          onClick={() => props.onToggleInsert('room')}
        >
          ＋房间
        </ToggleButton>
        <ToggleButton
          active={insertMode === 'door'}
          onClick={() => props.onToggleInsert('door')}
        >
          ＋门(点墙)
        </ToggleButton>
        <ToggleButton
          active={insertMode === 'freewall'}
          onClick={() => props.onToggleInsert('freewall')}
        >
          ＋自由墙
        </ToggleButton>
        <ToggleButton onClick={props.onMerge}>打通</ToggleButton>
        <ToggleButton onClick={props.onSplit}>分隔</ToggleButton>
      </div>
      <p className="text-xs text-gray-400">
        拖房间=移动 · 8 把手=缩放 · Alt 关吸附 · ＋房间/自由墙=点两点 · Shift+点
        多选 · 空白拖框选 · Ctrl+A 全选
      </p>

      {/* 多选房间对齐 / 分布 (阶段 5a / P2-7) */}
      <AlignBar
        count={selection.rooms.length}
        onAlign={props.onAlign}
        onDistribute={props.onDistribute}
      />

      {/* 属性区 */}
      <PanelSection>
        {room && (
          <div>
            <p className="font-semibold">房间 {room.id}</p>
            <SelectRow
              label="类型 type"
              value={room.type}
              options={ROOM_TYPES}
              onChange={(v) => props.onSetRoom('type', v)}
            />
            <SelectRow
              label="空间 space(同 space=开放无墙)"
              value={room.space}
              options={spaceKeys}
              onChange={(v) => props.onSetRoom('space', v)}
            />
            <TextRow
              label="标签 label.zh"
              value={room.label?.zh ?? ''}
              onChange={props.onSetLabel}
            />
            <div className="mt-2 grid grid-cols-2 gap-2">
              {(['x', 'y', 'w', 'h'] as const).map((k, i) => (
                <NumberRow
                  key={k}
                  label={k}
                  value={room.rect[i]}
                  onChange={(v) => props.onSetRect(i, v)}
                  suffix={fmtMm(room.rect[i], props.geometry)}
                />
              ))}
            </div>
            {/* 墙面材质 (P1 材质A): 逐面标注, 进效果图提示词 + 轴测色块暗示。 */}
            <div className="mt-2">
              <p className="text-xs font-semibold text-gray-500">
                墙面材质(进效果图)
              </p>
              <div className="grid grid-cols-2 gap-2">
                {WALL_SIDES.map(({ side, zh }) => (
                  <SelectRow
                    key={side}
                    label={zh}
                    value={
                      ((
                        room.walls as
                          | Record<string, { material?: string }>
                          | undefined
                      )?.[side]?.material ?? '') as string
                    }
                    options={WALL_MATERIALS.map((m) => m.value)}
                    renderLabel={(v) =>
                      WALL_MATERIALS.find((m) => m.value === v)?.zh ?? v
                    }
                    onChange={(v) => props.onSetWallFinish(side, v)}
                  />
                ))}
              </div>
              {props.projectId && props.baselineVersionId && (
                <WallPhotoControls
                  projectId={props.projectId}
                  baselineVersionId={props.baselineVersionId}
                  walls={
                    room.walls as
                      | Record<string, { material?: string; photo_id?: string }>
                      | undefined
                  }
                  onSetWallPhoto={props.onSetWallPhoto}
                />
              )}
            </div>
            <p className="mt-2 text-xs text-gray-400">
              录入=轴线尺寸(1=10mm)。Shift+点可选第二个房间用于打通。
            </p>
            <DangerButton onClick={props.onDelRoom}>🗑 删除房间</DangerButton>
          </div>
        )}

        {!room && opening && (
          <div>
            <p className="font-semibold">开洞 {opening.id}</p>
            <SelectRow
              label="kind"
              value={opening.kind}
              options={['door', 'window', 'passage']}
              onChange={(v) => props.onSetOp('kind', v)}
            />
            {opening.kind === 'door' && (
              <>
                <SelectRow
                  label="door_type"
                  value={opening.door_type ?? 'swing'}
                  options={['swing', 'sliding', 'double']}
                  onChange={(v) => props.onSetOp('door_type', v)}
                />
                {(opening.door_type ?? 'swing') !== 'sliding' && (
                  <>
                    <SelectRow
                      label="hinge"
                      value={opening.hinge ?? 'lo'}
                      options={['lo', 'hi']}
                      onChange={(v) => props.onSetOp('hinge', v)}
                    />
                    <SelectRow
                      label="swing"
                      value={opening.swing ?? '+'}
                      options={['+', '-']}
                      onChange={(v) => props.onSetOp('swing', v)}
                    />
                  </>
                )}
              </>
            )}
            {opening.kind === 'window' && (
              <SelectRow
                label="wtype"
                value={opening.wtype ?? 'normal'}
                options={['normal', 'full', 'high']}
                onChange={(v) => props.onSetOp('wtype', v)}
              />
            )}
            <Field label="cut(断墙)" htmlFor={cutId}>
              <div className="mt-1">
                <Switch
                  id={cutId}
                  checked={!!opening.cut}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    props.onSetOp('cut', e.target.checked)
                  }
                />
              </div>
            </Field>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <SelectRow
                label="axis"
                value={opening.wall.axis}
                options={['h', 'v']}
                onChange={(v) => props.onSetOpWall('axis', v)}
              />
              <NumberRow
                label="at"
                value={opening.wall.at}
                onChange={(v) => props.onSetOpWall('at', v)}
              />
              <NumberRow
                label="span lo"
                value={opening.wall.span[0]}
                onChange={(v) => props.onSetSpan(0, v)}
              />
              <NumberRow
                label="span hi"
                value={opening.wall.span[1]}
                onChange={(v) => props.onSetSpan(1, v)}
              />
            </div>
            <DangerButton onClick={props.onDelOp}>🗑 删除开洞</DangerButton>
          </div>
        )}

        {!room && !opening && freeWall && (
          <div>
            <p className="font-semibold">自由墙 {freeWall.id}</p>
            <SelectRow
              label="role"
              value={freeWall.role}
              options={FREEWALL_ROLES}
              onChange={(v) => props.onSetFw('role', v)}
            />
            <div className="mt-2 grid grid-cols-2 gap-2">
              <SelectRow
                label="axis"
                value={freeWall.axis}
                options={['h', 'v']}
                onChange={(v) => props.onSetFw('axis', v)}
              />
              <NumberRow
                label="at"
                value={freeWall.at}
                onChange={(v) => props.onSetFw('at', v)}
              />
              <NumberRow
                label="span lo"
                value={freeWall.span[0]}
                onChange={(v) => props.onSetFwSpan(0, v)}
              />
              <NumberRow
                label="span hi"
                value={freeWall.span[1]}
                onChange={(v) => props.onSetFwSpan(1, v)}
              />
            </div>
            <DangerButton onClick={props.onDelFw}>🗑 删除自由墙</DangerButton>
          </div>
        )}

        {!room && !opening && !freeWall && (
          <p className="text-xs text-gray-400">
            点房间选中(可改
            type/space/label);点门窗滑块拖动;点墙(开门模式)插门。
          </p>
        )}
      </PanelSection>

      {/* 校验 / 冲突 */}
      <PanelSection>
        <h3 className="mb-1 text-xs font-semibold text-gray-500 dark:text-gray-300">
          校验 / 冲突
        </h3>
        <StatusLines
          errors={allErrors}
          warns={stWarns}
          resolveLocate={props.canLocate}
          onLocate={props.onLocate}
          okText={saveState.savedOk ? '✓ 已保存 / 校验通过' : '✓ 无冲突'}
          footer={
            derived ? (
              <p className="mt-1 text-xs text-gray-400">
                墙 {derived.walls.length} · 门 {derived.doors.length} · 窗{' '}
                {derived.windows.length}
              </p>
            ) : null
          }
        />
      </PanelSection>

      <div className="flex items-center gap-2">
        <SaveButton
          onClick={props.onSave}
          disabled={saveState.saving || hasOverlap}
          title={
            hasOverlap ? '存在重叠冲突,先用「打通」标记合并或拖开' : undefined
          }
        >
          {saveState.saving
            ? '保存中…'
            : hasOverlap
            ? '⛔ 重叠冲突,无法保存'
            : '💾 校验并保存'}
        </SaveButton>
        <span
          data-testid="geo-save-status"
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
