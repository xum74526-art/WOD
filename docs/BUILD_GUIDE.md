# 编译与发布指南

本文从全新克隆的 `KAI-Unified` 根目录开始，分别说明 API、Next.js 网页和 uni-app iOS/Android 的编译流程。

## 1. 环境要求

| 用途 | 软件 |
|---|---|
| 全平台 | Git、Node.js 22 LTS（最低 20.19）、npm 10+ |
| API | Python 3.12，本地可使用 SQLite，生产使用 PostgreSQL |
| Web | Node.js/npm |
| Mobile 源码 | Node.js/npm、HBuilderX |
| iOS | macOS、Xcode、Apple Developer 签名资料（正式包） |
| Android | Android SDK、JDK 17、Android 模拟器或真机、keystore（正式包） |
| Agent | Go 1.22+ |

## 2. 首次安装

```bash
python3.12 -m venv services/api/.venv
services/api/.venv/bin/python -m pip install -r services/api/requirements.txt
npm ci --prefix apps/web
npm ci --prefix apps/mobile
cp services/api/.env.example services/api/.env
cp apps/mobile/.env.example apps/mobile/.env.local
```

`.env` 和 `.env.local` 只属于本机，已被 Git 忽略。

## 3. 启动统一 API

```bash
services/api/.venv/bin/alembic -c services/api/alembic.ini upgrade head
PYTHONPATH=services/api services/api/.venv/bin/uvicorn app.main:app \
  --host 127.0.0.1 --port 8100 --reload
```

验证：

```bash
curl http://127.0.0.1:8100/health
```

本机默认可使用 SQLite；生产环境必须在 `services/api/.env` 使用 PostgreSQL 连接并替换所有示例密钥。

## 4. 网页端（Next.js）

### 开发运行

```bash
npm --prefix apps/web run dev
```

打开 `http://127.0.0.1:9100`。默认 API 地址来自 `apps/web/.env.example`，需要本机覆盖时创建被 Git 忽略的 `apps/web/.env.local`：

```dotenv
NEXT_PUBLIC_KAI_API_BASE_URL=http://127.0.0.1:8100
```

### 生产构建

```bash
npm run check:web
npm run build:web
npm --prefix apps/web run start
```

- 生产输出：`apps/web/.next`
- 默认生产启动端口：`9100`
- `.next` 和 `node_modules` 不得提交 Git。
- 可使用 `apps/web/Dockerfile` 或 `infra/compose.production.yml` 容器化部署。

Next.js 是正式电脑端和手机浏览器网站。

## 5. Mobile 通用源码（uni-app）

### H5 开发预览

```bash
npm --prefix apps/mobile run dev:h5
```

打开 `http://127.0.0.1:9000`。H5 只用于 App UI 开发和 QA，不取代 Next.js 正式网站。

### 检查和 App 业务资源构建

```bash
npm run check:mobile
npm run test:mobile
npm run check:mobile:ios
npm run build:mobile:app
```

输出位于 `apps/mobile/dist/build/app`。它是 iOS/Android 共用的业务资源，不是可安装包。

### App API 地址

在 `apps/mobile/.env.local` 配置手机或模拟器能访问的地址：

```dotenv
VITE_KAI_API_BASE=http://192.168.1.100:8100/api/v1
VITE_KAI_IOS_DISTRIBUTION=app-store
```

真机不能用 `127.0.0.1` 访问电脑上的 API。本地调试可使用 Mac/PC 的局域网 IP；生产必须使用可公开访问的 HTTPS `/api/v1`。

## 6. iOS 编译与打包

1. 打开 HBuilderX，导入 `apps/mobile`，不要导入 `dist/build/app`。
2. 在 `apps/mobile/src/manifest.json` 填写 DCloud AppID、正式 Bundle ID 和版本号。
3. 确认 Kai 回调 scheme 为 `kai://auth`，并在 Kai 身份服务登记同一回调。
4. 模拟器：选择“运行 → 运行到手机或模拟器 → iOS Simulator”。
5. 真机/正式包：准备 Apple Developer 团队、证书和 Provisioning Profile，再使用 HBuilderX 原生 App 打包。
6. 公开 App Store 包使用 `VITE_KAI_IOS_DISTRIBUTION=app-store`；只有合规的企业/内部发行才使用 `enterprise`。

签名证书、描述文件、IPA 和 Xcode DerivedData 都已被 Git 忽略。

## 7. Android 编译与打包

1. 准备 Android SDK、Platform Tools、Build Tools、JDK 17 和模拟器/真机。
2. 在 HBuilderX 导入 `apps/mobile`。
3. 调试：选择“运行 → 运行到手机或模拟器 → Android”。
4. 正式包前，在 `manifest.json` 填写 DCloud AppID 和唯一 applicationId，例如 `com.yourcompany.kai`。
5. 生成并妥善保管自有 keystore；不要将 keystore 和密码上传 GitHub。
6. 在 HBuilderX 选择“发行 → 原生 App 云打包”，输出 APK 用于直接安装，或 AAB 用于 Google Play。

当前 Mac 已验证的 Android SDK/AVD 路径和启动命令见 [ANDROID_BUILD.md](ANDROID_BUILD.md)。

## 8. 整仓库验证

```bash
./tooling/check-all.sh
```

该脚本会运行 API 测试、OpenAPI 导出、Web 类型检查与构建、Mobile 类型检查与测试、API 契约检查，以及 Linux/Windows Agent 测试。GitHub Actions 也会在 push 和 pull request 时执行对应检查。

## 9. 构建产物与 Git

以下内容只在本地生成，不上传 GitHub：

- `apps/web/.next`
- `apps/mobile/dist` 和 `apps/mobile/unpackage`
- `node_modules` 和 Python `.venv`
- IPA、APK、AAB、keystore、Provisioning Profile 和签名证书
- 真实 `.env`/`.env.local`（保留 `.env.example`）、本地数据库、日志、上传文件和备份

上传前请再执行 [GitHub 上传说明](GITHUB_UPLOAD.md) 中的待提交文件检查。
