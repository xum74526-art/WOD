# 生产部署

本文供有生产权限的发布负责人或受明确授权的 Codex 使用。普通功能开发到推送 GitHub 为止；
未获得部署授权时不要连接服务器、重启服务或修改运行数据。

## 发布前提

- 目标代码已经合并到 GitHub `main`，工作区无未提交文件；
- `npm run check:all`、`npm run audit:deps` 和 CI 已通过；
- 发布负责人知道目标完整 commit SHA 和上一个稳定 release；
- 已阅读 [`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md) 并完成适用检查项；
- SSH、sudo 和运行环境文件权限已经由运维人员配置，真实密钥不出现在命令记录中。

## 服务器目录

```text
/home/ubuntu/wod/             # Git 源码
/home/ubuntu/wod-runtime/     # 数据库、上传、环境配置
/home/ubuntu/wod-releases/    # Web 版本化发布包
/home/ubuntu/wod-backups/     # 数据库和旧版本备份
```

`/home/ubuntu/wod/runtime` 是指向 `/home/ubuntu/wod-runtime` 的运行时软链接。
`/home/ubuntu/wod/frontend-release` 指向当前 Web release。数据库、`.env`、上传文件和发布包
不进 Git，也不要复制回开发机或提交到 issue/聊天记录。

## 服务

- `infra/kai-api.service`：FastAPI，默认监听 `127.0.0.1:8000`。
- `infra/kai-frontend.service`：Next.js standalone，默认监听 `127.0.0.1:3000`。
- `infra/kai-nginx.conf`：`/api` 转 FastAPI，`/api/v1` 转 Next.js BFF，其余转 Web。

API 运行配置从 `infra/api.env.example` 复制，Web 运行配置从 `infra/web.env.example` 复制。真实密钥只能保存在服务器的受限文件中。

## 发布流程

1. 记录服务器当前提交、服务状态、当前 release 和磁盘空间。
2. 把数据库备份到 `/home/ubuntu/wod-backups/`，校验文件非空并设置仅运行用户可读。
3. 在 `/home/ubuntu/wod` 执行 `git fetch origin` 和 `git pull --ff-only origin main`，确认
   实际 SHA 与计划发布 SHA 完全一致；如果服务器工作区不干净，立即停止并调查。
4. 使用锁文件安装 API 与 Web 依赖，运行 API 测试、OpenAPI 检查、Web 测试、类型检查和
   Linux production build。
5. 将 `.next/standalone`、`.next/static` 和 `public` 组合到新的
   `/home/ubuntu/wod-releases/<commit>/`，不要覆盖当前 release。
6. 在未使用的本机端口启动新 release，检查 `/api/v1/health` 和至少一个只读业务接口。
7. 原子更新 `/home/ubuntu/wod/frontend-release` 软链接，安装并校验仓库中的 systemd 文件，
   然后重启 API/Web。
8. 检查本机和公网首页、`/health`、`/api/v1/health`、关键只读接口与服务日志。
9. 确认稳定后清理源码目录内的 `node_modules`、`.next` 等可重建产物；至少保留当前和上一
   个稳定 release，不删除运行数据库、上传目录或未经确认的备份。

Web standalone 必须在 Linux 上构建，不要把 macOS 产生的原生 Node 依赖直接上传到 Linux。

## 验收命令

以下命令不包含密钥，可用于发布后只读检查：

```bash
git -C /home/ubuntu/wod status --short --branch
git -C /home/ubuntu/wod rev-parse HEAD
readlink /home/ubuntu/wod/frontend-release
systemctl is-active kai-api.service kai-frontend.service
curl --fail --silent --show-error http://127.0.0.1:8000/health
curl --fail --silent --show-error http://127.0.0.1:3000/api/v1/health
curl --fail --silent --show-error https://wod.kai.com/health
curl --fail --silent --show-error https://wod.kai.com/api/v1/health
```

再检查近期日志，确认没有持续异常或重启循环：

```bash
journalctl -u kai-api.service -u kai-frontend.service --since "15 minutes ago" --no-pager
```

日志中如果可能包含个人信息、Token 或支付参数，只在服务器上查看，不复制到公开渠道。

## 回滚

1. 停止继续发布并记录失败提交；
2. 将 `frontend-release` 软链接切回上一个已经验收的 release；
3. 重启 `kai-frontend.service` 并执行全部健康检查；
4. API 代码回滚必须使用 Git 中的已知稳定提交，不在服务器手改文件；
5. 只有数据库迁移确认向后不兼容且恢复方案经过评审时才恢复数据库备份；不要用旧数据库
   覆盖仍在写入的生产库；
6. 在本地修复、补测试、重新提交后再按正常流程发布。

## 发布记录

每次发布至少记录：发布时间、发布人、完整 commit SHA、release 路径、数据库备份路径、验证
结果和回滚版本。记录中只放路径和状态，不粘贴环境文件或任何密钥。
