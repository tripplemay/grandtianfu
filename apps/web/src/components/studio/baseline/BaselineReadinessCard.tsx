'use client';

import React from 'react';
import { MdCheckCircle, MdErrorOutline } from 'react-icons/md';
import type { BaselinePhoto } from 'lib/studioApi';

// 工作流改造 (B5): 「实拍生成准备度」面板 —— 把「确认户型」与「准备实拍素材」拆成两个清晰
// 里程碑。派生自空房照的标注/视角/质量, 逐项 ✓/⚠, 非阻断, 只做引导。

const VIEWS = ['v0', 'v1', 'v2', 'v3'];

function isEmptyPhoto(p: BaselinePhoto): boolean {
  return p.purpose == null || p.purpose === 'empty';
}

function hasView(p: BaselinePhoto): boolean {
  return !!p.direction && VIEWS.includes(p.direction);
}

function isReady(p: BaselinePhoto): boolean {
  return isEmptyPhoto(p) && !!p.room_id && hasView(p);
}

export default function BaselineReadinessCard({
  photos,
}: {
  photos: BaselinePhoto[];
}) {
  const empty = photos.filter(isEmptyPhoto);
  const withRoom = empty.filter((p) => p.room_id).length;
  const withView = empty.filter(hasView).length;
  const readyCount = empty.filter(isReady).length;
  const wallRefs = photos.filter((p) => p.purpose === 'wall_material').length;
  const lowQuality = empty.filter(
    (p) => (p.quality?.warnings?.length ?? 0) > 0,
  ).length;

  const checks: { ok: boolean; label: string }[] = [
    { ok: empty.length > 0, label: `已上传空房照 ${empty.length} 张` },
    {
      ok: empty.length > 0 && withRoom === empty.length,
      label: `每张已标注房间 (${withRoom}/${empty.length})`,
    },
    {
      ok: empty.length > 0 && withView === empty.length,
      label: `每张已选拍摄视角 (${withView}/${empty.length})`,
    },
    {
      ok: empty.length === 0 || lowQuality === 0,
      label:
        lowQuality > 0
          ? `${lowQuality} 张照片质量偏低,建议更换`
          : '照片质量良好',
    },
    {
      ok: wallRefs > 0,
      label: `墙面材质参考 ${wallRefs} 张(可选,提升材质还原)`,
    },
  ];

  const readyForReal = readyCount > 0;

  return (
    <div className="mb-4 rounded-xl border border-gray-200 p-3 dark:border-white/10">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-sm font-bold text-navy-700 dark:text-white">
          实拍生成准备度
        </p>
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            readyForReal
              ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200'
              : 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-200'
          }`}
        >
          {readyForReal
            ? `${readyCount} 张可直接用于实拍`
            : '尚无可直接用于实拍的照片'}
        </span>
      </div>
      <ul className="space-y-1">
        {checks.map((c, i) => (
          <li
            key={i}
            className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300"
          >
            {c.ok ? (
              <MdCheckCircle className="h-4 w-4 shrink-0 text-green-500" />
            ) : (
              <MdErrorOutline className="h-4 w-4 shrink-0 text-amber-500" />
            )}
            <span>{c.label}</span>
          </li>
        ))}
      </ul>
      {!readyForReal && empty.length > 0 && (
        <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
          实拍生成默认要求照片标注了房间与视角(否则需切换低准确度模式)。
        </p>
      )}
    </div>
  );
}
