# API Contracts

此目录保存 KAI `/api/v1` 的 OpenAPI 快照、契约差异检查和客户端类型生成配置。

规则：

- `services/api` 是契约来源。
- Web 和 Mobile 不手写重复的后端响应类型。
- OpenAPI 发生不兼容变化时 CI 必须失败。
- 客户端可拥有 ViewModel，但不能重新定义后端业务状态。

生成或更新契约快照：

```bash
services/api/.venv/bin/python packages/api-contracts/export_openapi.py
```

`openapi.json` 只能从 FastAPI 导出，不手工维护第二份接口定义。后续在此基础上加入 TypeScript 类型生成与 Breaking Change 检查。
