# 算力星图 / KAI Monorepo

算力星图是面向算力资源信息、需求撮合与商家协作的多端平台。本仓库同时维护 FastAPI 业务后端、独立数据采集服务、Next.js Web、iOS/Android 客户端、OpenAPI 契约以及静态审核页面。

## 命名说明

- **算力星图**：用户看到的 App 与平台名称。
- **KAI**：仓库内部、服务前缀、统一身份以及 KAI Pricing 行情源沿用的名称。
- KAI Pricing 是行情与商品数据来源之一，不等同于算力星图自营资源或第三方商家。

正式 Android applicationId 与 iOS Bundle ID 统一为 `com.kai.ztwstarmap`。生产域名 `wod.kai.com`、DCloud AppID、API 路径、数据源键、本地存储键以及已有订单/工单/邀请码前缀仍是兼容标识，不是对外品牌，不得做全局替换。旧 Android 包 `com.kai.wod` 仅保留独立的历史更新通道；由于 Android 不允许不同 applicationId 原位覆盖，它不能指向新的算力星图 APK。

## 当前发布模式

算力星图当前面向审核和资质准备的构建采用**撮合模式**：保留行情、曲线、资讯、需求提交、商家报价、双方合作确认、平台协调交付和历史记录查询；新直接交易、充值、提现和支付能力默认关闭。

相关代码、接口和账务模型没有删除，而是由服务端能力开关与移动端构建开关共同控制。只有资质、支付回调、对账、退款和运营流程全部验证后，才可发布启用直接交易的新版本。完整规则见 [`docs/COMMERCE_MODES.md`](docs/COMMERCE_MODES.md)。

客户端以 `GET /api/platform/capabilities` 返回的服务端能力为准；移动端直接交易还必须同时通过 `VITE_ENABLE_DIRECT_TRADE` 构建门禁。能力响应缺失、异常或不可达时按关闭处理。

## 系统架构

```text
Web Browser
  -> Next.js BFF /api/v1/canonical/*
  -> FastAPI /api/*
  -> Database configured by DATABASE_URL / private uploads

iOS / Android
  -> FastAPI /api/*
  -> Database / private uploads

External Sources
  -> Collector
  -> FastAPI /internal/v1/ingestion/*
  -> Database

KAI Pricing
  -> FastAPI scheduled Candle Agent
  -> market_price_candles
  -> read-only market APIs
```

架构约束：

- `services/api` 是唯一业务后端，也是唯一允许读写业务数据库的应用。
- Web 浏览器只调用同源 `/api/v1/canonical/*`，由 Next.js BFF 使用 HttpOnly Cookie 转发到 FastAPI。
- iOS 与 Android 使用同一 OpenAPI 契约和业务状态，不在客户端维护第二套订单、支付或钱包规则。
- `services/collector` 不连接数据库，只通过受保护的内部接口提交标准化数据。
- 运行数据库、上传文件、环境配置和发布包均位于 Git 之外。

更完整的边界定义见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

## 项目目录

| 目录 | 职责 |
|---|---|
| `apps/web` | Next.js Web 与同源 BFF；开发端口 9100 |
| `apps/ios` | uni-app iOS 客户端；H5 预览端口 9000 |
| `apps/android` | uni-app Android 客户端；H5 预览端口 9001，正式包名 `com.kai.ztwstarmap` |
| `services/api` | 唯一 FastAPI 业务后端和数据库访问者 |
| `services/collector` | 外部数据采集与标准化，只通过内部 API 提交 |
| `packages/api-contracts` | FastAPI OpenAPI 快照及客户端边界检查 |
| `static-review` | 无后端、可独立部署的静态审核页面 |
| `infra` | systemd、nginx 和生产环境变量模板 |
| `tooling` | 全仓检查、依赖审计和本地调试工具 |
| `docs` | 架构、开发、撮合模式、部署和上线门禁文档 |
| `.github/workflows` | Pull Request 与 `main` 分支 CI |

根 `package.json` 只负责统一编排命令，并不是 npm workspace。Web、iOS、Android 各自维护独立的 `package-lock.json`，依赖必须在对应子项目中安装。

## 环境要求

- Python 3.12
- Node.js 20.19+（CI 使用 Node.js 22）
- npm
- 执行根目录 `check:all` 与 `audit:deps` 需要 Linux、macOS、WSL 或兼容 Bash 的环境
- iOS 正式打包另需 macOS、Xcode、Apple 证书和 Provisioning Profile
- Android 正式打包另需 JDK 17、Android SDK/HBuilderX 和受控 keystore

## 首次安装

### Linux / macOS / WSL / Git Bash

```bash
python3.12 -m venv services/api/.venv
services/api/.venv/bin/python -m pip install -r services/api/requirements-dev.txt

python3.12 -m venv services/collector/.venv
services/collector/.venv/bin/python -m pip install -r services/collector/requirements.txt

npm ci --prefix apps/web
npm ci --prefix apps/ios
npm ci --prefix apps/android
```

### Windows PowerShell

```powershell
py -3.12 -m venv services/api/.venv
& .\services\api\.venv\Scripts\python.exe -m pip install -r services/api/requirements-dev.txt

py -3.12 -m venv services/collector/.venv
& .\services\collector\.venv\Scripts\python.exe -m pip install -r services/collector/requirements.txt

npm ci --prefix apps/web
npm ci --prefix apps/ios
npm ci --prefix apps/android
```

原生 PowerShell 可以运行各子项目命令；全仓 `.sh` 门禁请在 WSL、Git Bash 或 Linux CI 中执行。

## 本地启动

### Web

普通 Web 联调默认通过 BFF 使用云端 API，不复制生产数据库。

```powershell
$env:API_ORIGIN = "https://wod.kai.com"
npm --prefix apps/web run dev
```

```bash
API_ORIGIN=https://wod.kai.com npm --prefix apps/web run dev
```

仅在修改 FastAPI 本身时才启动本地 API 和本地沙箱数据库。具体环境文件、初始化和启动命令见 [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) 与 [`services/api/README.md`](services/api/README.md)。API 内含进程内调度任务，本地与当前生产定义均保持单 worker。

### iOS / Android H5 预览

```bash
npm --prefix apps/ios run dev:h5
npm --prefix apps/android run dev:h5
```

| 服务 | 地址 |
|---|---|
| Web | `http://127.0.0.1:9100` |
| iOS H5 | `http://127.0.0.1:9000` |
| Android H5 | `http://127.0.0.1:9001` |
| 本地 API（按需） | `http://127.0.0.1:8000` |
| Web 健康检查 | `http://127.0.0.1:9100/api/v1/health` |

## 验证与契约更新

完整依赖安装后，在 POSIX/WSL/Bash 环境执行：

```bash
npm run check:all
npm run audit:deps
git diff --check
node --test static-review/site.test.mjs
```

`check:all` 会运行 API 与 Collector 编译/单元测试、OpenAPI 一致性、Web 测试/类型检查/生产构建、iOS/Android 单元测试、i18n 检查、类型检查、App 资源构建和客户端边界检查。依赖漏洞审计由 `audit:deps` 单独执行。

只有 FastAPI router 或 schema 发生变化时才重新导出契约：

```bash
npm run export:openapi
git diff -- packages/api-contracts/openapi.json
npm run check:contracts
npm run check:all
```

`packages/api-contracts/openapi.json` 是生成物，不手工编辑。

## 移动端构建说明

- `npm run build:android:app` 与 `npm run build:ios:app` 生成 uni-app 业务资源，不等同于已签名的 APK、AAB 或 IPA。
- 正式安装包必须在对应平台环境中使用已批准的 AppID、证书和签名材料生成。
- keystore、证书、Provisioning Profile、密码、APK/AAB/IPA、DCloud 缓存和签名目录不得进入 Git。
- 移动端共同业务修改必须同步检查 iOS 与 Android；manifest、回跳、权限和签名配置保留平台差异。
- Android 和 iOS 的具体构建要求分别见 [`apps/android/README.md`](apps/android/README.md)、[`docs/ANDROID_BUILD.md`](docs/ANDROID_BUILD.md)、[`apps/ios/README.md`](apps/ios/README.md) 和 [`docs/IOS_APP_STORE_RELEASE.md`](docs/IOS_APP_STORE_RELEASE.md)。
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) 的服务器发布只更新 API 与 Web，不会自动更新已签名 APK/IPA。新 Android 包需单独上传为 `suanlixingtu.apk`，同步更新下载页的版本、大小和 SHA-256，并验证公网下载文件哈希；旧 `wod.apk` 只能继续承载 `com.kai.wod`。

## 静态审核页面

`static-review/` 是明确保留的独立静态审核站，不连接后端，也不读取正式账户。`apps/web/public/info/` 是 Web 的 `/info` 发布副本；两者属于不同部署目标，修改共享内容时必须同时验证，不能把其中一个当作可随意删除的构建产物。

```bash
python -m http.server 9200 --directory static-review
node --test static-review/site.test.mjs
```

## 配置与敏感数据

只从以下模板创建本地或服务器私有配置，README 和提交记录中不得填写真实值：

- `services/api/.env.example`
- `services/collector/.env.example`
- `apps/web/.env.example`
- `apps/ios/.env.example`
- `apps/android/.env.example`
- `infra/*.env.example`

以下内容始终禁止提交：真实 `.env`、Token、密钥、数据库、上传文件、备份、证书、签名资料、日志、测试账号、APK/AAB/IPA、`node_modules`、`.next`、`dist` 和 `unpackage`。

撮合、凭据托管、直接交易、支付、银行卡和提现是相互独立的能力开关。变量名及安全组合见 [`docs/COMMERCE_MODES.md`](docs/COMMERCE_MODES.md) 和环境模板，不要在客户端硬编码服务端能力。

## 分支与发布约定

- `main` 是唯一长期存在、可部署的分支。
- 功能修改从最新 `main` 创建短期 `codex/<topic>` 或团队约定分支，合并后删除。
- 历史发布使用 annotated tag / GitHub Release 保存，不长期堆积 `backup/*` 或服务器分支。
- 生产服务器只拉取已经审核的 `origin/main` 提交，不在服务器直接修改源码。
- 推送、合并、打包和部署均需明确授权；部署时本地、GitHub 与云端必须指向同一完整 commit SHA。

## 文档导航

| 文档 | 内容 |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 唯一数据源、请求链路、模块边界和兼容层治理 |
| [`docs/COMMERCE_MODES.md`](docs/COMMERCE_MODES.md) | 撮合审核版与未来直接交易版的能力门禁 |
| [`docs/MOBILE_CLIENTS.md`](docs/MOBILE_CLIENTS.md) | Android/iOS 共享能力、平台差异和本地验证 |
| [`docs/IOS_APP_STORE_RELEASE.md`](docs/IOS_APP_STORE_RELEASE.md) | iOS TestFlight、App Store Connect、最终 IPA 与隐私验收清单 |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | 本地开发、启动、采集与契约更新 |
| [`docs/APP_OWNERSHIP.md`](docs/APP_OWNERSHIP.md) | Web、iOS、Android 的源码边界 |
| [`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md) | 自动门禁、人工检查和外部上线条件 |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | 生产备份、发布、验收和回滚 |
| [`AGENTS.md`](AGENTS.md) | 开发人员与 Codex 的仓库协作规则 |

## 上线原则

代码检查通过不等于业务已经具备公开运营条件。正式上架前仍需完成适用的主体资质、隐私政策、客服与个人信息处理联系方式、短信/统一身份、支付与提现流程、证书签名、备份恢复和运维演练。状态与清单以 [`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md) 为准。
