/** @type {import('next').NextConfig} */

// 路 A(静态导出)与 dev 代理二选一,由 NEXT_OUTPUT_EXPORT 切换:
//   - yarn build:export  → output:'export',nginx 托管静态文件(prod 路 A)
//   - yarn dev / yarn build → 普通构建 + rewrites 把 /api 代理到 FastAPI(同源,无 CORS)
const isExport = process.env.NEXT_OUTPUT_EXPORT === '1';
const API_ORIGIN = process.env.API_ORIGIN || 'http://localhost:8000';

const nextConfig = {
  basePath: process.env.NEXT_PUBLIC_BASE_PATH,
  assetPrefix: process.env.NEXT_PUBLIC_BASE_PATH,
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'images.unsplash.com' },
      { protocol: 'https', hostname: 'i.ibb.co' },
      { protocol: 'https', hostname: 'scontent.fotp8-1.fna.fbcdn.net' },
    ],
    unoptimized: true,
  },
  ...(isExport ? { output: 'export' } : {}),
  // rewrites 与 output:'export' 不兼容,仅非导出(dev/node)时启用同源 /api 代理。
  ...(isExport
    ? {}
    : {
        async rewrites() {
          return [
            { source: '/api/:path*', destination: `${API_ORIGIN}/api/:path*` },
          ];
        },
      }),
};

module.exports = nextConfig;
