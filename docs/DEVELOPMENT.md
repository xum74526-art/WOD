# 本地开发

所有命令均从仓库根目录执行。

## 环境

- Python 3.12
- Node.js 20.19+
- npm
- iOS 打包另需 macOS、Xcode 和签名资料
- Android 打包另需 JDK 17、Android SDK/HBuilderX 和 keystore

## 首次安装

```bash
python3.12 -m venv services/api/.venv
services/api/.venv/bin/python -m pip install -r services/api/requirements-dev.txt
npm ci --prefix apps/web
npm ci --prefix apps/mobile
```

## 启动 API（仅后端开发）

```bash
(cd services/api && .venv/bin/python init_db.py)
(cd services/api && \
  MARKET_HISTORY_SYNC_ENABLED=false \
  COMMUNITY_ONLINE_ENABLED=false \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1)
```

API 健康检查是 `http://127.0.0.1:8000/health`，OpenAPI 页面是 `http://127.0.0.1:8000/docs`。

## 启动 Web（默认联调云端数据）

```bash
API_ORIGIN=https://wod.kai.com \
npm --prefix apps/web run dev
```

Web 只使用服务端 `API_ORIGIN`，不要创建 `NEXT_PUBLIC_API_ORIGIN`。这样本地 Web 的登录令牌仍由 HttpOnly Cookie 保护，业务数据与线上 Web/iOS 来自同一云端数据库。

只有修改 FastAPI 本身时才把 `API_ORIGIN` 切换为 `http://127.0.0.1:8000`，且必须同时显式设置 `API_ALLOW_INSECURE_HTTP=true`。本地 SQLite 是后端开发沙箱，不是常规前端联调数据源。

## 启动 Mobile

```bash
npm --prefix apps/mobile run dev:h5
```

iOS 和 Android 共享 `apps/mobile`。详细 Android 环境见 [`ANDROID_BUILD.md`](ANDROID_BUILD.md)。

## 契约

后端路由变更后更新 OpenAPI 快照：

```bash
npm run export:openapi
npm run check:contracts
```

Mobile 新增请求必须经过 `apps/mobile/src/api/request.ts`，并能在 OpenAPI 中找到对应的路由与 HTTP 方法。
Web 新增的直通业务请求必须使用 `canonicalApiPath()`，不得在页面或客户端代码中配置数据库。

## 全量检查

```bash
npm run check:all
npm run audit:deps
git diff --check
```

开发时从 `main` 创建功能分支，修改在本地完成并通过检查后才合并。生产服务器不作为代码编辑环境。
