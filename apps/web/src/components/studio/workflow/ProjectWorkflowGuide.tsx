'use client';

import React from 'react';
import Link from 'next/link';
import { MdCheck } from 'react-icons/md';
import { useProjectWorkflow } from './ProjectWorkflowContext';

// 项目工作流引导:状态驱动的「下一步」主 CTA + 水平 stepper。
// 让用户随时知道「在 8 步线性流程的第几步、下一步做什么」,并一键前往。
// 放在项目概览顶部;完全由 ProjectWorkflowContext 派生,不引入新数据源。

interface Step {
  key: string;
  label: string;
  href: string;
  cta: string;
  done: boolean;
}

export default function ProjectWorkflowGuide({
  projectId,
}: {
  projectId: string;
}) {
  const { currentBaseline, availableSchemes, loading } = useProjectWorkflow();
  const base = `/studio/projects/${encodeURIComponent(projectId)}`;

  const hasBaseline = !!currentBaseline; // 存在已确认户型版本
  // 「有方案」需存在一个真正的方案:排除自动生成的空 default(初始方案)——否则确认户型后
  // default 恒在,会让「创建方案」步骤永远算已完成、跳过引导。default 一旦有家具则算数。
  const hasSchemes = availableSchemes.some(
    (s) => s.id !== 'default' || (s.items ?? 0) > 0,
  );
  const hasFurniture = availableSchemes.some((s) => (s.items ?? 0) > 0);
  const hasRenders = availableSchemes.some((s) => (s.renders ?? 0) > 0);
  const hasPreferred = availableSchemes.some((s) => s.preferred);

  // 编辑/出图目标:优先首选方案,否则最近更新的方案。
  const byRecent = [...availableSchemes].sort((a, b) =>
    String(b.updated_at ?? '').localeCompare(String(a.updated_at ?? '')),
  );
  const target =
    availableSchemes.find((s) => s.preferred)?.id ?? byRecent[0]?.id;
  const editorHref = target
    ? `${base}/editor?scheme=${encodeURIComponent(target)}&tab=furniture`
    : `${base}/scheme`;
  const renderHref = target
    ? `${base}/render?scheme=${encodeURIComponent(target)}`
    : `${base}/scheme`;

  const steps: Step[] = [
    {
      key: 'baseline',
      label: '确认户型',
      href: `${base}/baseline`,
      cta: '继续完善并确认户型',
      done: hasBaseline,
    },
    {
      key: 'scheme',
      label: '创建方案',
      href: `${base}/scheme`,
      cta: '创建首个软装方案',
      done: hasSchemes,
    },
    {
      key: 'furniture',
      label: '布置家具',
      href: editorHref,
      cta: '去布置家具',
      done: hasFurniture,
    },
    {
      key: 'render',
      label: '生成效果图',
      href: renderHref,
      cta: '生成 AI 效果图',
      done: hasRenders,
    },
    {
      key: 'preferred',
      label: '选定首选',
      href: `${base}/scheme`,
      cta: '选定首选方案',
      done: hasPreferred,
    },
  ];

  const currentIndex = steps.findIndex((s) => !s.done);
  const nextStep = currentIndex >= 0 ? steps[currentIndex] : null;

  if (loading) return null;

  return (
    <div className="mb-4 rounded-2xl border border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-navy-800">
      {/* 状态驱动的下一步主 CTA */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
            下一步
          </p>
          <p className="mt-0.5 text-lg font-bold text-navy-700 dark:text-white">
            {nextStep ? nextStep.cta : '方案已就绪,可查看首选或继续迭代'}
          </p>
        </div>
        <Link
          href={nextStep ? nextStep.href : `${base}/scheme`}
          className="inline-flex w-fit items-center rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600"
        >
          {nextStep ? `${nextStep.cta} →` : '进入方案中心 →'}
        </Link>
      </div>

      {/* 水平 stepper:已完成打勾、当前高亮、待办灰;节点可点跳转 */}
      <ol className="mt-4 flex flex-wrap items-center gap-y-2">
        {steps.map((step, i) => {
          const status = step.done
            ? 'done'
            : i === currentIndex
            ? 'current'
            : 'todo';
          const circle =
            status === 'done'
              ? 'bg-green-500 text-white'
              : status === 'current'
              ? 'bg-brand-500 text-white'
              : 'bg-gray-200 text-gray-500 dark:bg-navy-700 dark:text-gray-400';
          const text =
            status === 'todo'
              ? 'text-gray-400'
              : 'text-navy-700 dark:text-white';
          return (
            <li key={step.key} className="flex items-center">
              <Link
                href={step.href}
                className="group flex items-center gap-2"
                title={step.cta}
              >
                <span
                  className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${circle}`}
                >
                  {status === 'done' ? <MdCheck className="h-4 w-4" /> : i + 1}
                </span>
                <span
                  className={`text-sm font-medium group-hover:underline ${text}`}
                >
                  {step.label}
                </span>
              </Link>
              {i < steps.length - 1 && (
                <span className="mx-2 h-px w-6 bg-gray-200 dark:bg-white/10" />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
