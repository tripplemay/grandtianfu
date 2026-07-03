'use client';

import React, { useEffect, useId, useState } from 'react';
import { labelCls, inputCls } from 'lib/floorplan/fieldStyles';

// 本地草稿输入 (升级计划 P0): 键入只改本地 state, blur/Enter 才提交 onChange ——
// 修 undo 逐字符落帧 (键入 350 = 3 帧历史) 并消灭键入中间值触发的 derive 请求。
// 外部 value 变化 (选中另一元素/撤销) 时同步回草稿。
function useDraftValue<T>(value: T): [T, (v: T) => void, () => void] {
  const [draft, setDraft] = useState<T>(value);
  useEffect(() => {
    setDraft(value);
  }, [value]);
  return [draft, setDraft, () => setDraft(value)];
}

function commitKeys(commit: () => void, revert: () => void) {
  return (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      commit();
      e.currentTarget.blur();
    } else if (e.key === 'Escape') {
      revert();
      e.currentTarget.blur();
    }
  };
}

// 紧凑属性面板字段组件族 (审查清单 Q2-#1 主体 / P2-B)。
// 刻意 *不* 使用 Horizon InputField: 其 h-12 尺寸不适合 340px 密集面板,
// 且 InputField 有 value=0 渲染丢值的 bug。这里数字字段 value={value} 直传,
// value=0 正确显示。补 htmlFor/id 关联 (a11y)。

// label + 任意控件 (供需要自定义控件的场景, 如 Switch 行)。
// 渲染为单个 <div> 包裹, 使每个字段行在 grid-cols-2 中占一个格子;
// 堆叠场景下表现与原裸 label+input 等价 (margin 折叠)。
export function Field({
  label,
  htmlFor,
  children,
}: {
  label: React.ReactNode;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className={labelCls}>
        {label}
      </label>
      {children}
    </div>
  );
}

// 文本输入行 (草稿式: blur/Enter 提交, Esc 还原)。
export function TextRow({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: React.ReactNode;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const id = useId();
  const [draft, setDraft, revert] = useDraftValue(value);
  const commit = () => {
    if (draft !== value) onChange(draft);
  };
  return (
    <Field label={label} htmlFor={id}>
      <input
        id={id}
        className={inputCls}
        value={draft}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={commitKeys(commit, revert)}
      />
    </Field>
  );
}

// 数字输入行 (草稿式)。value=0 正确显示 (不做 value && value);
// 键入中间态 (空串/负号) 停留在草稿, 提交时非法值还原。
export function NumberRow({
  label,
  value,
  onChange,
}: {
  label: React.ReactNode;
  value: number;
  onChange: (value: number) => void;
}) {
  const id = useId();
  const [draft, setDraft, revert] = useDraftValue<string>(String(value));
  const commit = () => {
    const n = Number(draft);
    if (draft.trim() === '' || Number.isNaN(n)) {
      revert();
      return;
    }
    if (n !== value) onChange(n);
  };
  return (
    <Field label={label} htmlFor={id}>
      <input
        id={id}
        type="number"
        className={inputCls}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={commitKeys(commit, revert)}
      />
    </Field>
  );
}

// 原生 <select> 取值行 (Horizon dropdown 是菜单弹层非受控 select, 清单明确勿换)。
export function SelectRow({
  label,
  value,
  options,
  onChange,
  renderLabel,
}: {
  label: React.ReactNode;
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
  renderLabel?: (value: string) => React.ReactNode;
}) {
  const id = useId();
  return (
    <Field label={label} htmlFor={id}>
      <select
        id={id}
        className={inputCls}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {renderLabel ? renderLabel(o) : o}
          </option>
        ))}
      </select>
    </Field>
  );
}
