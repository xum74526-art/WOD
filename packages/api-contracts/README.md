# API Contracts

此目录保存 KAI FastAPI `/api` 的 OpenAPI 快照和 Mobile 契约检查。Web 的 `/api/v1` 是 Next.js BFF 公开的同源边界，不是第二个业务后端。

规则：

- `services/api` 是契约来源。
- Mobile 请求必须经过统一请求层，并与 OpenAPI 路由匹配。
- Web 的新代码统一经过 `/api/v1/canonical/*` BFF，不再引用历史 `/mobile/*` 命名。
- 客户端不得出现 `DATABASE_URL`，也不得绕过云端 API 读写数据。
- OpenAPI 发生不兼容变化时 CI 必须失败。
- 客户端可拥有 ViewModel，但不能重新定义后端业务状态。

生成或更新契约快照：

```bash
services/api/.venv/bin/python packages/api-contracts/export_openapi.py
```

`openapi.json` 只能从 FastAPI 导出，不手工维护第二份接口定义。
