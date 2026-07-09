'use client';

import React, { useState } from 'react';
import { Button } from '../ui/buttons';
import { patchScheme, type SchemeBrief } from 'lib/studioApi';

// 工作流改造 (B3): 方案级结构化设计 Brief 编辑器。把自由文本需求结构化 (风格方向/预算/主材/
// 主色/禁忌/重点房间等), 后端编译进轴测与实拍 prompt。自由文本 style_prompt 仍保留作补充。

const TEXT_FIELDS: {
  key: 'style_direction' | 'budget_tier' | 'occupants';
  label: string;
  placeholder: string;
}[] = [
  { key: 'style_direction', label: '风格方向', placeholder: '如 现代轻奢 / 日式原木' },
  { key: 'budget_tier', label: '预算档位', placeholder: '如 中高 / 高端' },
  { key: 'occupants', label: '居住人群', placeholder: '如 三口之家' },
];

const LIST_FIELDS: {
  key:
    | 'primary_materials'
    | 'banned_materials'
    | 'primary_colors'
    | 'banned_colors'
    | 'focus_rooms'
    | 'avoid_elements';
  label: string;
  placeholder: string;
}[] = [
  { key: 'primary_materials', label: '主材', placeholder: '逗号分隔, 如 胡桃木, 暖白石材' },
  { key: 'banned_materials', label: '禁用材质', placeholder: '如 亮面不锈钢' },
  { key: 'primary_colors', label: '主色', placeholder: '如 米色, 暖白' },
  { key: 'banned_colors', label: '禁用颜色', placeholder: '如 荧光色' },
  { key: 'focus_rooms', label: '重点房间', placeholder: '如 客厅, 主卧' },
  { key: 'avoid_elements', label: '不希望出现', placeholder: '如 杂乱堆物' },
];

function toList(s: string): string[] {
  return s
    .split(/[,，]/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function fromList(v?: string[]): string {
  return (v ?? []).join(', ');
}

export function briefFilledCount(b?: SchemeBrief | null): number {
  if (!b) return 0;
  let n = 0;
  for (const f of TEXT_FIELDS) if ((b[f.key] ?? '').trim()) n += 1;
  if (b.keep_hardscape) n += 1;
  for (const f of LIST_FIELDS) if ((b[f.key] ?? []).length) n += 1;
  return n;
}

export default function SchemeBriefEditor({
  projectId,
  schemeId,
  brief,
  editable,
  onSaved,
}: {
  projectId: string;
  schemeId: string;
  brief?: SchemeBrief | null;
  editable: boolean;
  onSaved: () => Promise<void> | void;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [textDraft, setTextDraft] = useState<Record<string, string>>({});
  const [keepHardscape, setKeepHardscape] = useState(false);

  const filled = briefFilledCount(brief);

  const openEditor = () => {
    const d: Record<string, string> = {};
    for (const f of TEXT_FIELDS) d[f.key] = brief?.[f.key] ?? '';
    for (const f of LIST_FIELDS) d[f.key] = fromList(brief?.[f.key]);
    setTextDraft(d);
    setKeepHardscape(!!brief?.keep_hardscape);
    setError(null);
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const next: SchemeBrief = {};
      for (const f of TEXT_FIELDS) {
        const v = (textDraft[f.key] ?? '').trim();
        if (v) next[f.key] = v;
      }
      if (keepHardscape) next.keep_hardscape = true;
      for (const f of LIST_FIELDS) {
        const list = toList(textDraft[f.key] ?? '');
        if (list.length) next[f.key] = list;
      }
      // 空对象由后端 _normalize_brief 归一化为 null (清空)。
      await patchScheme(projectId, schemeId, { brief: next });
      setEditing(false);
      await onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  if (!editing) {
    return (
      <div className="mt-2 flex items-start justify-between gap-2">
        <p className="min-w-0 text-xs text-gray-500 dark:text-gray-400">
          {filled > 0
            ? `设计 Brief:已填 ${filled} 项`
            : '设计 Brief:未填(可选,填了会编译进出图 prompt)'}
        </p>
        {editable && (
          <button
            type="button"
            onClick={openEditor}
            className="shrink-0 text-xs font-medium text-brand-600 hover:underline dark:text-brand-400"
          >
            {filled > 0 ? '编辑 Brief' : '填写 Brief'}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="mt-2 flex flex-col gap-2 rounded-lg border border-gray-200 p-3 dark:border-white/10">
      <p className="text-xs font-bold text-navy-700 dark:text-white">设计 Brief</p>
      {TEXT_FIELDS.map((f) => (
        <label key={f.key} className="flex flex-col gap-1">
          <span className="text-[11px] text-gray-500 dark:text-gray-400">
            {f.label}
          </span>
          <input
            type="text"
            value={textDraft[f.key] ?? ''}
            placeholder={f.placeholder}
            onChange={(e) =>
              setTextDraft((p) => ({ ...p, [f.key]: e.target.value }))
            }
            className="w-full rounded-lg border border-gray-200 px-2 py-1 text-xs text-navy-700 outline-none focus:border-brand-500 dark:border-white/10 dark:bg-navy-900 dark:text-white"
          />
        </label>
      ))}
      {LIST_FIELDS.map((f) => (
        <label key={f.key} className="flex flex-col gap-1">
          <span className="text-[11px] text-gray-500 dark:text-gray-400">
            {f.label}
          </span>
          <input
            type="text"
            value={textDraft[f.key] ?? ''}
            placeholder={f.placeholder}
            onChange={(e) =>
              setTextDraft((p) => ({ ...p, [f.key]: e.target.value }))
            }
            className="w-full rounded-lg border border-gray-200 px-2 py-1 text-xs text-navy-700 outline-none focus:border-brand-500 dark:border-white/10 dark:bg-navy-900 dark:text-white"
          />
        </label>
      ))}
      <label className="flex items-center gap-2 text-xs text-navy-700 dark:text-gray-200">
        <input
          type="checkbox"
          checked={keepHardscape}
          onChange={(e) => setKeepHardscape(e.target.checked)}
        />
        保留现有硬装/建筑不变
      </label>
      {error && (
        <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
      )}
      <div className="flex items-center gap-2">
        <Button variant="primary" size="sm" onClick={save} disabled={saving}>
          {saving ? '保存中…' : '保存 Brief'}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setEditing(false)}
          disabled={saving}
        >
          取消
        </Button>
      </div>
    </div>
  );
}
