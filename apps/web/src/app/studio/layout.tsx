'use client';
// Studio 全局壳:照搬 admin/layout.tsx 已验证的组装,换 Studio* 薄封装 + studioRoutes + brand。
// 消费根 AppWrappers 已提供的 ConfiguratorContext(mini/hovered/theme),绝不新增第二个 Provider。
import { usePathname } from 'next/navigation';
import { useContext, useState } from 'react';
import { ConfiguratorContext } from 'contexts/ConfiguratorContext';
import studioRoutes from 'lib/studioRoutes';
import {
  getActiveNavbar,
  getActiveRoute,
  isWindowAvailable,
} from 'utils/navigation';
import React from 'react';
import { Portal } from '@chakra-ui/portal';
import StudioNavbar from 'components/studio/shell/StudioNavbar';
import StudioSidebar from 'components/studio/shell/StudioSidebar';
import StudioFooter from 'components/studio/shell/StudioFooter';
import { ProjectNavProvider } from 'components/studio/shell/ProjectNavContext';
import { ToastProvider } from 'components/studio/ui/ToastHost';
import { ConfirmProvider } from 'components/studio/ui/ConfirmDialog';

const STUDIO_BRAND = { full: '阅天府软装', mini: '阅' };

export default function StudioLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [hovered, setHovered] = useState(false);
  const pathname = usePathname();
  if (isWindowAvailable()) document.documentElement.dir = 'ltr';
  const context = useContext(ConfiguratorContext);
  const { mini, theme, setTheme, setMini } = context;
  return (
    <ProjectNavProvider>
      <ConfirmProvider>
        <ToastProvider>
          <div className="flex h-full w-full bg-background-100 dark:bg-background-900">
            <StudioSidebar
              routes={studioRoutes}
              brand={STUDIO_BRAND}
              open={open}
              setOpen={() => setOpen(!open)}
              hovered={hovered}
              setHovered={setHovered}
              mini={mini}
              variant="admin"
            />
            {/* Navbar & Main Content */}
            <div className="h-full w-full font-dm dark:bg-navy-900">
              {/* Main Content */}
              <main
                className={`mx-2.5 flex-none transition-all dark:bg-navy-900 md:pr-2 ${
                  mini === false
                    ? 'xl:ml-[313px]'
                    : mini === true && hovered === true
                    ? 'xl:ml-[313px]'
                    : 'ml-0 xl:ml-[142px]'
                } `}
              >
                <div>
                  <Portal>
                    <StudioNavbar
                      onOpenSidenav={() => setOpen(!open)}
                      brandText={getActiveRoute(studioRoutes, pathname)}
                      secondary={getActiveNavbar(studioRoutes, pathname)}
                      theme={theme}
                      setTheme={setTheme}
                      hovered={hovered}
                      mini={mini}
                      setMini={setMini}
                    />
                  </Portal>
                  <div className="mx-auto min-h-screen p-2 !pt-[100px] md:p-2">
                    {children}
                  </div>
                  <div className="p-3">
                    <StudioFooter />
                  </div>
                </div>
              </main>
            </div>
          </div>
        </ToastProvider>
      </ConfirmProvider>
    </ProjectNavProvider>
  );
}
