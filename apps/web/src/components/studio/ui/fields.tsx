'use client';

import React, { useId } from 'react';
import { labelCls, inputCls } from 'lib/floorplan/fieldStyles';

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

// 文本输入行。
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
  return (
    <Field label={label} htmlFor={id}>
      <input
        id={id}
        className={inputCls}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </Field>
  );
}

// 数字输入行。value=0 正确显示 (不做 value && value)。
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
  return (
    <Field label={label} htmlFor={id}>
      <input
        id={id}
        type="number"
        className={inputCls}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
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
