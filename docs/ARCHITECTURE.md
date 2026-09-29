# 系统架构

本文是代码评审时的架构基线。若实现与本文冲突，应先修正实现或在评审中明确更新本文，
不能通过增加临时兼容层同时保留两套业务逻辑。

## 核心结论

| 运行端 | 源码 | 对外请求入口 | 数据库访问 |
|---|---|---|---|
| 线上 Web | `apps/web` | 同源 `/api/v1/canonical/*` | 禁止 |
| 本地测试 Web | `apps/web` | BFF 转发到 `https://wod.kai.com/api` | 禁止 |
| iOS | `apps/ios` | `https://wod.kai.com/api` | 禁止 |
| Android | `apps/android` | `https://wod.kai.com/api` | 禁止 |
| 数据采集 | `services/collector` | FastAPI `/internal/v1/ingestion/*` | 禁止 |
| 云端 API | `services/api` | FastAPI `/api/*` | 唯一允许 |

因此，本地 Web、线上 Web 和手机端不需要“同步数据库文件”。它们通过同一个云端 API
读写同一个数据库，接口响应才是客户端的数据来源。

## 客户端与后端

KAI 有三个发布目标和三套明确的客户端目录：

```text
apps/web     -> Web
apps/ios     -> iOS
apps/android -> Android
```

iOS 和 Android 使用相同的 OpenAPI、订单状态和支付状态。平台目录只处理各自的界面、深度链接、权限和签名；任何业务规则仍由后端唯一实现。

`services/api` 是唯一业务后端，负责账号、商品、行情、订单、资产、钱包、商家、通知和审核。前端不得维护第二份业务数据库。

## 请求链路

```text
Web Browser
  -> Next.js /api/v1/canonical BFF
  -> FastAPI /api
  -> Database / Uploads

iOS / Android
  -> FastAPI /api
  -> Database / Uploads

External Sources
  -> Collector adapters
  -> FastAPI /internal/v1/ingestion
  -> Database

KAI Pricing
  -> Scheduled Candle Agent
  -> market_price_candles
  -> FastAPI market read endpoints
```

生产域名上的 nginx 路由优先级是：

1. `/api/v1/*` 到 Next.js BFF；
2. `/api/*`、`/health`、`/docs` 到 FastAPI；
3. 其余请求到 Next.js 页面。

不要改变前两项的顺序，否则浏览器可能绕过 HttpOnly Cookie 会话边界。
`/internal/v1/ingestion/*` 不经过公网 nginx 和 Web BFF，只允许受保护的内部网络调用。

Web BFF 只负责以下事情：

- 把后端 Token 保存在 HttpOnly、SameSite Cookie 中；
- 同源和反向代理安全检查；
- 为现有 Web 页面做有限的字段适配。

BFF 不保存业务状态，不实现第二套订单或钱包规则。

`/api/v1/mobile/*` 只是已发布 Web 链接的过渡别名；新 Web 代码必须使用
`/api/v1/canonical/*`。`/api/payments/qixiangpay/*` 同样只为已安装旧版 App
保留，当前 Web/iOS/Android 只使用 `/api/payments/qixiang/*`。这些别名不得
出现在 OpenAPI 或新客户端源码中。

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

`services/collector` 与 FastAPI 通过版本化批次契约通信。Collector 不导入 ORM、不读取业务密钥、不连接数据库；FastAPI 负责鉴权、严格校验、幂等、事务、当前报价投影和历史快照。当前 Vast 搜索属于变化中的样本，必须标记为 `incremental`，不得冒充完整快照。

KAI 官方历史 OHLC 使用独立的定时 Candle Agent。Agent 是唯一允许访问该历史上游的执行路径，
结果幂等写入 `market_price_candles`，同步状态写入 `market_candle_sync_status`。公开的
`/api/market/prices/candles`、排名和 Web BFF 只查询数据库；上游失败时继续返回最后一次成功数据，
不能在用户请求中回源，也不能把历史 OHLC 写成商品库存或当前报价。

## 契约与状态所有权

- FastAPI OpenAPI 是后端 HTTP 契约的唯一来源。
- `packages/api-contracts/openapi.json` 只能通过脚本生成。
- iOS 请求必须经过 `apps/ios/src/api/request.ts`，Android 请求必须经过
  `apps/android/src/api/request.ts`。
- Web 浏览器请求必须使用同源 `/api/v1`。
- 本地 Web 联调也把 `API_ORIGIN` 指向云端 API，因此与线上 Web 和 App 读写同一数据库。
- 订单、支付、钱包、商家审核等状态枚举由后端定义。

后端 router 或 schema 变化时必须执行：

```bash
npm run export:openapi
npm run check:contracts
```

`packages/api-contracts/openapi.json` 是生成物，不手工编辑。契约检查同时禁止客户端出现
数据库配置、废弃 API 基地址和新增旧路由调用。

## 登录与支付边界

- Web 登录凭据由 BFF 保存到 HttpOnly、SameSite Cookie，浏览器 JavaScript 不持有后端
  Token。
- 原生 App 通过系统浏览器完成 KAI OAuth，回跳地址必须在 KAI Auth、App manifest 和 API
  环境变量中保持一致。
- KAI 的 OIDC `issuer` 与 OAuth 接口前缀是两个独立值：前者用于验证授权响应和 ID Token，
  后者只用于 authorization、token、JWKS 和 userinfo 请求；正式环境必须分别配置，不能把接口
  路径当成令牌签发方。
- 首次成功完成 Kai 登录或注册时，服务端会按 Kai `issuer + subject` 原子创建一个本地平台账号、
  钱包和必要的账号记录；不会依据 Kai 返回的邮箱、手机号、昵称或任何其他资料自动合并到既有账号。
  同一 `issuer + subject` 只能对应一个本地账号，并发回调也不得产生重复账号。
- 新账号只能由已在第一方客户端明确同意当前用户协议与隐私政策的授权流程创建；同意状态随
  服务端授权 flow 保存并在回调时校验，不能只依赖客户端页面拦截。
- 已有本地账号仍可在登录后显式发起 Kai 身份绑定。绑定 ticket 一次性、短时有效，并且只能由
  发起绑定的同一已登录用户兑换；身份已属于其他账号时必须拒绝，不做自动合并。
- Kai 首次创建的账号可在登录后的设置中自愿设置本地手机号登录标识和密码。当前未接入短信服务，
  该手机号不视为归属核验，不得作为实名、资金或高风险操作的核验依据。找回邮箱仍须完成邮件验证；
  首次设置时可使用近期的 Kai 登录会话完成授权，之后的变更仍按本地凭据和服务端安全规则执行。
- 登录成功后 API 建立服务端认证会话。`created_platform` 从该会话固化为
  `web / ios / android / admin / legacy`，历史记录统一归为 `legacy`；客户端自定义请求头不会覆盖
  会话来源。管理员可通过 `/api/admin/overview`、`/users`、`/orders`、`/recharge-orders`
  以及财务列表的 `platform` 参数进行审计筛选。
- 平台来源只用于统计、排障和审计，不是授权边界。公开 Web/App 的 `client_id` 可以被复制，任何
  管理操作仍必须校验平台管理员角色；财务审核不使用独立账号或白名单。若将来需要证明是真实
  安装包或设备，应另行接入
  Apple App Attest / DeviceCheck 和 Google Play Integrity，并在服务端完成证明校验。
- 当前支付路由是 `/api/payments/qixiang/*`，支付状态最终以服务端验签后的回调或主动查单为准，
  不能以客户端跳转成功作为入账依据。
- 支付密钥只存在于云端 API 环境文件，不进入 Web、Mobile 或 Git。

## 金额与显示币种边界

- 账本、订单、充值、退款、提现和现有支付渠道统一以人民币（CNY）记账与结算，不再把卡时作为
  账户结算单位；历史字段名只作为数据库和已安装客户端的兼容边界。
- 界面语言与显示币种是两个独立偏好。首次使用可按简体中文/繁体中文/英文分别预选
  CNY/HKD/USD，用户随后可以独立选择 CNY、HKD 或 USD，切换语言不得暗中改变已选币种。
- 港币和美元只用于商品、行情和余额参考值的界面换算。充值、提现、账本、退款、返佣和订单
  实际结算金额始终明确以人民币输入、提交和保存；客户端不得把显示币种金额反向换算后发起资金操作。
- API 每日从 ECB 官方参考汇率中读取带日期的 EUR/CNY、EUR/HKD 和 EUR/USD，计算 CNY 到
  HKD/USD 的交叉汇率并保存完整快照。客户端统一从 `/api/platform/capabilities` 获取快照，不能
  各自联网取汇率或维护第二套换算规则。
- ECB 参考汇率仅用于显示换算，不作为支付渠道的实际清算汇率。上游失败时继续使用最后一份完整
  快照并标记 `rates_stale`；请求链路不访问第三方汇率服务，避免汇率上游故障影响登录和交易。
- 首次运行本版 `init_db.py` 会在同一事务内把历史结算单位按固定事实
  `1 卡时 = ¥1.002` 转为 CNY，覆盖钱包、流水、订单、收益、返佣、优惠券、商家结算与持有转让，
  但不重复换算原本就是 CNY 的支付渠道金额、KAI 行情价和 KAI 商品价。迁移通过
  `app_migrations` 幂等认领，并在 `app_migration_audits` 留存倍率和分表计数。

## 返佣账务边界

- 个人购买返佣与商家销售返佣是两个独立、版本化的计提程序；商家购买其他商家的使用型
  算力时仍按个人身份参与购买返佣。
- 个人购买返佣按当月已确认的使用型购买和续费金额定级，在资产最终到期时结算；购买持有、
  取消和未完成交付不计提。
- 商家销售返佣按当月已确认销售金额定级，基数不是平台服务费；升级后只计提新月度目标
  与当月已计提金额的差额。自购不产生销售返佣。
- 后端 `reward_accruals` 是返佣义务的唯一事实来源，保存政策版本、当时等级、封顶占用、到期
  时间和幂等键；客户端只展示后端返回的等级、封顶和进度，不维护另一份规则。
- 历史 `assets.rebate_*` 和旧返佣流水仅用于审计，不得因新开关启用而恢复为可用余额。

## 兼容层治理

兼容代码只能出现在明确的边界，并必须有保留原因：

- 支付路由别名：保护已安装旧 App 和历史回调；
- 历史 MaPay 订单查询：保护已入账订单的可追溯性；
- 数据库迁移和旧加密数据读取：保护线上数据。

页面差异、旧环境变量、开发默认值不得继续新增兼容层。
`check-client-boundaries.mjs` 和 OpenAPI 一致性检查在 CI 中强制这些边界。

新增兼容层必须同时记录：旧调用方、为何不能立即迁移、覆盖测试、停止使用的判断方式和计划
删除版本。没有这些信息的兼容分支不应合并。

## 平台差异

iOS 与 Android 可以有各自的 ViewModel，但必须保持相同的 API 契约和业务状态。跨端共同修复应同步检查两端，平台差异仅限系统能力和发布要求。

## 常见修改的影响范围

| 修改 | 至少检查 |
|---|---|
| 新增业务字段 | model、schema、service、迁移/初始化、OpenAPI、两端显示 |
| 新增 API | router、鉴权、service 测试、OpenAPI、Web/Mobile 调用 |
| 修改登录 | KAI Auth 配置、回跳白名单、Cookie/Token、安全测试 |
| 修改支付 | 下单、验签、回调幂等、查单、超时、旧订单兼容 |
| 修改 Web BFF | 同源限制、Cookie、错误映射、canonical 路径测试 |
| 修改 Mobile API 层 | HTTPS `/api` 基地址、登录过期、上传、契约检查 |
| 修改 nginx/systemd | 路由优先级、权限、健康检查、回滚流程 |
