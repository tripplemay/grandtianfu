/* eslint-disable */
'use client';

import { HiX } from 'react-icons/hi';
import { MdLogout, MdPersonOutline } from 'react-icons/md';
import Links from 'components/sidebar/components/Links';
import {
  renderThumb,
  renderTrack,
  renderView,
  renderViewMini,
} from 'components/scrollbar/Scrollbar';
import { Scrollbars } from 'react-custom-scrollbars-2';
import Card from 'components/card';
import { IRoute } from 'types/navigation';
import { useContext } from 'react';
import { useSearchParams } from 'next/navigation';
import { ConfiguratorContext } from 'contexts/ConfiguratorContext';
import NavLink from 'components/link/NavLink';
import { projectScopedItems } from 'lib/studioRoutes';
import { useProjectNav } from './ProjectNavContext';

export interface StudioBrand {
  full: string;
  mini: string;
}

// Studio 侧栏:薄封装,复用 Horizon Sidebar 组件与原子(Links/Card/Scrollbar)。
// 与 demo Sidebar 的差异:可配品牌(brand)、删 SidebarCard 理财卡 + Adela 头像,
// 用户区替换为静态「工作台用户」占位 + 退出位(Phase 1 不接逻辑)。
function StudioSidebar(props: {
  routes: IRoute[];
  brand: StudioBrand;
  [x: string]: any;
}) {
  const { routes, brand, open, setOpen, variant, setHovered, hovered } = props;
  const context = useContext(ConfiguratorContext);
  const { mini } = context;
  const projectNav = useProjectNav();
  const searchParams = useSearchParams();
  const currentScheme = searchParams.get('scheme');
  // 文本显隐:展开 / mini+hover 时显示;mini 折叠(xl)时隐藏文字仅留图标。
  const textVis =
    mini === false
      ? 'block'
      : mini === true && hovered === true
      ? 'block'
      : 'block xl:hidden';
  return (
    <div
      className={`sm:none ${
        mini === false
          ? 'w-[285px]'
          : mini === true && hovered === true
          ? 'w-[285px]'
          : 'w-[285px] xl:!w-[120px]'
      } duration-175 linear fixed !z-50 min-h-full transition-all md:!z-50 lg:!z-50 xl:!z-0 ${
        variant === 'auth' ? 'xl:hidden' : 'xl:block'
      } ${open ? '' : '-translate-x-[110%] xl:translate-x-[unset]'}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <Card
        extra={`ml-3 w-full h-[96.5vh] sm:mr-4 sm:my-4 m-7 !rounded-[20px]`}
      >
        <Scrollbars
          autoHide
          renderTrackVertical={renderTrack}
          renderThumbVertical={renderThumb}
          renderView={
            mini === false
              ? renderView
              : mini === true && hovered === true
              ? renderView
              : renderViewMini
          }
        >
          <div className="flex h-full flex-col justify-between">
            <div>
              <button
                type="button"
                aria-label="关闭侧栏菜单"
                title="关闭"
                className="absolute right-4 top-4 block cursor-pointer xl:hidden"
                onClick={() => setOpen(false)}
              >
                <HiX />
              </button>
              <div className={`ml-[52px] mt-[44px] flex items-center `}>
                <div
                  className={`ml-1 mt-1 h-2.5 font-poppins text-[26px] font-bold text-navy-700 dark:text-white ${
                    mini === false
                      ? 'block'
                      : mini === true && hovered === true
                      ? 'block'
                      : 'hidden'
                  }`}
                >
                  {brand.full}
                </div>
                <div
                  className={`ml-1 mt-1 h-2.5 font-poppins text-[26px] font-bold text-navy-700 dark:text-white ${
                    mini === false
                      ? 'hidden'
                      : mini === true && hovered === true
                      ? 'hidden'
                      : 'block'
                  }`}
                >
                  {brand.mini}
                </div>
              </div>
              <div className="mb-7 mt-[58px] h-px bg-gray-200 dark:bg-white/10" />
              {/* Nav item */}
              <ul>
                <Links mini={mini} hovered={hovered} routes={routes} />
              </ul>

              {/* 项目作用域:命中 /studio/projects/[id]/* 时插入「当前项目」分组 (§2.2) */}
              {projectNav.inProject && (
                <div className="mt-2">
                  <div className="mx-[30px] mb-2 mt-4 flex items-center gap-2">
                    <span
                      className={`text-xs font-semibold uppercase tracking-wide text-gray-400 ${textVis}`}
                    >
                      当前项目 · {projectNav.name}
                    </span>
                    <div className="h-px flex-1 bg-gray-200 dark:bg-white/10" />
                  </div>
                  <ul>
                    {projectScopedItems.map((it) => {
                      const active = projectNav.page === it.sub;
                      const baseHref = `/studio/projects/${encodeURIComponent(
                        projectNav.id ?? '',
                      )}/${it.sub}`;
                      // 项目内切页必须保留显式方案；否则会静默退回 default，
                      // 造成家具和效果图看似“消失”。
                      const href = currentScheme
                        ? `${baseHref}?scheme=${encodeURIComponent(
                            currentScheme,
                          )}`
                        : baseHref;
                      // Phase 5:comingSoon 项 (软装方案 #4 / 效果图 #6) 改为可点达
                      // 占位页 (导航生效),仅保留「即将」徽章提示功能未完整。
                      const iconCls = active
                        ? 'text-brand-500 dark:text-white'
                        : 'text-gray-600';
                      const labelCls = active
                        ? 'font-bold text-navy-700 dark:text-white'
                        : 'font-medium text-gray-600';
                      const body = (
                        <div className="relative mb-2 flex">
                          <li className="my-[3px] flex items-center px-[30px]">
                            <span className={`flex ${iconCls}`}>{it.icon}</span>
                            <p
                              className={`leading-1 ml-4 flex items-center gap-1.5 text-sm ${labelCls} ${textVis}`}
                            >
                              {it.name}
                              {it.comingSoon && (
                                <span className="rounded bg-gray-100 px-1 py-0.5 text-[10px] font-medium text-gray-400 dark:bg-navy-700">
                                  即将
                                </span>
                              )}
                            </p>
                          </li>
                          {active && (
                            <div className="absolute right-0 top-px h-9 w-1 rounded-lg bg-brand-500 dark:bg-brand-400" />
                          )}
                        </div>
                      );
                      return (
                        <NavLink
                          key={it.sub}
                          href={href}
                          aria-label={it.name}
                          aria-current={active ? 'page' : undefined}
                          title={
                            it.comingSoon ? `${it.name} · 即将上线` : it.name
                          }
                          className="hover:cursor-pointer"
                        >
                          {body}
                        </NavLink>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>
            {/* 用户区占位(静态,不接登录/会话逻辑) */}
            <div className="mb-[30px] mt-[28px]">
              <div className="mt-5 flex items-center justify-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-lightPrimary text-navy-700 dark:bg-navy-700 dark:text-white">
                  <MdPersonOutline className="h-6 w-6" />
                </div>
                <div
                  className={`ml-1 ${
                    mini === false
                      ? 'block'
                      : mini === true && hovered === true
                      ? 'block'
                      : 'block xl:hidden'
                  }`}
                >
                  <h4 className="text-base font-bold text-navy-700 dark:text-white">
                    工作台用户
                  </h4>
                  <button
                    type="button"
                    className="mt-0.5 flex items-center gap-1 text-sm font-medium text-gray-600 hover:text-gray-700 dark:hover:text-gray-300"
                  >
                    <MdLogout className="h-3.5 w-3.5" />
                    退出
                  </button>
                </div>
              </div>
            </div>
          </div>
        </Scrollbars>
      </Card>
    </div>
  );
}

export default StudioSidebar;
