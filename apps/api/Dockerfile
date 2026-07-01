# 阅天府软装 API 镜像 (FastAPI + 内置 floorplan_core 引擎)。
# 构建上下文 = monorepo 根 (docker build -f apps/api/Dockerfile .)。
# 关键 de-risk: librsvg2-bin + Noto CJK 字体, 保证中文房名光栅化不豆腐块。
FROM python:3.12-slim

ARG APP_VERSION=dev

# rsvg 光栅 + 中文字体 + curl (供 HEALTHCHECK 探活)。
RUN apt-get update && apt-get install -y --no-install-recommends \
        librsvg2-bin \
        fonts-noto-cjk \
        fonts-noto-cjk-extra \
        curl \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

# 非 root 运行 (uid 10001 与 bind 卷 chown 对齐, 保证 save 可写)。
RUN useradd -m -u 10001 appuser

WORKDIR /app

# 引擎库内置 (现 main.py: from floorplan_core import ...; 旧 ENGINE_DIR 挂载思路已废弃)。
# 先装引擎再装 app 依赖, 利用层缓存 (引擎/依赖不变则不重装)。
COPY packages/floorplan_core /opt/floorplan_core
RUN pip install --no-cache-dir /opt/floorplan_core

COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 只 COPY api 源 (引擎已 pip 装入 site-packages, 不再运行期挂载)。
COPY apps/api/ /app/

# DATA_DIR=活数据 bind 卷; GEOM_READONLY 留空=可写 (生产红线)。
# ARTIFACTS_DIR/UPLOADS_DIR 指向 /data 下 (Phase5 各自 bind 挂载 + chown 10001 持久/备份);
# 缺省值兜底, 杜绝落到 /app/aigc/* (root 拥有且镜像内短暂, appuser 不可写 -> 上传 500、预算/产物丢失)。
ENV DATA_DIR=/data/projects HOUSE=D GEOM_READONLY= APP_VERSION=$APP_VERSION \
    ARTIFACTS_DIR=/data/artifacts UPLOADS_DIR=/data/uploads

USER appuser

EXPOSE 8000

# 真实探活 (/api/health: DATA_DIR 可写 + 引擎可导入); 失败 -> 容器 unhealthy。
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# MVP 单用户先 1 worker (配合 mem_limit, 避免 2 worker×渲染峰值 OOM); 压测后再调。
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
