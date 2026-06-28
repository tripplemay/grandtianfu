'use client';

// Studio 页脚:薄封装,版权替换为阅天府软装,去 Horizon/simmmple 营销外链。
const StudioFooter = () => {
  return (
    <div className="flex w-full flex-col items-center justify-between px-1 pb-8 pt-3 lg:px-8 xl:flex-row">
      <p className="mb-4 text-center text-sm font-medium text-gray-600 sm:!mb-0 md:text-lg">
        <span className="mb-4 text-center text-sm text-gray-600 sm:!mb-0 md:text-base">
          ©{new Date().getFullYear()} 阅天府软装 · 版权所有
        </span>
      </p>
    </div>
  );
};

export default StudioFooter;
