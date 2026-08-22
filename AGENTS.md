# KAI 仓库协作说明

本文件对整个仓库生效，供开发人员和 Codex 在克隆仓库后快速建立正确上下文。
修改 `apps/web` 时还必须遵守该目录下的 `AGENTS.md`。

## 开始工作前

按顺序阅读：

1. `README.md`：项目入口、安装和常用命令；
2. `docs/ARCHITECTURE.md`：系统边界、数据所有权和兼容层规则；
3. `docs/PRODUCTION_READINESS.md`：上线门禁和外部阻塞项；
4. `docs/DEPLOYMENT.md`：服务器发布、验收和回滚；
5. `docs/DEVELOPMENT.md`：本地启动和契约更新。

开始修改前先运行 `git status --short --branch`，保留并尊重已有未提交改动。不要用
`git reset --hard`、`git checkout --` 等命令覆盖同事的工作。

## 不可破坏的架构约束

- `services/api` 是唯一业务后端，也是唯一可以读取或写入数据库的应用。
- Web 浏览器只能调用同源 `/api/v1/*`；Next.js BFF 再转发到 FastAPI。
- iOS、Android 和 Mobile H5 共用 `apps/mobile`；原生端默认调用
  `https://wod.kai.com/api`。
- 普通本地 Web 联调也通过 `API_ORIGIN=https://wod.kai.com` 使用云端数据，不复制线上
  SQLite 文件，不在前端增加数据库配置。
- FastAPI OpenAPI 是 HTTP 契约的唯一来源。不能在 Web 或 Mobile 中独立发明订单、支付、
  钱包等业务状态。
- 新 Web 代码使用 `/api/v1/canonical/*`，新 Mobile 代码使用规范 `/api/*` 路由。旧路由只
  能在文档明确列出的兼容边界中保留。
- 密钥、Token、数据库、上传文件、证书、签名资料和构建产物不得提交到 Git。

## 修改位置

| 需求 | 首选位置 | 同步检查 |
|---|---|---|
| 数据模型或业务规则 | `services/api/app/models`、`schemas`、`services` | router、迁移、测试、OpenAPI |
| HTTP 接口 | `services/api/app/routers` | OpenAPI 快照、Web/Mobile 调用方 |
| Web 页面或 BFF | `apps/web` | 同源 Cookie、canonical 路径、Web 测试 |
| iOS/Android/H5 | `apps/mobile` | 共享实现、条件编译、Mobile 测试 |
| 反向代理或服务 | `infra` | `systemd-analyze verify`、nginx 检查、部署文档 |
| 契约检查 | `packages/api-contracts` | 重新导出 OpenAPI，不手改快照 |

复杂业务逻辑放在 `services`，router 只承担 HTTP 边界。平台差异优先使用小型适配器或
uni-app 条件编译，不复制整套页面。新增兼容层必须注明旧调用方、删除条件和测试。

## 标准工作流

```bash
# 首次安装
python3.12 -m venv services/api/.venv
services/api/.venv/bin/python -m pip install -r services/api/requirements-dev.txt
npm ci --prefix apps/web
npm ci --prefix apps/mobile

# API 路由或 schema 变化后
npm run export:openapi
npm run check:contracts

# 提交前
npm run check:all
npm run audit:deps
git diff --check
```

仅改文档时至少运行 `git diff --check`，并人工检查链接和命令。代码修改应同时补测试；不要
通过删除断言、跳过检查或扩展兼容分支来掩盖失败。

默认从最新 `main` 创建 `codex/<topic>` 或团队约定的功能分支。提交应小而完整，提交信息
说明目的。只有用户或发布负责人明确要求时才推送、合并或部署。

## 完成标准

- 修改符合 `docs/ARCHITECTURE.md` 的唯一数据源约束；
- 相关测试、类型检查、生产构建和依赖审计通过；
- API 变化已更新 OpenAPI 快照和所有调用方；
- 文档、环境变量示例和实际代码保持一致；
- 工作区没有意外生成物或未说明的文件；
- 如执行部署，GitHub、本地和云端必须指向同一提交，并按
  `docs/DEPLOYMENT.md` 完成备份、健康检查与回滚准备。
