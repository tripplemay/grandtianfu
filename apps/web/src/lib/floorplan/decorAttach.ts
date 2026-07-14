// 附着配饰注册表 (decor-b1) —— 前端镜像。
// **与后端 catalog.py DECOR_ATTACH 保持一致，spec §3.3 为准。**
// 附着配饰挂在宿主家具顶面, 无独立坐标; 3D/prompt 定位由后端按宿主 footprint + mount_z 处理,
// 前端只需知道「附着类型 -> 中文名 + 允许宿主白名单」用于 SidePanel 增删与换件透传过滤。
// 故本表不含 mount_z (纯后端渲染参数)。圆形宿主 (round_table/round_chair 等) 不进任何 hosts。

// 附着配饰子列表元素 (宿主 furniture item.decor 的元素)。至少含附着类型 t; 无独立坐标。
export interface DecorAttachItem {
  t: string;
}

export interface DecorAttachDef {
  zh: string;
  hosts: readonly string[];
}

// 附着类型 -> { 中文名, 允许宿主类型白名单 }。宿主列表逐字对应后端 catalog.py DECOR_ATTACH.hosts。
export const DECOR_ATTACH: Record<string, DecorAttachDef> = {
  cushions: {
    zh: '抱枕',
    hosts: ['sofa', 'chaise', 'armchair', 'bed', 'kids_bed', 'bunk_bed'],
  },
  bedding: {
    zh: '床品搭毯',
    hosts: ['bed', 'kids_bed', 'bunk_bed'],
  },
  table_lamp: {
    zh: '台灯',
    hosts: ['nightstand', 'side_table', 'console_table', 'sideboard', 'desk'],
  },
  vase: {
    zh: '花瓶花艺',
    hosts: [
      'coffee_table',
      'dining_table',
      'console_table',
      'sideboard',
      'media',
      'side_table',
    ],
  },
  ornament: {
    zh: '摆件',
    hosts: [
      'coffee_table',
      'dining_table',
      'console_table',
      'sideboard',
      'media',
      'side_table',
    ],
  },
};

// 该宿主类型允许挂载的附着配饰类型列表 (可能为空 -> 非宿主, 不显示配饰分节)。纯函数, 可单测。
export function decorTypesForHost(hostType: string): string[] {
  return Object.keys(DECOR_ATTACH).filter((t) =>
    DECOR_ATTACH[t].hosts.includes(hostType),
  );
}

// 附着配饰类型 -> 中文名 (回退类型 key)。
export function decorZh(t: string): string {
  return DECOR_ATTACH[t]?.zh ?? t;
}
