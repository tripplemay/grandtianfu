# 阅天府软装 API 镜像 (api/worker 共用基底)。
# 关键 de-risk: librsvg2-bin + Noto CJK 字体, 保证中文房名光栅化不豆腐块。
FROM python:3.12-slim

# rsvg 光栅 + 中文字体 (对抗 #35: CJK 镜像廉价隔离 de-risk)
RUN apt-get update && apt-get install -y --no-install-recommends \
        librsvg2-bin \
        fonts-noto-cjk \
        fonts-noto-cjk-extra \
        curl \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

# 非 root 运行
RUN useradd -m -u 10001 appuser

WORKDIR /app

COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 只 COPY api 源; 引擎在运行期通过 ENGINE_DIR 挂载/COPY 接入 (本 de-risk 阶段不内置引擎)。
COPY apps/api /app

USER appuser

EXPOSE 8000

# 默认假定引擎挂载到 /engine; compose/run 时用 -e ENGINE_DIR=/engine -v <宿主引擎>:/engine:ro
ENV ENGINE_DIR=/engine

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
