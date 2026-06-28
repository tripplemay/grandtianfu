'use client';

import React from 'react';
import Dropdown from 'components/dropdown';
import { FiAlignJustify, FiSearch } from 'react-icons/fi';
import { MdPersonOutline, MdDarkMode, MdLightMode } from 'react-icons/md';
import Configurator from 'components/navbar/Configurator';
import StudioBreadcrumb, { useActivePageTitle } from './StudioBreadcrumb';
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
  // 顶栏大标题:项目内取项目页名(编辑器/画廊),否则取顶层页名(项目台等)。
  const pageTitle = useActivePageTitle(brandText);
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
        {/* 面包屑:阅天府软装 / 项目名 / 页名(项目内);否则 阅天府软装 / 顶层页名 */}
        <div className="h-6 pt-1">
          <StudioBreadcrumb rootLabel={brandRoot} topName={brandText} />
        </div>
        <p className="shrink text-[33px] font-bold text-navy-700 dark:text-white">
          {pageTitle}
        </p>
      </div>

      <div className="relative mt-[3px] flex h-[61px] w-[355px] flex-grow items-center justify-around gap-2 rounded-full bg-white px-2 py-2 shadow-xl shadow-shadow-500 dark:!bg-navy-800 dark:shadow-none md:w-[365px] md:flex-grow-0 md:gap-1 xl:w-[365px] xl:gap-2">
        <div className="flex h-full items-center rounded-full bg-lightPrimary text-navy-700 dark:bg-navy-900 dark:text-white xl:w-[225px]">
          <p className="pl-3 pr-2 text-xl">
            <FiSearch className="h-4 w-4 text-gray-400 dark:text-white" />
          </p>
          <input
            type="text"
            placeholder="搜索..."
            aria-label="搜索"
            className="block h-full w-full rounded-full bg-lightPrimary text-sm font-medium text-navy-700 outline-none placeholder:!text-gray-400 dark:bg-navy-900 dark:text-white dark:placeholder:!text-white sm:w-fit"
          />
        </div>
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
        {/* 用户区占位(静态,不接登录/会话逻辑) */}
        <Dropdown
          button={
            <div
              role="button"
              tabIndex={0}
              aria-label="用户菜单"
              title="工作台用户"
              className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full bg-lightPrimary text-navy-700 dark:bg-navy-900 dark:text-white"
            >
              <MdPersonOutline className="h-5 w-5" />
            </div>
          }
          classNames={'py-2 top-8 -left-[180px] w-max'}
        >
          <div className="flex h-max w-56 flex-col justify-start rounded-[20px] bg-white bg-cover bg-no-repeat pb-4 shadow-xl shadow-shadow-500 dark:!bg-navy-700 dark:text-white dark:shadow-none">
            <div className="ml-4 mt-3">
              <div className="flex items-center gap-2">
                <p className="text-sm font-bold text-navy-700 dark:text-white">
                  👋 工作台用户
                </p>{' '}
              </div>
            </div>
            <div className="mt-3 h-px w-full bg-gray-200 dark:bg-white/20 " />
            <div className="ml-4 mt-3 flex flex-col">
              <button
                type="button"
                className="text-left text-sm font-medium text-red-500 hover:text-red-500"
              >
                退出
              </button>
            </div>
          </div>
        </Dropdown>
      </div>
    </nav>
  );
};

export default StudioNavbar;
