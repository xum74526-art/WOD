# KAI + WOD

本仓库现在采用“手机端后端是唯一事实来源”的架构。WOD FastAPI 与它的 SQLite 数据库负责账号、商品、行情、钱包、订单、资产、商家和通知；Web 不再运行自己的数据库。

## 当前架构

```text
uni-app iOS / Android ───────────────> WOD FastAPI /api ──> wod.db
                                            ↑
Next.js Web ──> 同源 /api/v1 BFF ───────────┘
                 （无数据库，只做鉴权和字段适配）
```

| 目录 | 作用 |
|---|---|
| `apps/mobile` | 原 WOD uni-app 手机端，直接使用 WOD `/api` |
| `services/mobile-api` | 唯一业务后端与唯一数据库模型 |
| `apps/web` | Next.js Web；通过无数据库 BFF 读取/修改手机端数据 |
| `services/api` | 旧 KAI Web 后端源码，仅作历史参考，不参与当前本地运行 |
| `agent`、旧 `infra` | 旧 KAI Agent/部署源码，不属于当前手机端数据闭环 |

Web 的手机端直通契约是 `/api/v1/mobile/*`，例如 `/api/v1/mobile/wallet` 会在服务端转发为 WOD `/api/wallet`。现有 Web 页面迁移期间使用 `/api/v1` 兼容适配，适配结果仍只来自 WOD。浏览器不直接访问 WOD 地址，也不持有 WOD JWT。

## 本地启动

需要 Python 3.12、Node.js 20.19+ 和 npm。

```bash
# 1. 唯一后端
python3.12 -m venv services/mobile-api/.venv
services/mobile-api/.venv/bin/python -m pip install -r services/mobile-api/requirements.txt
(cd services/mobile-api && .venv/bin/python init_db.py)
(cd services/mobile-api && MARKET_HISTORY_SYNC_ENABLED=false COMMUNITY_ONLINE_ENABLED=false \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1)

# 2. Web（另一个终端）
npm ci --prefix apps/web
MOBILE_API_ORIGIN=http://127.0.0.1:8000 npm --prefix apps/web run dev

# 3. Mobile H5（可选，另一个终端）
npm ci --prefix apps/mobile
npm --prefix apps/mobile run dev:h5
```

- Web：`http://127.0.0.1:9100`
- Mobile H5：`http://127.0.0.1:9000`
- 手机端后端文档：`http://127.0.0.1:8000/docs`
- Web 到手机端健康检查：`http://127.0.0.1:9100/api/v1/health`

本地 SQLite 位于 `services/mobile-api/wod.db`（已被 Git 忽略）。Web 不创建 `.db` 文件，也不需要 PostgreSQL/Redis。

## 配置

Web 只使用服务端变量。当前局域网联调在 `apps/web/.env.local` 中配置：

```dotenv
MOBILE_API_ORIGIN=http://192.168.110.32:8000
MOBILE_API_ALLOW_INSECURE_HTTP=true
```

正式部署必须改为 HTTPS，并关闭开发开关：

```dotenv
MOBILE_API_ORIGIN=https://api.example.com
MOBILE_API_ALLOW_INSECURE_HTTP=false
```

不要把后端地址放进 `NEXT_PUBLIC_*`。Web 登录后把 WOD JWT 放入 HttpOnly、SameSite=Lax Cookie；浏览器 JavaScript 无法读取 Token。生产环境未设置 `MOBILE_API_ORIGIN`、使用 HTTP，或地址中包含路径和账号密码时，BFF 会拒绝启动业务请求。

## 验证

```bash
npm run check:all
```

该命令运行：

- 手机端后端编译与完整单元测试；
- Web TypeScript 检查与生产构建；
- Mobile TypeScript 检查与单元测试。

## 已停用的旧 Web 模块

手机端后端没有团队、API Key、KAI Agent、公钥自动租约和旧 Web 私有文件等模型。对应旧路由不会回退到 `services/api`，而是明确返回 HTTP 503 和 `mobile_source_unavailable`。导航已优先保留共享商品、订单、钱包、通知、地址与手机端商家流程。

生产部署前仍需配置强 `SECRET_KEY`、独立 `SENSITIVE_DATA_KEY`、持久化数据库/上传目录以及所需的行情和支付服务。
