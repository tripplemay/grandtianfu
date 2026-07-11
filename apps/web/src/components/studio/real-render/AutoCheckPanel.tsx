import React from 'react';
import { Badge } from 'components/studio/ui/status';
import { Button } from 'components/studio/ui/buttons';
import type { GeometryEditBackend, RenderRecord } from 'lib/studioApi';

// P4 自动验收透出 (与人工验收 status 互不相干): auto_check 仅 method=geometry-lock 记录
// 才有; 旧记录/轴测软参考路径缺省 (undefined) 视为"无验收信息", 不折叠不弱化 —— 一律折叠
// 会把全部历史图折没。

export function autoCheckFailed(r: RenderRecord): boolean {
  return r.auto_check?.ok === false;
}

// 折叠/弱化门: 人工验收 (status=accepted) 覆盖机器判定 —— 自动验收是软门, 用户看图后
// 显式通过的交付图不得再被机器判定折叠/置灰 (徽章仍保留双状态并示)。
export function shouldCollapseFailed(r: RenderRecord): boolean {
  return autoCheckFailed(r) && r.status !== 'accepted';
}

// 记录生效的编辑后端: edit_backend 是新增溯源字段, 更早的 geometry-lock 记录按 model 推断。
export function recordBackend(r: RenderRecord): GeometryEditBackend {
  if (r.edit_backend) return r.edit_backend;
  return r.model?.startsWith('fal-ai/') ? 'fal' : 'relay';
}

// 展示标签 = 两后端的默认模型名 (relay=IMAGE_MODEL 默认 gpt-image-2 / fal=FAL_EDIT_MODEL
// 默认 nano-banana); env 改配非默认模型时仅标签失准, 实际调用不受影响。
export const BACKEND_LABEL: Record<GeometryEditBackend, string> = {
  relay: 'gpt-image-2',
  fal: 'nano-banana',
};

export function retryBackendOf(r: RenderRecord): GeometryEditBackend {
  return recordBackend(r) === 'fal' ? 'relay' : 'fal';
}

// "验收未过"红徽章 (最新结果卡/历史网格/对比页共用, 保持单一实现)。
export function AutoCheckFailedBadge({ record }: { record: RenderRecord }) {
  if (!autoCheckFailed(record)) return null;
  return (
    <Badge
      tone="red"
      size="xs"
      title={(record.auto_check?.fail_reasons ?? []).join('; ') || undefined}
    >
      验收未过
    </Badge>
  );
}

// 质量徽章行: 几何锁定标识 + 自动验收结果 (通过/未过/异常)。
export function RenderQualityBadges({ record }: { record: RenderRecord }) {
  const check = record.auto_check;
  return (
    <>
      {record.method === 'geometry-lock' && (
        <Badge
          tone="brand"
          size="xs"
          title={`编辑后端: ${BACKEND_LABEL[recordBackend(record)]}`}
        >
          几何锁定
        </Badge>
      )}
      <AutoCheckFailedBadge record={record} />
      {check?.ok === true && !check.skipped && !check.error && (
        <Badge
          tone="green"
          size="xs"
          title={check.score != null ? `验收得分 ${check.score}` : undefined}
        >
          自动验收 ✓
        </Badge>
      )}
      {check?.error && (
        <Badge tone="amber" size="xs" title={check.error}>
          验收异常
        </Badge>
      )}
    </>
  );
}

// 验收未过的默认折叠面板 (代替大图): 失败原因 + 仍要查看 + 一键换后端重试。
// 软门语义: 图已交付 (得分最高的一张), 但默认不当普通成功展示, 防止误用为交付图。
export function AutoCheckFailedPanel({
  record,
  onExpand,
  onRetry,
  retryDisabledReason,
  retrying,
}: {
  record: RenderRecord;
  onExpand: () => void;
  onRetry: () => void;
  retryDisabledReason?: string | null;
  retrying: boolean;
}) {
  const check = record.auto_check;
  const target = retryBackendOf(record);
  return (
    <div className="mb-3 flex min-h-[420px] w-full flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-red-300 bg-red-50 p-6 text-center dark:border-red-500/40 dark:bg-red-500/10">
      <Badge tone="red">自动验收未通过</Badge>
      <p className="max-w-xl text-sm text-gray-600 dark:text-gray-300">
        {check?.score != null && <>得分 {check.score.toFixed(2)} · </>}已尝试{' '}
        {check?.attempts ?? 1} 次,保留的是其中得分最高的一张。图片默认折叠,
        以免与正常结果混淆。
      </p>
      {(check?.fail_reasons?.length ?? 0) > 0 && (
        <ul className="space-y-0.5 text-xs text-red-700 dark:text-red-300">
          {(check?.fail_reasons ?? []).map((reason) => (
            <li key={reason}>· {reason}</li>
          ))}
        </ul>
      )}
      <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
        <Button variant="neutral-outline" size="sm" onClick={onExpand}>
          仍要查看这张图
        </Button>
        <Button
          variant="soft-brand"
          size="sm"
          onClick={onRetry}
          disabled={retrying || !!retryDisabledReason}
          title={
            retryDisabledReason ?? `改用 ${BACKEND_LABEL[target]} 重新生成一张`
          }
        >
          {retrying ? '重试中…' : `换后端重试 (${BACKEND_LABEL[target]})`}
        </Button>
      </div>
    </div>
  );
}
