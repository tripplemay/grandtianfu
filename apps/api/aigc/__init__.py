# -*- coding: utf-8 -*-
"""阅天府 AI 子系统 (Phase 1 基础设施)。

模块:
  config    — 环境变量集中读取 + ai_enabled 判定 (凭据缺失不崩主服务)。
  errors    — AIError / ProviderError / BudgetExceeded 类型化异常。
  providers — 图像生成 provider 抽象 + OpenAI 兼容实现 (relay, /images/edits 单/多图)。
  budget    — 文件落盘原子预算护栏 (预扣/释放, 张数硬闸 + token 计量)。
  jobs      — 进程内异步任务管理 (生成 90-225s, 提交即返 job_id, 前端轮询)。
  artifacts — 生成产物/上传图 的落盘与防穿越服务 (自托管, 免外域 CSP)。
  raster    — SVG -> PNG (rsvg-convert), 第5步 img2img 底图前置。
"""
