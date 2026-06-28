// 拖拽期画布覆盖反馈类型 (阶段 3 / P1-4): 实时尺寸 HUD。
// 吸附辅助线类型 SnapGuide 定义在 geometry.ts (几何域), 此处仅补充 HUD。

// 实时尺寸标签: 锚点为几何坐标 (尚未叠加 origin), 文本如 "320 × 180" / "R 22"。
// 渲染层负责叠加 origin + 随 scale 反比保持可读字号 (见 GuideLayer)。
export interface DragHud {
  x: number; // 锚点 X (几何坐标, 通常元素顶边中点)
  y: number; // 锚点 Y (几何坐标)
  text: string;
}
