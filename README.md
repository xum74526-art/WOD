# KAI

KAI 是一个 monorepo：一个 FastAPI 业务后端、一个 Next.js Web，以及一套同时生成 iOS/Android 的 uni-app Mobile。

## 架构

```text
Web Browser ──> Next.js BFF /api/v1/canonical ──┐
                                      ├──> FastAPI /api ──> wod.db
iOS / Android ─────────────────────┘
```

- `services/api` 是唯一业务后端和数据模型。
- `apps/web` 不连接数据库；BFF 使用 HttpOnly Cookie 保存会话并转发到 FastAPI。
- `apps/mobile` 是一套 Vue 3/uni-app 源码，分别生成 iOS 和 Android，不维护两套页面。
- `packages/api-contracts` 保存从 FastAPI 导出的 OpenAPI 快照并检查 Mobile 请求。
- `infra` 只保留当前 systemd/nginx 部署文件；运行数据和发布包不进 Git。

详细边界见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。
生产门禁和仍需外部配置的上线条件见 [`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md)。

## 目录

| 目录 | 职责 |
|---|---|
| `apps/web` | Next.js Web 和同源 BFF |
| `apps/mobile` | uni-app iOS/Android 共享源码 |
| `services/api` | 唯一 FastAPI 后端 |
| `packages/api-contracts` | OpenAPI 快照和契约检查 |
| `infra` | systemd、nginx 和环境变量示例 |
| `tooling` | 全仓检查和本地工具 |
| `docs` | 架构、开发、部署和移动端打包文档 |

## 本地启动

需要 Python 3.12、Node.js 20.19+ 和 npm。

```bash
# Web（默认连接云端唯一数据库）
npm ci --prefix apps/web
API_ORIGIN=https://wod.kai.com npm --prefix apps/web run dev

# Mobile H5（可选，另一终端）
npm ci --prefix apps/mobile
npm --prefix apps/mobile run dev:h5
```

- Web：`http://127.0.0.1:9100`
- Mobile H5：`http://127.0.0.1:9000`
- 云端 API 文档：`https://wod.kai.com/docs`
- Web 健康检查：`http://127.0.0.1:9100/api/v1/health`

修改 FastAPI 时可按开发文档另外启动本地沙箱数据库；普通 Web/iOS 联调一律使用云端 API。完整说明见 [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)。

## 验证

```bash
npm run export:openapi
npm run check:all
```

`check:all` 会运行 API 编译和单元测试、OpenAPI 快照一致性、Web 测试/类型检查/生产构建、Mobile 测试/类型检查，以及客户端边界检查。

## 开发原则

1. 业务数据只能由 `services/api` 写入。
2. Web 和 Mobile 可以有各自的 ViewModel，但不重新定义订单、支付、钱包等状态。
3. iOS/Android 差异只放在条件编译或平台适配层。
4. 禁止在生产服务器直接修改源码；发布必须对应一个 Git 提交。
5. 密钥、数据库、上传文件、签名资料和构建产物不进 Git。
