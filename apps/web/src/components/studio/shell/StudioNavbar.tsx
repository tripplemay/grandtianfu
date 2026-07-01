'use client';

import React from 'react';
import { FiAlignJustify } from 'react-icons/fi';
import { MdPersonOutline, MdDarkMode, MdLightMode } from 'react-icons/md';
import Configurator from 'components/navbar/Configurator';
import StudioBreadcrumb, { useActivePageTitle } from './StudioBreadcrumb';
import { useProjectNav } from './ProjectNavContext';
import { applyColorMode } from 'lib/colorMode';

// Studio 顶栏:薄封装,复用 Horizon Navbar 结构与原子(Dropdown/Configurator/NavLink)。
// 与 demo Navbar 的差异:删 Notification / Info 下拉 / Buy Horizon UI PRO 营销;
// 头像区 Adela → 静态「工作台用户」占位 + 退出位(Phase 1 不接逻辑)。保留搜索 + 主题/暗色切换 + 汉堡键。
const StudioNavbar = (props: {
  onOpenSidenav: () => void;
  brandText: string;
  secondary?: boolean | string;
  brandRoot?: string;
  [x: string]: any;
}) => {
  const {
    onOpenSidenav,
    brandText,
    brandRoot = '阅天府软装',
    mini,
    hovered,
  } = props;
  const [darkmode, setDarkmode] = React.useState(
    document.body.classList.contains('dark'),
  );
  // 顶栏大标题:仅在非项目页展示(项目台/设置);项目内页名由 PageShell 标题承担,
  // 项目/户型/方案上下文由粘性 ProjectWorkflowHeader 承担, 避免同屏三处页名。
  const pageTitle = useActivePageTitle(brandText);
  const { inProject } = useProjectNav();
  return (
    <nav
      className={`duration-175 linear fixed right-3 top-3 flex flex-row flex-wrap items-center justify-between rounded-xl bg-white/30 transition-all ${
        mini === false
          ? 'w-[calc(100vw_-_6%)] md:w-[calc(100vw_-_8%)] lg:w-[calc(100vw_-_6%)] xl:w-[calc(100vw_-_350px)] 2xl:w-[calc(100vw_-_365px)]'
          : mini === true && hovered === true
          ? 'w-[calc(100vw_-_6%)] md:w-[calc(100vw_-_8%)] lg:w-[calc(100vw_-_6%)] xl:w-[calc(100vw_-_350px)] 2xl:w-[calc(100vw_-_365px)]'
          : 'w-[calc(100vw_-_6%)] md:w-[calc(100vw_-_8%)] lg:w-[calc(100vw_-_6%)] xl:w-[calc(100vw_-_180px)] 2xl:w-[calc(100vw_-_195px)]'
      }  p-2 backdrop-blur-xl dark:bg-[#0b14374d] md:right-[30px] md:top-4 xl:top-[20px]`}
    >
      <div className="ml-[6px]">
        {/* 面包屑:项目内仅「阅天府软装」根逃生;非项目内「阅天府软装 / 顶层页名」 */}
        <div className="h-6 pt-1">
          <StudioBreadcrumb rootLabel={brandRoot} topName={brandText} />
        </div>
        {!inProject && (
          <p className="shrink text-[33px] font-bold text-navy-700 dark:text-white">
            {pageTitle}
          </p>
        )}
      </div>

      <div className="relative mt-[3px] flex h-[61px] flex-grow items-center justify-around gap-2 rounded-full bg-white px-3 py-2 shadow-xl shadow-shadow-500 dark:!bg-navy-800 dark:shadow-none md:flex-grow-0 md:gap-1 xl:gap-2">
        {/* 全局搜索未接入(死控件),接入检索前不展示,避免误导 */}
        <button
          type="button"
          aria-label="打开侧栏菜单"
          title="菜单"
          className="flex cursor-pointer text-xl text-gray-600 dark:text-white xl:hidden "
          onClick={onOpenSidenav}
        >
          <FiAlignJustify className="h-5 w-5" />
        </button>
        <Configurator
          mini={props.mini}
          setMini={props.setMini}
          theme={props.theme}
          setTheme={props.setTheme}
          darkmode={darkmode}
          setDarkmode={setDarkmode}
        />
        {/* 暗色切换 (Phase 4):单一来源 applyColorMode → body.dark + localStorage 持久化 */}
        <button
          type="button"
          aria-label={darkmode ? '切换到亮色模式' : '切换到暗色模式'}
          aria-pressed={darkmode}
          title={darkmode ? '亮色模式' : '暗色模式'}
          className="cursor-pointer text-gray-600 dark:text-white"
          onClick={() => {
            const next = !darkmode;
            applyColorMode(next);
            setDarkmode(next);
          }}
        >
          {darkmode ? (
            <MdLightMode className="h-5 w-5" />
          ) : (
            <MdDarkMode className="h-5 w-5" />
          )}
        </button>
        {/* 用户区占位(静态)。登录/会话/退出未接入,接入鉴权前不放可点下拉,避免死控件误导 */}
        <div
          aria-label="工作台用户"
          title="工作台用户"
          className="flex h-10 w-10 items-center justify-center rounded-full bg-lightPrimary text-navy-700 dark:bg-navy-900 dark:text-white"
        >
          <MdPersonOutline className="h-5 w-5" />
        </div>
      </div>
    </nav>
  );
};

export default StudioNavbar;
