# 系统架构

## 客户端与后端

KAI 有三个发布目标，但只有两套前端源码：

```text
apps/web     -> Web
apps/mobile  -> iOS
             -> Android
```

iOS 和 Android 共享 uni-app/Vue 3 的页面、状态和 API 层。只有系统权限、深度链接、推送、支付、签名等差异能进入平台适配层。

`services/api` 是唯一业务后端，负责账号、商品、行情、订单、资产、钱包、商家、通知和审核。前端不得维护第二份业务数据库。

## 请求链路

```text
Web Browser
  -> Next.js /api/v1 BFF
  -> FastAPI /api
  -> Database / Uploads

iOS / Android
  -> FastAPI /api
  -> Database / Uploads
```

Web BFF 只负责以下事情：

- 把后端 Token 保存在 HttpOnly、SameSite Cookie 中；
- 同源和反向代理安全检查；
- 为现有 Web 页面做有限的字段适配。

BFF 不保存业务状态，不实现第二套订单或钱包规则。

## API 内部边界

```text
services/api/app/
├── core/          # 配置、安全、依赖注入、限流
├── db/            # 会话和数据库基础设施
├── models/        # SQLAlchemy 持久化模型
├── schemas/       # Pydantic 请求/响应契约
├── routers/       # HTTP 边界，不堆积复杂业务逻辑
├── services/      # 业务规则、第三方集成和后台任务
├── integrations/  # 外部供应商适配
└── utils/         # 无状态工具
```

新业务功能应在 `models/schemas/routers/services` 中使用同一业务名称，避免把所有逻辑放进 `main.py` 或单个巨型 router。

## 契约与状态所有权

- FastAPI OpenAPI 是后端 HTTP 契约的唯一来源。
- `packages/api-contracts/openapi.json` 只能通过脚本生成。
- Mobile 请求必须经过 `apps/mobile/src/api/request.ts`。
- Web 浏览器请求必须使用同源 `/api/v1`。
- 订单、支付、钱包、商家审核等状态枚举由后端定义。

## 平台差异

默认先在 `apps/mobile` 共享实现。当且仅当能力确实不同时，使用 uni-app 条件编译或独立平台适配文件。不因为视觉小差异复制整个页面。
