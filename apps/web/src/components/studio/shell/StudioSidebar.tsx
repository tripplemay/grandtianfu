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
import { ConfiguratorContext } from 'contexts/ConfiguratorContext';

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
              <span
                className="absolute right-4 top-4 block cursor-pointer xl:hidden"
                onClick={() => setOpen(false)}
              >
                <HiX />
              </span>
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
