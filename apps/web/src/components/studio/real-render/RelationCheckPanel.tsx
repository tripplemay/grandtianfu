import React from 'react';
import { Badge } from 'components/studio/ui/status';
import type { RelationCheckItem, RenderRecord } from 'lib/studioApi';

// 关系布置验收透出 (render-relation-b1 / render-mask-b1, 与 AutoCheckPanel 并列互不相干):
// relation_check 仅 relational 系 (relational / relational_mask) 记录有; 旧记录/softref/
// geometry_lock 缺省 (undefined) 不展示。软门语义: 不折叠不弱化大图, 只如实列出逐条核对
// 结果供用户判断 (uncertain 不算 fail, 背景保真只分级不做门)。
// render-mask-b1: relational_mask 记录另带 background_diff (mask 外像素级锁定校验);
// 区域估计失败的降级记录 (strategy=relational + mask_degraded) 灰字说明未启用背景锁定。

const CHECK_STATUS: Record<
  RelationCheckItem['status'],
  { mark: string; cls: string }
> = {
  pass: { mark: '✓', cls: 'text-green-600 dark:text-green-400' },
  fail: { mark: '✗', cls: 'text-red-600 dark:text-red-400' },
  uncertain: { mark: '?', cls: 'text-gray-400 dark:text-gray-500' },
};

// relational 系验收结果面板: relation_pass 徽章 + 逐条 checks + 背景保真/像素锁定 + 修正轮数。
export function RelationCheckPanel({ record }: { record: RenderRecord }) {
  const rc = record.relation_check;
  const bg = record.background_diff;
  // relational 系记录恒带 relation_check; 仅 mask 字段而无 rc 属理论兜底, 也渲染小区块。
  if (!rc && !bg && !record.mask_degraded) return null;
  const rounds = record.rounds ?? 1;
  return (
    <div className="mt-3 rounded-xl border border-gray-200 p-3 dark:border-white/10">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-bold text-navy-700 dark:text-white">
          {rc ? '关系布置验收' : '背景锁定校验'}
        </p>
        {rc &&
          (rc.degraded ? (
            <Badge tone="amber" size="xs" title={rc.error}>
              自动验收暂不可用(已交付)
            </Badge>
          ) : rc.relation_pass ? (
            <Badge
              tone="green"
              size="xs"
              title={`通过 ${rc.npass} · 不确定 ${rc.nuncertain}`}
            >
              验收通过 ✓
            </Badge>
          ) : (
            <Badge
              tone="red"
              size="xs"
              title={`通过 ${rc.npass} · 未过 ${rc.nfail} · 不确定 ${rc.nuncertain}`}
            >
              有未通过项
            </Badge>
          ))}
        {rc && rounds > 1 && (
          <Badge
            tone="gray"
            size="xs"
            title="首轮验收有未过项, 回写修正后重出并两轮取优"
          >
            经 {rounds} 轮修正
          </Badge>
        )}
        {rc && (
          <Badge
            tone={rc.background_preserved ? 'gray' : 'amber'}
            size="xs"
            title={
              rc.background_preserved
                ? '墙面/地面/门窗等背景未被改动'
                : '背景(墙面/地面/门窗等)疑似被改动, 见下方列表'
            }
          >
            {rc.background_preserved ? '背景保真 ✓' : '背景疑似被改动'}
          </Badge>
        )}
        {/* render-mask-b1: mask 外像素级锁定校验 (确定性 diff, 与 VLM 背景分级并列)。 */}
        {bg &&
          (bg.ok ? (
            <Badge
              tone="green"
              size="xs"
              title={
                bg.checked_px != null
                  ? `mask 外 ${bg.checked_px} 像素零改动`
                  : 'mask 外像素零改动'
              }
            >
              背景逐像素锁定 ✓
            </Badge>
          ) : (
            <Badge
              tone="amber"
              size="xs"
              title={bg.error ?? `max_diff ${bg.max_diff}`}
            >
              背景有像素改动
            </Badge>
          ))}
      </div>
      {record.mask_degraded && (
        <p
          className="mt-1.5 text-xs text-gray-400 dark:text-gray-500"
          title={record.mask_degraded}
        >
          区域估计失败,已按普通智能布置出图(未启用背景锁定)。
        </p>
      )}
      {rc?.summary && (
        <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
          {rc.summary}
        </p>
      )}
      {bg && !bg.ok && (
        <p className="mt-1.5 text-xs text-amber-700 dark:text-amber-300">
          mask 外 {(bg.changed_frac * 100).toFixed(2)}% 像素被改动 (max_diff{' '}
          {bg.max_diff}){bg.error ? ` —— ${bg.error}` : ''}
        </p>
      )}
      {rc &&
        (rc.degraded ? (
          <p className="mt-1.5 text-xs text-gray-400 dark:text-gray-500">
            验收模型暂不可用, 本次跳过逐条核对直接交付 ——
            请人工确认布置是否符合方案。
          </p>
        ) : (
          rc.checks.length > 0 && (
            <ul className="mt-2 space-y-1">
              {rc.checks.map((c) => {
                const st = CHECK_STATUS[c.status] ?? CHECK_STATUS.uncertain;
                return (
                  <li key={c.id} className="flex items-start gap-1.5 text-xs">
                    <span className={`shrink-0 font-bold ${st.cls}`}>
                      {st.mark}
                    </span>
                    <span className="text-gray-600 dark:text-gray-300">
                      {c.note || c.id}
                    </span>
                  </li>
                );
              })}
            </ul>
          )
        ))}
      {rc && !rc.background_preserved && rc.background_issues.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-amber-700 dark:text-amber-300">
          {rc.background_issues.map((issue) => (
            <li key={issue}>· {issue}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
