// calib-cure-b3 F002 修复（verifying-1 判 PARTIAL）：拍摄构图「简示意」。
//
// 验收实证的缺口：acceptance 原文是「拍摄指南(**文字 + 简示意**)」且要求覆盖上传入口
// **与标定入口**两处；原实装只有文字、且「角落机位 / 避免正对单面墙」这两条 b3 立项赖以
// 成立的核心认知在标定入口完全缺席（全前端 grep 仅命中 BaselinePhotosCard 一处）。
//
// 本组件是纯 SVG 俯视示意（无外部依赖、无位图），两处复用。示意的是**几何事实**：
// 角落机位 → 视锥同时罩住两面相邻墙 → 特征点非共面 → 可解；
// 正对单面墙 → 可见特征全落在同一平面 → PnP 退化 → 数学上无解（b2 L2 实证）。

type Variant = 'good' | 'bad';

const WALL = 'stroke-gray-400 dark:stroke-gray-500';

function Panel({ variant }: { variant: Variant }) {
  const good = variant === 'good';
  const accent = good
    ? 'fill-green-500/20 dark:fill-green-400/25 stroke-green-600 dark:stroke-green-400'
    : 'fill-red-500/15 dark:fill-red-400/20 stroke-red-600 dark:stroke-red-400';
  const dot = good
    ? 'fill-green-600 dark:fill-green-400'
    : 'fill-red-600 dark:fill-red-400';
  // 相机在左下角 (good) / 贴下墙中央朝上 (bad)
  const cam = good ? { x: 14, y: 62 } : { x: 50, y: 66 };
  // 视锥三角形：good 罩住左墙+上墙的夹角区；bad 只罩住上面一面墙
  const cone = good ? '14,62 86,20 30,10' : '50,66 24,14 76,14';
  return (
    <figure className="flex-1">
      <svg
        viewBox="0 0 100 76"
        className="h-auto w-full"
        role="img"
        aria-label={
          good
            ? '示意图：相机位于房间角落，画面同时带到两面相邻的墙'
            : '示意图：相机正对一面墙平拍，画面只有一面墙'
        }
      >
        {/* 房间四壁 */}
        <rect
          x="8"
          y="8"
          width="84"
          height="60"
          className={`fill-none ${WALL}`}
          strokeWidth="2"
        />
        {/* 视锥 */}
        <polygon points={cone} className={accent} strokeWidth="1.5" />
        {/* 相机位 */}
        <circle cx={cam.x} cy={cam.y} r="4" className={dot} />
        {/* good：把被拍到的两面相邻墙加粗；bad：只加粗一面 */}
        {good ? (
          <>
            <line
              x1="8"
              y1="8"
              x2="92"
              y2="8"
              className="stroke-green-600 dark:stroke-green-400"
              strokeWidth="3"
            />
            <line
              x1="8"
              y1="8"
              x2="8"
              y2="68"
              className="stroke-green-600 dark:stroke-green-400"
              strokeWidth="3"
            />
          </>
        ) : (
          <line
            x1="8"
            y1="8"
            x2="92"
            y2="8"
            className="stroke-red-600 dark:stroke-red-400"
            strokeWidth="3"
          />
        )}
      </svg>
      <figcaption
        className={`mt-1 text-center text-xs font-semibold ${
          good
            ? 'text-green-700 dark:text-green-400'
            : 'text-red-700 dark:text-red-400'
        }`}
      >
        {good ? '✓ 站角落 · 两面墙入画' : '✗ 正对单面墙平拍'}
      </figcaption>
      <p className="text-center text-[11px] text-gray-500 dark:text-gray-400">
        {good ? '特征点不共面 → 能标定' : '特征全共面 → 几何上无解'}
      </p>
    </figure>
  );
}

/** 拍摄构图简示意（俯视）：角落机位 vs 正对单面墙。上传入口与标定入口共用。 */
export default function ShootingGuideDiagram({
  className = '',
}: {
  className?: string;
}) {
  return (
    <div className={`mt-2 flex max-w-xs gap-4 ${className}`}>
      <Panel variant="good" />
      <Panel variant="bad" />
    </div>
  );
}
