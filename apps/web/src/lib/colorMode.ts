// 暗色模式单一来源 (Phase 4 / §2.6)。
// 约定:body.dark class 控制暗色样式 (Horizon Tailwind `dark:` 变体由此驱动);
// localStorage('color-theme') 持久化用户偏好。无偏好时默认 dark,保持 /admin 与
// studio 现观感不变。首屏由 RootLayout 注入的 inline script 同步置 class,规避闪烁。

export const COLOR_MODE_KEY = 'color-theme';

export type ColorMode = 'dark' | 'light';

// 应用并持久化暗色偏好:同步改 body class + 写 localStorage。所有暗色切换入口
// (StudioNavbar 开关 / Configurator Color Mode) 统一经此,保证单一来源。
export function applyColorMode(dark: boolean): void {
  if (typeof document !== 'undefined') {
    if (dark) document.body.classList.add('dark');
    else document.body.classList.remove('dark');
  }
  try {
    window.localStorage.setItem(COLOR_MODE_KEY, dark ? 'dark' : 'light');
  } catch {
    // localStorage 不可用 (隐私模式等):降级为仅运行时 class,不阻断。
  }
}

// 读当前是否暗色:以 body class 为准 (inline script 首屏已据 localStorage 置位)。
export function isDarkMode(): boolean {
  if (typeof document === 'undefined') return true; // SSR 默认暗色。
  return document.body.classList.contains('dark');
}

// 首屏 inline script (字符串):在 <body> 起始处同步执行,据 localStorage 置 class。
// 无偏好 → 默认 dark。先于 React 水合,避免明暗闪烁 (FOUC)。
export const COLOR_MODE_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem('${COLOR_MODE_KEY}');if(t==='light'){document.body.classList.remove('dark');}else{document.body.classList.add('dark');}}catch(e){document.body.classList.add('dark');}})();`;
