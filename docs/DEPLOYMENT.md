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
- `infra/kai-collector.service`：可选外部数据采集进程，只访问本机 FastAPI 内部接口。
- `infra/kai-frontend.service`：Next.js standalone，默认监听 `127.0.0.1:3000`。
- `infra/kai-nginx.conf`：`/api` 转 FastAPI，`/api/v1` 转 Next.js BFF，其余转 Web。

API 运行配置从 `infra/api.env.example` 复制，Collector 从 `infra/collector.env.example` 复制，Web 从 `infra/web.env.example` 复制。API 与 Collector 使用同一个独立 ingestion token；真实密钥只能保存在服务器的受限文件中。

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
   然后重启 API/Collector/Web。
8. 检查本机和公网首页、`/health`、`/api/v1/health`、关键只读接口与服务日志。
9. 确认稳定后清理源码目录内的 `node_modules`、`.next` 等可重建产物；至少保留当前和上一
   个稳定 release，不删除运行数据库、上传目录或未经确认的备份。

### 账号找回首次启用

账号找回会增加用户找回邮箱字段、一次性恢复票据及可靠邮件队列表。首次发布必须使用与
计划发布完全相同的 API 镜像执行专用迁移，不能只依赖 `init_db.py`：

1. 保持旧 API 继续运行，先完成数据库备份并校验备份非空；
2. 确认私有 API 环境已经配置 `ACCOUNT_RECOVERY_*`，文件权限仅允许运行负责人读取；
3. 使用新 API 镜像运行 `python migrate_account_recovery.py --check`。首次检查报告缺失项并
   返回非零是预期结果；除预期的账号找回增量外，出现任何不兼容结构都必须停止发布；
4. 运行 `python migrate_account_recovery.py`，随后再次运行 `--check`，必须显示 schema ready；
5. 在 KAI/OIDC 控制台登记 `https://wod.kai.com/api/auth/kai/callback`，并确认 `https://wod.kai.com/login`、`https://wod.kai.com/reset-password`、`https://wod.kai.com/account/settings` 与原生端 `kai://auth` 均已加入 `KAI_AUTH_ALLOWED_RETURN_URLS` 的精确白名单；更换移动包名不等于更换 OAuth 回跳，除非 KAI 服务端和两个客户端在同一版本同时迁移，否则保持 `kai://auth`；
6. 再启动候选 API，检查 `/health`、找回能力配置接口和近期日志，最后才切换正式流量。

Docker 镜像必须包含 `migrate_account_recovery.py`，便于通过 `--entrypoint python` 在与正式服务
相同的依赖环境中运行。迁移只允许增加账号找回所需结构，不从 KAI 身份或其他资料自动回填
历史邮箱。容器和 systemd 启动入口会在通用 `init_db.py` 前检查该专用 schema；全新空库应先在
受控初始化步骤执行 `init_db.py`，再通过专用 `--check` 后启动服务。SMTP 授权码不得写入镜像、
Git、发布记录或命令行。

### 返佣账务首次启用

返佣升级包含新增 `reward_accruals` 表和 `ledger.ref_reward_accrual_id`，属于向后兼容的
增量迁移。首次启用时必须按以下顺序操作：

1. 先完成数据库备份，再在所有返佣开关关闭的情况下运行 `services/api/init_db.py`；
2. 确认新表、账务引用列和唯一索引已创建，且新表初始没有意外的历史补录；
3. 保持旧 `REWARD_SERVICE_ENABLED=false`、`CLOSED_TEST_REWARD_ENABLED=false`；
4. 正式启用个人购买与商家销售时设置
   `CONSUMER_REWARD_ENABLED=true`、`SUPPLIER_REWARD_ENABLED=true`、
   `REWARD_SETTLEMENT_ENABLED=true`、`REWARD_TIMEZONE=Asia/Shanghai`；
5. 邀请奖励是独立机制，除非另有业务批准，保持 `INVITE_REWARD_ENABLED=false`；
6. 重启后检查 API 日志，并用只读查询确认同一业务事件只有一个计提记录、同一计提最多
   只有一条钱包流水。

程序会拒绝在旧返佣写入器开启时启动。新开关只影响之后确认的订单或续费，不自动追溯历史
订单；暂停新计提时也不能删除已经生成的待结算义务。紧急情况下可单独关闭
`REWARD_SETTLEMENT_ENABLED` 暂停入账，待问题确认后再恢复。

Web standalone 必须在 Linux 上构建，不要把 macOS 产生的原生 Node 依赖直接上传到 Linux。

### 移动端包名迁移与更新接口

- 新 Android/iOS 标识统一为 `com.kai.ztwstarmap`，原生回跳继续使用 `kai://auth`；
- 新 Android 客户端请求 `/api/platform/app-release` 时必须携带
  `application_id=com.kai.ztwstarmap`，并只接收 `suanlixingtu.apk`；
- 未携带 `application_id` 或显式携带 `com.kai.wod` 的旧 Android 客户端只能读取
  `APP_ANDROID_LEGACY_*` 和 `wod.apk`，不能被引导安装新包作为“原位更新”；
- 上传并校验新 APK 后，才可启用/更新 `APP_ANDROID_*`；旧包不再维护时应关闭
  `APP_ANDROID_LEGACY_RELEASE_ENABLED`，不要把 legacy URL 改成新包；
- Web 构建前用新签名 APK 的实际值填写 `NEXT_PUBLIC_KAI_ANDROID_APK_SIZE` 与
  `NEXT_PUBLIC_KAI_ANDROID_APK_SHA256`；未打包时保持为空，官网会显示“待重新打包”，
  不得沿用旧 APK 的大小或摘要；
- iOS 仅在正式 App Store 页面存在后启用 `APP_IOS_RELEASE_ENABLED`，更新地址不得使用
  Android APK 或任意第三方下载页；未携带 `application_id` 的旧 iOS 客户端只读取
  `APP_IOS_LEGACY_*`，不会被引导安装不同 Bundle ID 的新应用。

## 验收命令

以下命令不包含密钥，可用于发布后只读检查：

```bash
git -C /home/ubuntu/wod status --short --branch
git -C /home/ubuntu/wod rev-parse HEAD
readlink /home/ubuntu/wod/frontend-release
systemctl is-active kai-api.service kai-collector.service kai-frontend.service
curl --fail --silent --show-error http://127.0.0.1:8000/health
curl --fail --silent --show-error http://127.0.0.1:3000/api/v1/health
curl --fail --silent --show-error https://wod.kai.com/health
curl --fail --silent --show-error https://wod.kai.com/api/v1/health
```

再检查近期日志，确认没有持续异常或重启循环：

```bash
journalctl -u kai-api.service -u kai-collector.service -u kai-frontend.service --since "15 minutes ago" --no-pager
```

日志中如果可能包含个人信息、Token 或支付参数，只在服务器上查看，不复制到公开渠道。

## 回滚

1. 停止继续发布并记录失败提交；
2. 将 `frontend-release` 软链接切回上一个已经验收的 release；
3. 重启 `kai-collector.service` 和 `kai-frontend.service` 并执行全部健康检查；
4. API 代码回滚必须使用 Git 中的已知稳定提交，不在服务器手改文件；
5. 只有数据库迁移确认向后不兼容且恢复方案经过评审时才恢复数据库备份；不要用旧数据库
   覆盖仍在写入的生产库；
6. 在本地修复、补测试、重新提交后再按正常流程发布。

## 发布记录

每次发布至少记录：发布时间、发布人、完整 commit SHA、release 路径、数据库备份路径、验证
结果和回滚版本。记录中只放路径和状态，不粘贴环境文件或任何密钥。
