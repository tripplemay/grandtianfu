import React, { ReactNode } from 'react';
import AppWrappers from './AppWrappers';
import { COLOR_MODE_INIT_SCRIPT } from 'lib/colorMode';
// import '@asseinfo/react-kanban/dist/styles.css';
// import '/public/styles/Plugins.css';

// 暗色单一来源 (Phase 4 / §2.6):去掉写死的 body.dark,改 SSR 安全初始化——
// 在 <body> 起始注入 inline script,首屏据 localStorage('color-theme') 置 class;
// 无偏好默认 dark,保持 /admin 与 studio 现观感。suppressHydrationWarning 防 class
// 在水合前被脚本改动触发的 hydration 警告/闪烁。界面为中文,lang 改 zh-CN。
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body id={'root'} suppressHydrationWarning>
        <script
          dangerouslySetInnerHTML={{ __html: COLOR_MODE_INIT_SCRIPT }}
        />
        <AppWrappers>{children}</AppWrappers>
      </body>
    </html>
  );
}
