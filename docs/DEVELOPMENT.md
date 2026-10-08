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
python3.12 -m venv services/collector/.venv
services/collector/.venv/bin/python -m pip install -r services/collector/requirements.txt
npm ci --prefix apps/web
npm ci --prefix apps/ios
npm ci --prefix apps/android
```

## 启动 API（仅后端开发）

先为本地私有 `.env` 独立生成长随机 `SECRET_KEY` 和 Fernet `SENSITIVE_DATA_KEY`。
两者不得复用或相互派生；一旦写入持久数据库就必须在受控密钥库与备份中稳定保留，
不得在重装、重启或日常发布时重新生成。需要轮换时先设计可回滚的双密钥重加密迁移。

```bash
(cd services/api && .venv/bin/python preflight_sensitive_storage.py)
(cd services/api && .venv/bin/python init_db.py)
(cd services/api && \
  MARKET_HISTORY_SYNC_ENABLED=false \
  COMMUNITY_ONLINE_ENABLED=false \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1)
```

API 健康检查是 `http://127.0.0.1:8000/health`，OpenAPI 页面是 `http://127.0.0.1:8000/docs`。

## 启动外部数据采集（可选）

复制 `services/collector/.env.example` 为私有 `.env`，并为 Collector 与 FastAPI 配置同一个独立 ingestion token。确认来源授权后，可单次同步或启动独立调度进程：

```bash
(cd services/collector && .venv/bin/python -m collector sync all)
(cd services/collector && .venv/bin/python -m collector run)
```

Collector 只调用 `/internal/v1/ingestion/market-offers/batches`，不得连接 SQLite/PostgreSQL。该内部接口不得代理到公网。

## 同步官方行情 K 线

FastAPI 启动后会运行独立的 Candle Agent，默认每 300 秒获取最近 90 天 KAI 官方 OHLC 并幂等写入
`market_price_candles`，并在 `market_candle_sync_status` 记录最后成功时间。公开行情接口只读这些
数据库记录。首次初始化后可手动执行一次同步，避免等待启动任务：

```bash
(cd services/api && .venv/bin/python -c 'from app.services.market_candle_sync import sync_market_candles; print(sync_market_candles(force=True))')
```

同步周期和保留期分别由 `MARKET_CANDLE_SYNC_SECONDS`、`MARKET_CANDLE_HISTORY_DAYS` 控制；默认保留 100 天。

## 启动 Web（默认联调云端数据）

```bash
API_ORIGIN=https://wod.kai.com \
npm --prefix apps/web run dev
```

Web 只使用服务端 `API_ORIGIN`，不要创建 `NEXT_PUBLIC_API_ORIGIN`。这样本地 Web 的登录令牌仍由 HttpOnly Cookie 保护，业务数据与线上 Web/iOS 来自同一云端数据库。

只有修改 FastAPI 本身时才把 `API_ORIGIN` 切换为 `http://127.0.0.1:8000`，且必须同时显式设置 `API_ALLOW_INSECURE_HTTP=true`。本地 SQLite 是后端开发沙箱，不是常规前端联调数据源。

## 启动 iOS/Android 预览

```bash
npm --prefix apps/ios run dev:h5
npm --prefix apps/android run dev:h5
```

iOS 预览默认使用 9000 端口，Android 预览默认使用 9001 端口。详细 Android 环境见 [`ANDROID_BUILD.md`](ANDROID_BUILD.md)。

## 契约

后端路由变更后更新 OpenAPI 快照：

```bash
npm run export:openapi
npm run check:contracts
```

iOS/Android 新增请求必须经过各自的 `src/api/request.ts`，并能在 OpenAPI 中找到对应的路由与 HTTP 方法。
Web 新增的直通业务请求必须使用 `canonicalApiPath()`，不得在页面或客户端代码中配置数据库。

## 全量检查

```bash
npm run check:all
npm run audit:deps
git diff --check
```

移动端构建依赖中的 `braces` 暂使用仓库内的安全修复，详见
[`packages/braces/README.md`](../packages/braces/README.md)。安装依赖时保留两端
`.npmrc` 的 `install-links=true`；只复制 `apps/ios` 或 `apps/android` 目录不足以安装完整依赖。
`npm run test:dependency-security` 验证实际安装的补丁和漏洞样例，已包含在上述两项门禁中。

沿用当前协作分支完成修改，检查通过后按发布负责人要求合并到 `main`；需要隔离时再创建分支。
生产服务器不作为代码编辑环境。
