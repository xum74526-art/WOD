# 本地开发与编译

所有命令均在 `KAI-Unified` 根目录运行。旧 KAI 与旧 WOD 目录不参与编译。

## 1. 首次安装

```bash
python3.12 -m venv services/api/.venv
services/api/.venv/bin/python -m pip install -r services/api/requirements.txt
npm ci --prefix apps/web
npm ci --prefix apps/mobile
```

本机开发默认可以使用 SQLite；生产部署必须使用 PostgreSQL。

## 2. 启动 API

```bash
cp services/api/.env.example services/api/.env
services/api/.venv/bin/alembic -c services/api/alembic.ini upgrade head
PYTHONPATH=services/api services/api/.venv/bin/uvicorn app.main:app \
  --host 127.0.0.1 --port 8100 --reload
```

检查地址：

- API 健康检查：`http://127.0.0.1:8100/health`
- OpenAPI：`http://127.0.0.1:8100/docs`

仅在本地开发库创建或重置测试账号：

```bash
PYTHONPATH=services/api services/api/.venv/bin/python \
  services/api/scripts/create_test_user.py \
  --identifier 13800000000 \
  --password 'Kai-Test-2026!' \
  --name 'KAI 测试用户'
```

脚本在 `APP_ENV=production` 时会直接拒绝执行。

### 统一登录与 Kai 配置

Web、iOS 和 Android 都支持“邮箱或手机号 + 密码”。两端使用同一个用户账号；浏览器签发 Cookie + CSRF 会话，App 签发 Bearer Token。未接入短信服务时，手机号只是登录标识，`phone_verified` 保持为 `false`。

Kai 使用服务端授权码流程、PKCE 和一次性 App 登录票据。需要先在 Kai 身份服务登记下面的后端回调地址，然后配置：

```dotenv
KAI_AUTH_ISSUER=https://auth.kai.com/api/auth
KAI_AUTH_CLIENT_ID=
KAI_AUTH_CLIENT_SECRET=
KAI_AUTH_CALLBACK_URL=https://api.example.com/api/v1/auth/kai/callback
KAI_AUTH_APP_REDIRECT_URL=kai://auth
```

默认从 `KAI_AUTH_ISSUER` 派生 `/authorize`、`/token` 和 `/userinfo`。如果 Kai 实际端点不同，显式设置：

```dotenv
KAI_AUTH_AUTHORIZATION_URL=
KAI_AUTH_TOKEN_URL=
KAI_AUTH_USERINFO_URL=
```

没有客户端 ID、密钥和回调地址时，两端仍展示一致的 Kai 入口，但按钮会明确显示“尚未配置”，不会伪造登录成功。

## 3. 启动网页

```bash
npm --prefix apps/web run dev
```

浏览器打开 `http://127.0.0.1:9100`。

## 4. 预览移动端

复制环境变量：

```bash
cp apps/mobile/.env.example apps/mobile/.env.local
npm --prefix apps/mobile run dev:h5
```

H5 只用于开发预览和 QA，正式手机浏览器仍由 Next.js 提供。

iOS/Android App 资源：

```bash
npm --prefix apps/mobile run build:app
```

然后在 HBuilderX 中导入 `apps/mobile` 源码目录进行真机运行或打包。正式 iOS 签名前必须在 `apps/mobile/src/manifest.json` 填写 DCloud AppID 和自己的 Bundle ID，并在 `.env.local` 将 `VITE_KAI_API_BASE` 指向可从手机访问的 HTTPS `/api/v1`。

当前 Mac 的局域网调试示例（只写入被 Git 忽略的 `.env.local`）：

```dotenv
VITE_KAI_API_BASE=http://192.168.31.5:8100/api/v1
```

模拟器或手机不能使用 `127.0.0.1` 访问 Mac 上的 API。局域网地址变化后需要更新此值并重新运行 App。生产发布必须改为 HTTPS 域名。

### HBuilderX 编译说明

1. 打开 HBuilderX，导入 `apps/mobile`，不要导入 `dist/build/app`。
2. “运行 → 运行到手机或模拟器”可使用标准调试基座验证 iOS/Android。
3. “发行 → 原生 App 云打包”前，必须先申请 DCloud AppID。
4. iOS 还需要自己的 Bundle ID、Apple Developer 证书和描述文件；Android 需要正式包名和 keystore。
5. 没有这些身份材料时，`build:app` 仍可生成双平台业务资源，但不能生成可安装的正式 IPA/APK/AAB。

当前本机已验证 Xcode iPhone 17 Pro 模拟器和 Pixel 9 / Android 16 模拟器登录成功。Android SDK、系统镜像和 AVD 位于外接 APFS 硬盘，具体命令见 [ANDROID_BUILD.md](ANDROID_BUILD.md)。

### 本地批量算力市场演示数据

需要测试大量服务器卡片、筛选和分页时，可从已保存的 GetDeploying 算力行情生成 120 台明确标注为“演示”的服务器：

```bash
PYTHONPATH=services/api services/api/.venv/bin/python -m scripts.seed_market_catalog --confirm-local --count 120
```

脚本只允许操作本机开发数据库，并按固定资源编号重复更新，不会在重复执行时无限追加。演示价格围绕行情中位价生成，仅用于界面和流程测试，不代表真实库存或真实商家报价。

## 5. 完整检查

```bash
./tooling/check-all.sh
```

该命令检查 API、Web、Mobile、移动 API 契约、iOS 源配置和 Linux/Windows Agent。构建产物、依赖与本地环境文件均由 `.gitignore` 排除。
