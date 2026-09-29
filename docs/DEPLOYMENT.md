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
7. 原子更新 `/home/ubuntu/wod/frontend-release` 软链接，安装并校验仓库中的 systemd 文件。
8. 将本次提交的 `infra/kai-nginx.conf` 安装为生产实际启用的站点配置并核对文件完全一致；必须先
   执行 `nginx -t`，只有语法与引用检查通过后才允许 reload Nginx。不得只更新源码目录而继续使用
   服务器上的旧代理配置。
9. 重启 API/Collector/Web，检查本机和公网首页、`/health`、`/api/v1/health`、关键只读接口与
   服务日志。
10. 确认稳定后清理源码目录内的 `node_modules`、`.next` 等可重建产物；至少保留当前和上一
   个稳定 release，不删除运行数据库、上传目录或未经确认的备份。

标准 Ubuntu 站点路径下，Nginx 配置安装与切换至少执行以下步骤；如果现网使用不同的 include
路径，先通过 `nginx -T` 确认唯一实际加载位置，再把下列目标路径替换为该位置，不能并存两份
`default_server`：

```bash
sudo install -o root -g root -m 0644 /home/ubuntu/wod/infra/kai-nginx.conf /etc/nginx/sites-available/kai.conf
sudo ln -sfn /etc/nginx/sites-available/kai.conf /etc/nginx/sites-enabled/kai.conf
sudo cmp --silent /home/ubuntu/wod/infra/kai-nginx.conf /etc/nginx/sites-enabled/kai.conf
sudo nginx -t
sudo systemctl reload nginx
```

`cmp` 或 `nginx -t` 任一失败都必须停止发布，不得 reload；reload 后还要按下文验收实际加载的
location，而不是仅检查仓库文件。

### 敏感存储密钥预检

`SECRET_KEY` 和 Fernet `SENSITIVE_DATA_KEY` 必须在受控环境中分别生成，不得复用，也不得把
`SENSITIVE_DATA_KEY` 设为 `SECRET_KEY` 的 SHA-256/Fernet 派生值。生成后立即写入私有密钥管理系统并
保持可恢复备份；只要仍有由它们保护的持久数据，就不得因为重装、日常发布或人员变更而重新生成、覆盖或丢失。
任何轮换都必须先完成可回滚的双密钥重加密迁移，不得直接替换现有值。

在任何 schema 检查、迁移或 `init_db.py` 之前，必须先在将要运行 API 的同一私有环境执行：

```bash
cd /home/ubuntu/wod/services/api
.venv/bin/python preflight_sensitive_storage.py
```

该预检不导入数据库引擎且不读写数据库；任何报错都必须停止发布。systemd 和 Docker 入口会在
`migrate_account_recovery.py` 与 `init_db.py` 之前自动执行同一预检，`init_db.py` 及涉及敏感数据的内部迁移也有独立自守卫。

从早期版本升级时，必须在完成数据库备份后保留原 `SECRET_KEY`，再新增独立
`SENSITIVE_DATA_KEY`。通用迁移会先验证历史 `SECRET_KEY` 派生的 `enc:v1` 密文，然后立即用独立密钥重加密；
任何无法验证的密文都会使迁移失败，不得通过清空字段、停用银行卡或换新密钥绕过。

### 账号找回首次启用

账号找回会增加用户找回邮箱字段、一次性恢复票据及可靠邮件队列表。首次发布必须使用与
计划发布完全相同的 API 镜像执行专用迁移，不能只依赖 `init_db.py`：

1. 保持旧 API 继续运行，先完成数据库备份并校验备份非空；
2. 确认私有 API 环境已经配置 `ACCOUNT_RECOVERY_*`，文件权限仅允许运行负责人读取；
3. 先使用新 API 镜像运行 `python preflight_sensitive_storage.py`，通过后再运行
   `python migrate_account_recovery.py --check`。首次 schema 检查报告缺失项并
   返回非零是预期结果；除预期的账号找回增量外，出现任何不兼容结构都必须停止发布；
4. 运行 `python migrate_account_recovery.py`，随后再次运行 `--check`，必须显示 schema ready；
5. 在 KAI/OIDC 控制台登记 `https://wod.kai.com/api/auth/kai/callback`，并确认 `https://wod.kai.com/login`、`https://wod.kai.com/reset-password`、`https://wod.kai.com/account-deletion`、`https://wod.kai.com/account/settings` 与原生端 `kai://auth` 均已加入 `KAI_AUTH_ALLOWED_RETURN_URLS` 的精确白名单；更换移动包名不等于更换 OAuth 回跳，除非 KAI 服务端和两个客户端在同一版本同时迁移，否则保持 `kai://auth`；
   KAI 当前元数据中的签发方是 `https://auth.kai.com`，而 OAuth/JWKS/UserInfo 接口位于
   `https://auth.kai.com/api/auth`。生产环境必须分别填写 `KAI_AUTH_ISSUER` 与
   `KAI_AUTH_ENDPOINT_BASE`，不能把接口路径当成令牌签发方；
6. 再启动候选 API，检查 `/health`、找回能力配置接口和近期日志，最后才切换正式流量。

Docker 镜像必须同时包含 `preflight_sensitive_storage.py` 和 `migrate_account_recovery.py`，便于通过 `--entrypoint python` 在与正式服务
相同的依赖环境中运行。账号找回迁移只允许增加找回所需结构，不从 KAI 身份或其他资料自动回填
历史邮箱。KAI 首次登录创建账号所需的 `users.password_set` 兼容列由通用 `init_db.py` 以旧账号
默认已设置密码的方式补齐；它不得把 KAI 返回的邮箱、手机号或昵称回填或合并到任何历史账号。
容器和 systemd 启动入口会在通用 `init_db.py` 前检查该专用 schema；全新空库应先在
受控初始化步骤执行 `init_db.py`，再通过专用 `--check` 后启动服务。SMTP 授权码不得写入镜像、
Git、发布记录或命令行。

### 直接交易、七相充值与人工提现首次启用

这是一次需要新移动包、Web 返回页、API 配置、法律文本和运营值守同时到位的发布，不能只在
服务器把一个开关改成 `true`。仓库模板和移动端 `.env.example` 始终保持关闭；真实商户号、
密钥、银行卡资料、支付参数和审核账号不得写入 Git、命令行或发布记录。

首次启用前必须全部满足：

1. 本次 API、Web、Android 和 iOS 来自同一已审核 commit；Web 已部署
   `https://wod.kai.com/payment/qixiang/return`，该页面不采信 query，而是返回钱包并让客户端
   通过服务端查单；
2. App 内与 Web 的用户协议、隐私政策版本和正文一致，已说明七相充值、钱包余额支付、充值
   余额不可提现、退款及人工提现，并完成依法需要的重新同意；
3. Android 与 iOS 都使用递增版本号、以 `VITE_ENABLE_DIRECT_TRADE=true` 重新签名打包，完成
   真机支付回跳测试和适用商店审核；旧安装包不会因服务器开关自动出现资金入口；
4. 七相商户号与密钥已在私有环境配置，支付宝/微信中只有商户实际获批且已实测的渠道列入
   `QIXIANGPAY_PAYMENT_TYPES`；支付机构侧通知地址精确登记为
   `https://wod.kai.com/api/payments/qixiang/notify`，返回地址精确登记为
   `https://wod.kai.com/payment/qixiang/return`；服务启动门禁会同时把七相 API 固定为
   `https://api.payqixiang.cn`、原生 checkout 基址固定为 `https://wod.kai.com/api`，任一外域配置
   都必须停止发布；
5. 财务人员已经具备充值对账、异常/迟到付款、退款、银行卡审核、人工转账、凭证留存和投诉
   处理流程，并完成最小权限与双人复核安排；
6. 已备份数据库，并验证订单、支付订单、钱包流水、银行卡与提现结构均由本次 API 正常读取；
   发现任何意外 schema 差异时停止，不以开关掩盖迁移问题。

本版还包含一次性的历史卡时直转人民币迁移。必须先停止所有 API 写实例并完成数据库备份，再只让
一个发布实例运行 `services/api/init_db.py`。迁移固定使用历史生产事实 `1 卡时 = ¥1.002`，与每日
HKD/USD 展示汇率无关；成功后用只读查询确认
`app_migrations.name = '20260929_legacy_card_hours_to_direct_cny_v1'` 和同名
`app_migration_audits` 各恰有一条记录，并抽查迁移前后钱包、流水与订单的守恒关系。标记、审计记录
和金额修改在同一事务，失败时必须整体回滚；不得手工插入标记跳过金额转换，也不得再次运行旧代码
把已经转换的 CNY 当成卡时。多个启动实例即使同时到达迁移也只允许一个实例取得幂等标记。

先在全部资金写开关关闭时部署代码和配置。私有 `api.env` 至少应显式包含以下安全基线；占位
值必须替换成真实受控值，但不要把真实值输出到终端：

```dotenv
MATCHMAKING_ENABLED=true
DIRECT_TRADE_ENABLED=false
PAYMENT_SERVICE_ENABLED=false
MAPAY_ENABLED=false
MAPAY_LEGACY_RECONCILIATION_ENABLED=false
MAPAY_BASE_URL=https://mzf.mapay.cc/xpay/epayn
MAPAY_PID=<historical-private>
MAPAY_MERCHANT_PRIVATE_KEY_PATH=/run/secrets/mapay_merchant_private.pem
MAPAY_PLATFORM_PUBLIC_KEY_PATH=/run/secrets/mapay_platform_public.pem
MAPAY_HTTP_TIMEOUT=10
MAPAY_PROVIDER_TIMEZONE=Asia/Shanghai
QIXIANGPAY_ENABLED=false
QIXIANGPAY_REFUND_ENABLED=false
QIXIANGPAY_BASE_URL=https://api.payqixiang.cn
QIXIANGPAY_PID=<private>
QIXIANGPAY_KEY=<private>
QIXIANGPAY_NOTIFY_URL=https://wod.kai.com/api/payments/qixiang/notify
QIXIANGPAY_RETURN_URL=https://wod.kai.com/payment/qixiang/return
QIXIANGPAY_PUBLIC_API_BASE_URL=https://wod.kai.com/api
QIXIANGPAY_PAYMENT_TYPES=<provider-approved channels only>
PAYMENT_CHECKOUT_ALLOWED_HOSTS=api.payqixiang.cn
PAYMENT_RECONCILIATION_ENABLED=false
MANUAL_BANK_CARD_ENABLED=false
MANUAL_PAYOUT_ENABLED=false
REVENUE_SETTLEMENT_ENABLED=false
```

`MAPAY_ENABLED` 必须保持 `false`，七相是本次唯一新收款渠道；不要把“打开所有支付入口”理解为
同时启用两个收款提供商。若仍有 MaPay 历史订单，旧商户号、商户私钥和平台公钥必须保留在私有
配置/密钥挂载中，直至所有历史订单均完成通知、主动查单、入账或人工复核并完成最终对账。开启
`MAPAY_LEGACY_RECONCILIATION_ENABLED` 时，启动门禁会要求上述凭据可用，并把查询地址精确固定为
`https://mzf.mapay.cc/xpay/epayn`；不得用镜像、代理或自定义域名承载带签名的查询。历史单结清且
审计留存确认后，先关闭历史收尾开关，再按密钥管理流程撤下旧密钥文件，不得提前删除在途凭据。
MaPay 回调验签和主动查单都受该历史开关及完整配置门控；开关关闭或配置缺失时均拒绝处理，不得
依靠仍挂载的旧公钥绕过门禁写入钱包。
`REVENUE_SETTLEMENT_ENABLED` 是独立的合成算力收益写入器，普通商家
销售收入提现不依赖它，本次保持 `false`。返佣、邀请奖励、第三方公开商品目录也不随支付一并
开启。

按以下顺序启用并逐步验收：

1. 在上述关闭基线启动候选 API/Web，检查健康接口、专用返回页、`GET /api/platform/capabilities`
   的关闭态以及近期日志；同时确认 Next.js 仅监听 `127.0.0.1:3000`，公网请求只能经由会覆盖
   `X-Real-IP` 的 Nginx 进入，避免 Web 充值把回环地址提交给支付渠道；确认支付通知、checkout
   token 和专用返回页使用关闭 access log 的专用 location，通知请求体上限为 32 KiB，API 的
   有效 Uvicorn 启动命令包含 `--no-access-log`，Nginx 和 journald 中均没有签名 query 或令牌；
2. 先设置 `QIXIANGPAY_ENABLED=true`，但保持 `PAYMENT_SERVICE_ENABLED=false`。在不创建面向
   普通用户新资金承诺的收尾模式下，由受控测试账号和支付机构测试工具验证通知签名、来源限制、
   历史订单查询和专用返回页；如仍有 MaPay 历史单需要主动核对，仅设置
   `MAPAY_LEGACY_RECONCILIATION_ENABLED=true`，不得设置 `MAPAY_ENABLED=true`；启用前确认旧商户号、
   RSA 私钥/平台公钥、`Asia/Shanghai` 时区、1–55 秒请求超时和官方精确 API 地址均通过启动门禁；
3. 完成官方退款 API、结果不确定人工处置和定时主动查单验证后，分别设置
   `QIXIANGPAY_REFUND_ENABLED=true`、`PAYMENT_RECONCILIATION_ENABLED=true`。这两个开关用于
   历史收尾，不会单独开放新充值；结果不确定的退款必须由发起人之外的另一名管理员依据商户
   后台证据确认，不能由原操作人自行解除冻结；
4. 确认合格移动包已经可获取后，将 `DIRECT_TRADE_ENABLED=true`、
   `PAYMENT_SERVICE_ENABLED=true`，重启 API 并确认 capabilities 只开放预期的直接交易与充值能力；
5. 分别用商户已批准的支付宝和微信渠道完成一笔最低允许金额的真实充值。逐项核对平台订单号、
   七相订单、金额、签名通知、主动查询、唯一钱包流水和余额；重复通知或重复返回不得重复入账；
6. 在 Web、Android 真机和 iPhone 真机验证：只有精确专用 HTTPS 返回地址结束收银台，返回
   query 不直接显示成功，钱包会主动查询服务端；取消、失败、超时、迟到付款和未安装支付 App
   都进入正确状态；
7. 完成一笔钱包余额直接订单及取消/退款验证，确认账户余额按最终服务端状态退回原钱包或解除冻结，
   不错误发起外部现金退款；充值余额不得进入可提现余额；
8. 只有在财务值守已就绪后，才将 `MANUAL_BANK_CARD_ENABLED=true` 和
   `MANUAL_PAYOUT_ENABLED=true`。用受控资料验证登记、创建申请、冻结、拒绝/失败解冻、人工打款、
   凭证和完成状态；历史银行卡缺少当前版本同意记录时，必须由用户重新提交同一卡片并明示同意
   加密保存和用于人工打款与复核，系统不得允许其直接提现；页面和客服不得宣称银行四要素认证
   或自动到账。审批通过后，首位查看完整付款信息的非审批管理员会被原子绑定为唯一付款经办人，
   只有该经办人可再次查看并确认打款；不得由另一管理员另行转账。系统不自动转派经办人；经办人
   无法继续处理时不得由他人直接解冻或接管，申请必须保持冻结并进入人工事故审计；只有在原经办人
   确认银行侧未执行转账后，才可由其标记打款失败并注明原因、解除冻结，再让用户重新申请并完成
   新一轮双人审核；
9. 对照支付机构账单、平台支付订单和钱包流水完成首轮人工对账，记录订单编号与结果，不记录
   商户密钥、完整银行卡号或用户敏感信息。观察期稳定后再扩大用户范围。

支付专项回滚优先停止**新**资金承诺，不删除历史记录：先设置
`MANUAL_BANK_CARD_ENABLED=false`、`MANUAL_PAYOUT_ENABLED=false`，再设置
`PAYMENT_SERVICE_ENABLED=false`；如直接交易整体不安全，再设置 `DIRECT_TRADE_ENABLED=false`，
并保持 `MATCHMAKING_ENABLED=true`。正常回滚必须继续保持 `QIXIANGPAY_ENABLED=true`、
`QIXIANGPAY_REFUND_ENABLED=true` 和 `PAYMENT_RECONCILIATION_ENABLED=true`，以便接收通知、主动
查单、处理退款并核对回滚前已创建的订单；只有商户凭据疑似泄露或支付机构明确要求停用时，才在
建立人工收尾清单后关闭这些提供方开关。重启后确认 capabilities 已关闭新入口。不得通过清库、
删除流水或关闭回调来“回滚”。对在途充值、退款和提现建立人工清单，完成对账与用户通知后再决定
是否恢复新收款。

#### 旧 API 代码回滚门禁

紧急处置默认只关闭上述新入口，并保持**当前兼容 API**继续收回调、主动查单、退款和人工提现收尾。
“关闭功能开关”与“把代码降级到旧提交”是两个不同操作；有在途资金时不得用旧 API 替换当前收尾实现。

只要本版迁移或资金记录已存在，目标提交就必须继续支持以下安全语义；缺少任何一项均禁止回滚：

- `withdrawal_orders.payout_actor_id` 的 schema、读写和原子 CAS 绑定；
- `POST /api/finance/withdrawals/{order_id}/payment-instructions` 的原子 claim，不得恢复为可重放的 GET 查看；
- 审批人、唯一打款人与最终确认人的职责分离，以及一次性 `payment_instruction_grants`；
- 七相充值的 `review` / `late_paid_review` / `refund_pending` / `refund_unknown` 和
  `payment_refunds` 的提交中、不确定、成功、失败处置，不得把未知结果当成失败解冻。

在计划切换到任何较旧提交前，先做数据库备份，再在已加载正式私有 `DATABASE_URL` 且不回显其内容的运维会话中执行：

```bash
cd /home/ubuntu/wod/services/api
.venv/bin/python preflight_payment_rollback.py
```

该命令使用数据库只读事务，只输出固定阻断分类和条数，不读取或输出订单号、用户、卡号、Token、密钥或数据库地址。
若存在待审核/待人工打款提现、其未使用的付款信息授权、在途/待人工复核充值或非终态退款，必须返回非零并停止代码回滚。

预检通过只表示未发现已知在途资金状态，**不表示目标代码兼容**。发布负责人还必须在目标 commit 静态核对上述字段、
POST claim 路由、职责分离、授权消费与退款状态机，并使用数据库副本验证该提交可读当前 schema，才能决定是否切换。
`preflight_payment_rollback.py` 只供这次人工回滚评估，不得加入 systemd `ExecStartPre`、Docker 入口或日常启动流程。

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
systemctl is-active kai-api.service kai-collector.service kai-frontend.service nginx.service
systemctl show kai-api.service --property=ExecStart --no-pager | grep -F -- '--no-access-log'
sudo cmp --silent /home/ubuntu/wod/infra/kai-nginx.conf /etc/nginx/sites-enabled/kai.conf
sudo nginx -t
curl --fail --silent --show-error http://127.0.0.1:8000/health
curl --fail --silent --show-error http://127.0.0.1:3000/api/v1/health
curl --fail --silent --show-error https://wod.kai.com/health
curl --fail --silent --show-error https://wod.kai.com/api/v1/health
```

必须检查 `nginx -T` 输出中的**实际生效配置**，而不是只读取 Git 工作区。以下命令打印全部
15 个支付敏感 location（canonical/legacy 通知、原生/Web checkout 和专用返回页），并检查每个
块都关闭 access/error request 日志：

```bash
payment_nginx_config="$(sudo nginx -T 2>&1)"
payment_edge_locations="$(printf '%s\n' "${payment_nginx_config}" | sed -n '/location = \/api\/payments\/qixiang\/notify {/,/location = \/api\/v1 {/p' | sed '$d')"
printf '%s\n' "${payment_edge_locations}"
test "$(printf '%s\n' "${payment_edge_locations}" | grep -c 'access_log off;')" = "15"
test "$(printf '%s\n' "${payment_edge_locations}" | grep -c 'error_log /dev/null crit;')" = "15"
```

六个通知块必须同时包含 `client_max_body_size 32k`、API upstream 和
`X-Real-IP $remote_addr`；原生 checkout 必须指向 API `:8000`，Web checkout 与返回页必须指向
Next.js `:3000`。全部 15 个块必须包含 `access_log off`、`error_log /dev/null crit` 和覆盖
`X-Real-IP`。支付块的 error log 直接丢弃，因此无需为其配置 logrotate。再用不含真实支付资料的
唯一标记验证该标记不会写入 Nginx 的任何 access/error log 或应用 journald，并确认带标记的超限
通知在边缘返回 413：

```bash
payment_log_probe="edge-no-log-$(date +%s)-abcdefghij"
curl --silent --show-error --output /dev/null "https://wod.kai.com/api/payments/qixiang/notify?probe=${payment_log_probe}"
curl --silent --show-error --output /dev/null "https://wod.kai.com/api/payments/qixiang/checkout/${payment_log_probe}"
curl --silent --show-error --output /dev/null "https://wod.kai.com/api/v1/canonical/payments/qixiang/checkout/${payment_log_probe}"
curl --silent --show-error --output /dev/null "https://wod.kai.com/payment/qixiang/return?probe=${payment_log_probe}"
payment_callback_status="$(head -c 32769 /dev/zero | curl --silent --show-error --output /dev/null --write-out '%{http_code}' --header 'Content-Type: application/x-www-form-urlencoded' --data-binary @- "https://wod.kai.com/api/payments/qixiang/notify?probe=${payment_log_probe}-oversize")"
test "${payment_callback_status}" = "413"
if sudo grep -R -F -- "${payment_log_probe}" /var/log/nginx; then echo "payment route leaked into nginx logs" >&2; exit 1; fi
if sudo journalctl -u kai-api.service -u kai-frontend.service --since "2 minutes ago" --no-pager | grep -F -- "${payment_log_probe}"; then echo "payment route leaked into application journal" >&2; exit 1; fi
```

若现网 `nginx -T` 显示 access log 写入其他目录，应对所有实际 access-log 目标执行同一标记检查。
以上探针预期会得到业务层 4xx；这里只验证代理边界，不把响应当作有效支付通知或 checkout。

还必须在**隔离预发布边缘**执行一次 upstream 故障探针：让候选 API upstream 暂时不可达，对支付
通知和 checkout URL 发送另一个唯一标记，确认返回 502/504 时该标记仍未进入 Nginx access/error
log 或应用 journald。不得为此停止生产服务、修改生产 upstream，或使用真实订单号、签名和 Token。

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
