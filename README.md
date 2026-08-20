# KAI Unified

KAI 算力平台的统一单仓库（monorepo）：一个 FastAPI 后端向 Next.js 网页、uni-app iOS/Android 和服务器 Agent 提供同一套 `/api/v1` 业务接口。

## 仓库结构

| 目录 | 内容 | 技术 |
|---|---|---|
| `apps/web` | 电脑端和手机浏览器 | Next.js 16 / React 19 / TypeScript |
| `apps/mobile` | iOS 和 Android App | uni-app / Vue 3 / TypeScript |
| `services/api` | 统一 API、数据库模型与迁移 | FastAPI / SQLAlchemy / Alembic |
| `packages/api-contracts` | OpenAPI 快照与 Mobile 契约检查 | Python / Node.js |
| `agent` | Linux / Windows 算力服务器 Agent | Go |
| `infra` | Docker Compose、Caddy 和部署模板 | Docker |
| `docs` | 架构、构建、测试与发布文档 | Markdown |

```text
Next.js Web ─────────┐
uni-app iOS/Android ──├──> FastAPI /api/v1 ──> PostgreSQL
KAI Agent ─────────┘
```

网页 UI 和 App UI 保持独立，账号、余额、行情、商品、订单和社区数据共用统一后端。手机浏览器使用 Next.js；uni-app H5 仅用于 App 开发预览和 QA。

## 快速开始

需要 Node.js 22 LTS（最低 20.19）、npm 10+、Python 3.12 和 Go 1.22+。iOS/Android 运行与打包还需要 HBuilderX；iOS 需要 macOS + Xcode，Android 需要 Android SDK/JDK。

```bash
# API
python3.12 -m venv services/api/.venv
services/api/.venv/bin/python -m pip install -r services/api/requirements.txt
cp services/api/.env.example services/api/.env
services/api/.venv/bin/alembic -c services/api/alembic.ini upgrade head
PYTHONPATH=services/api services/api/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8100

# Web（另一个终端）
npm ci --prefix apps/web
npm --prefix apps/web run dev

# Mobile H5 预览（另一个终端）
npm ci --prefix apps/mobile
cp apps/mobile/.env.example apps/mobile/.env.local
npm --prefix apps/mobile run dev:h5
```

- Web：`http://127.0.0.1:9100`
- Mobile H5 预览：`http://127.0.0.1:9000`
- API 文档：`http://127.0.0.1:8100/docs`

## 编译

```bash
# 网页类型检查和生产构建
npm run check:web
npm run build:web

# iOS/Android 共用业务资源
npm run check:mobile
npm run test:mobile
npm run build:mobile:app

# 整仓库检查
./tooling/check-all.sh
```

`build:mobile:app` 生成的 `apps/mobile/dist/build/app` 是 App 业务资源，不是独立 IPA/APK/AAB。正式安装包需要在 HBuilderX 配置 DCloud AppID、包名和平台签名。

完整流程见 [编译与发布指南](docs/BUILD_GUIDE.md)，本机开发见 [开发说明](docs/DEVELOPMENT.md)，GitHub 上传范围见 [GitHub 上传说明](docs/GITHUB_UPLOAD.md)。

## 当前验证状态

- 118/118 个 Mobile 网络请求通过 `/api/v1` OpenAPI 契约检查。
- API 自动测试 16/16 通过。
- Mobile 自动测试 54/54 通过，App 业务资源构建通过。
- iOS 和 Android 模拟器已完成测试账号登录和主要功能回归。

详见 [实施状态](docs/IMPLEMENTATION_STATUS.md)、[后端统一报告](docs/BACKEND_UNIFICATION_REPORT.md) 和 [Android 测试报告](docs/ANDROID_TEST_REPORT.md)。

## 安全与提交规则

- 不提交 `.env`、数据库、上传文件、日志、私钥、证书、keystore 或打包产物。
- 不提交 `node_modules`、`.venv`、`.next`、`dist` 或 `unpackage`。
- Web 写请求使用 Cookie + CSRF，App 使用限定通道的 Bearer Token。
- 支付、KYC、推送、Kai 统一认证和对象存储在没有生产密钥时必须明确不可用，不伪造成功。
