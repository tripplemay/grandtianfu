'use client';

import React, { useEffect, useState } from 'react';
import { StudioCard } from 'components/studio/ui/primitives';
import { Badge, StatusLines } from 'components/studio/ui/status';
import { LinkButton } from 'components/studio/ui/buttons';
import { getBaselineReadiness, type BaselineReadiness } from 'lib/studioApi';

// P0-1: 后端权威的"户型可生成质量"面板 —— blocking (会阻断出图) / warning (可降级建议) /
// summary。取代前端各处自行派生 readiness, 单一真源。reloadKey 变化时重取 (家具/照片编辑后)。
export default function BaselineReadinessPanel({
  projectId,
  versionId,
  reloadKey,
  canEdit = true,
}: {
  projectId: string;
  versionId: string;
  reloadKey?: unknown;
  // 历史/只读版本无法编辑, 不显示"去编辑器修复" CTA (会误导)。
  canEdit?: boolean;
}) {
  const [data, setData] = useState<BaselineReadiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    void getBaselineReadiness(projectId, versionId)
      .then((r) => {
        if (alive) {
          setData(r);
          setError(null);
        }
      })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [projectId, versionId, reloadKey]);

  if (loading) return null;
  if (error || !data) {
    // 拉取失败: 显式提示 (区别于"未渲染"), 不静默消失。
    return (
      <StudioCard extra="flex items-center gap-2">
        <Badge tone="gray" size="xs">
          就绪度
        </Badge>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          就绪度暂不可用{error ? `:${error}` : ''}
        </span>
      </StudioCard>
    );
  }

  const editorHref = `/studio/projects/${encodeURIComponent(
    projectId,
  )}/editor?baseline=${encodeURIComponent(versionId)}`;
  const s = data.summary;

  return (
    <StudioCard extra="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-bold text-navy-700 dark:text-white">
          生成就绪度
        </p>
        {data.ok ? (
          <Badge tone="green" size="xs">
            可生成 ✓
          </Badge>
        ) : (
          <Badge tone="red" size="xs">
            {data.blocking.length} 项待修复
          </Badge>
        )}
        {data.warning.length > 0 && (
          <Badge tone="amber" size="xs">
            {data.warning.length} 项建议
          </Badge>
        )}
      </div>

      <StatusLines
        errors={data.blocking.map((b) => b.message)}
        warns={data.warning.map((w) => w.message)}
        okText="户型几何、家具布局均已就绪,可生成效果图"
      />

      <p className="text-xs text-gray-500 dark:text-gray-400">
        家具 {s.furniture_count ?? 0} 件 · 空房照 {s.photos_total ?? 0} 张
        (已标注 {s.photos_ready ?? 0} · 已标定 {s.photos_calibrated ?? 0})
      </p>

      {canEdit && data.blocking.some((b) => b.fix === 'editor') && (
        <div>
          <LinkButton href={editorHref} variant="primary">
            去编辑器修复
          </LinkButton>
        </div>
      )}
    </StudioCard>
  );
}
