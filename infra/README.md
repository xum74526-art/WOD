# Infrastructure

此目录只保留当前 KAI 部署所需的示例和服务定义：

- `kai-api.service`：唯一 FastAPI 后端。
- `kai-collector.service`：独立外部数据采集进程，只调用本机 FastAPI 内部接口。
- `kai-frontend.service`：Next.js standalone Web。
- `kai-nginx.conf`：Web BFF 和原生 Mobile API 的反向代理。
- `api.env.example`：API 环境变量占位。
- `collector.env.example`：Collector 环境变量占位。
- `web.env.example`：Web 服务端环境变量占位。

不要在此目录保存真实密钥、数据库、上传文件或构建产物。部署步骤见 [`../docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md)。
