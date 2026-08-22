# 生产部署

## 服务器目录

```text
/home/ubuntu/wod/             # Git 源码
/home/ubuntu/wod-runtime/     # 数据库、上传、环境配置
/home/ubuntu/wod-releases/    # Web 版本化发布包
/home/ubuntu/wod-backups/     # 数据库和旧版本备份
```

源码目录内只允许保留指向上述目录的兼容软链接。数据库、`.env`、上传文件和发布包不进 Git。

## 服务

- `infra/kai-api.service`：FastAPI，默认监听 `127.0.0.1:8000`。
- `infra/kai-frontend.service`：Next.js standalone，默认监听 `127.0.0.1:3000`。
- `infra/kai-nginx.conf`：`/api` 转 FastAPI，`/api/v1` 转 Next.js BFF，其余转 Web。

API 运行配置从 `infra/api.env.example` 复制，Web 运行配置从 `infra/web.env.example` 复制。真实密钥只能保存在服务器的受限文件中。

## 发布流程

1. 在 CI 或 Linux 构建机上检出确定的 Git 提交。
2. 运行 `npm run check:all`。
3. 执行 API 数据库备份，再运行 `services/api/init_db.py`。
4. 构建 Next.js standalone，发布到 `/home/ubuntu/wod-releases/<commit>/`。
5. 先在临时端口做健康检查，再原子切换 `current` 软链接。
6. 重启 API/Web，检查本机与公网的首页、`/health` 和 `/api/v1/health`。
7. 失败时切回上一发布目录，不在生产源码上临时改文件。

Web standalone 必须在 Linux 上构建，不要把 macOS 产生的原生 Node 依赖直接上传到 Linux。
