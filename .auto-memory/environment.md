---
name: environment
description: 生产/部署环境拓扑与红线（很少变）— 凭据不入库，见 docs/生产环境交接.md
type: reference
---

## 生产拓扑

- 链路：`Cloudflare DNS-only → dmitsvr → WireGuard → deploysvr`
- 部署机：**deploysvr**，路径 `/opt/grandtianfu`，数据 `/opt/grandtianfu/data/{projects,artifacts,uploads}`
- 旧机 `kolmatrix`：仅冻结回滚点，**非**生产真相源
- **canonical 文档：`docs/生产环境交接.md`**（任何生产/部署/DNS/数据/回滚操作前必读，覆盖历史 planning 文档）

## 部署方式

- **push `main` = 部署生产**：GitHub Actions 构建 `api`+`web` 镜像 → GHCR；VPS 主机本地 `/opt/grandtianfu/scripts/deploy.sh` 拉取（不构建）
- 主机 `.env`/Compose/scripts/Nginx/systemd **不**由 CI 同步；远端 deploy 脚本当前与仓库版本有差异——依赖门禁/回滚前先读交接文档
- CI **跑** pytest（`pytest.yml`，两套，PR + push main，Python **3.12**，装 rsvg+Noto CJK 故渲染测试真跑）＋ Playwright smoke（`e2e.yml`）
- **但两个洞**：① golden 逐字节比对被 CI 排除（`.phase0-baseline/` gitignored）→ **只有本地能跑**；② pytest 红**不挡部署**（`deploy.yml` 独立触发于 push main）→ 仍须本地先跑
- 本机 `python3` 是 **3.9.6**，生产/CI 是 **3.12** → 代码须保持 3.9 兼容

## 红线

- 文件存储无 DB；仓库 `data/projects/` 仅种子快照，**绝不**从仓库覆盖生产
- `data/uploads/` gitignored（PIPL 敏感照片），绝不提交
- `GEOM_READONLY` 置位时 `/save-geometry` 返 403（测试/smoke 护栏）
- api `--workers 1`（OOM 护栏，渲染峰值 1g），勿擅自加 worker
- **凭据不入库**：外部引用见 `docs/生产环境交接.md`

<!-- 写入规则：由 Planner 统一维护；账号密码不明文，引用 secret manager。 -->
