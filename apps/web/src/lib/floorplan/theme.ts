// SVG 画布主题色集中 (审查清单 Q2-#12)。
// 此前散落在 6+ studio 组件的颜色字面量统一收口于此; 值与原字面量逐一对应,
// 替换后渲染零变化。与已集中的 ROOM_COLORS / FURN_COLORS 看齐。

// ---- 画布 ---- //
export const CANVAS_BG = '#0b1437'; // SVG 画布底色

// ---- 通用状态描边 ---- //
export const STROKE_SELECTED = '#e0701a'; // 选中态橙色描边/把手/落点
export const STROKE_ERROR = '#dc2626'; // 重叠未合并冲突的红色高亮描边

// ---- 房间 ---- //
export const ROOM_STROKE = '#b3a98f'; // 房间默认描边 (含家具模式淡显参考层)
export const ROOM_LABEL = '#3a3024'; // 房间 id/标签文本
export const ROOM_DIM_LABEL = '#cdbfa0'; // 家具模式淡显房间标签文本
export const ROOM_FILL_FALLBACK = '#eee'; // 未知房型回退填充色

// ---- 派生墙 ---- //
export const WALL_SOLID = '#444'; // 实墙
export const WALL_DASHED = '#9a9a9a'; // 虚线墙

// ---- 自由墙 ---- //
export const FREEWALL_STROKE = '#777'; // 未选中自由墙

// ---- 开洞滑块 ---- //
export const OPENING_IDLE = 'rgba(224,112,26,0.35)'; // 未选中开洞 (STROKE_SELECTED 的半透)

// ---- 派生门 / 窗 ---- //
export const WINDOW_STROKE = '#2a6cb0';
export const DOOR_SLIDING = '#7a5a3c';
export const DOOR_ARC = '#b08a5a';
export const DOOR_LEAF = '#7a3f2a';

// ---- 把手 ---- //
export const HANDLE_FILL = '#fff';

// ---- 家具 ---- //
export const FURN_STROKE = '#9a8a6a'; // 未选中家具描边
export const FURN_LABEL = '#3a3024'; // 家具标签文本 (= ROOM_LABEL)
export const FURN_ARROW = '#7a3f2a'; // 家具朝向短线 (= DOOR_LEAF)
export const FURN_FILL_FALLBACK = '#ddd'; // 未知家具回退填充色
export const FURN_FILL_NONE = 'rgba(0,0,0,0.04)'; // color='none' 的透明占位填充
