# Web 端以手机端为蓝本的功能重构方案

## 1. 目标

手机端是当前产品功能和业务数据的事实标准。Web 不再维护独立业务模型，也不恢复旧 KAI 后端；所有可用功能通过 Next.js 同源 BFF 访问 WOD 后端 `MOBILE_API_ORIGIN`。

```text
iOS / Android ───────────────> WOD /api ──> 唯一业务数据库
Web 浏览器 ──> /api/v1 BFF ──┘
```

重构遵循四条约束：

1. Web 页面使用与手机端相同的账号、余额、商品、订单、资产和经营数据。
2. 浏览器不直接访问 WOD，不读取或保存 WOD JWT。
3. 没有手机端数据源的旧 Web 功能不伪造数据；旧 Web API、页面与路由作为兼容能力保留，不删除，但不作为新的商业主流程数据源。
4. Web 不是手机页面的等比放大版，而是把同一业务重排为适合桌面端的运营台、数据表和批量操作界面。

## 2. 当前差距

远端 OpenAPI 当前包含约 150 个“HTTP 方法 + 路径”操作。2026-08-21 重构后，Web 已覆盖手机端的主要交易、账户、内容、客服、求购和财务审核闭环；未覆盖项集中在首次引导、行情高级视图、财务银行卡复核/审计日志，以及没有手机端数据模型的旧 Web 模块。

| 业务域 | 手机端 | Web 重构前 | 目标状态 |
|---|---|---|---|
| 登录、用户资料 | 完整 | 手机号登录可用，部分旧邮箱入口无数据源 | 统一手机号/Kai 登录和手机端资料 |
| 商品、行情、购买 | 完整 | 商品和行情可用，购买流程部分可用 | 保持同源并补齐真实订单状态 |
| 个人资产 | 资产、算力、到期、收益入口齐全 | 仍跳转到旧服务器租约 | 改用 `/api/assets`，提供资产总览和到期视图 |
| 钱包、充值、提现 | 钱包、Mapay、银行卡、提现齐全 | 钱包只读，仍保留旧支付 Intent | 改用手机端钱包、充值订单和提现订单 |
| 收益、返佣 | 收益趋势、明细、返佣进度 | 占位页 | 接入 `/api/revenue`、`/api/user/rebate` |
| 银行卡、实名认证 | 可提交和管理 | 旧 KYC Provider 页面 | 改用 `/api/verification`、`/api/bank-cards` |
| 优惠券、邀请 | 完整 | 占位页 | 提供查看、兑换、邀请记录 |
| 求购与报价 | 买家、卖家流程 | 旧 Web 状态机与手机端不一致 | 已改为 `/api/buy-requests` 状态模型 |
| 通知、地址 | 完整 | 已使用手机端接口 | 已补齐通知偏好设置 |
| 社区、客服 | 帖子、评论、关注、客服工单 | 原旧新闻/视频接口失效 | 已迁移到 `/api/community`、`/api/chat` |
| 商家设备、订单 | 完整 | 设备与交付基本可用 | 补齐经营统计、收益、返佣、店铺资料 |
| 管理与财务审核 | 手机端财务角色可用 | 原旧 KAI 管理接口无数据源 | 实名、提现和银行卡复核已改用 `/api/finance`；审计日志待补 |

## 3. Web 信息架构

### 买家中心

1. 总览
2. 个人资产
3. 采购订单
4. 求购与报价
5. 钱包与提现
6. 收益与返佣
7. 优惠券
8. 邀请记录
9. 银行卡
10. 实名认证
11. 通知中心
12. 地址与账户设置

### 商家后台

1. 经营总览
2. 设备与算力商品
3. 交付订单
4. 收益与提现
5. 经营统计
6. 商家返佣
7. 店铺资料

桌面端采用“左侧业务导航 + 顶部数据源状态 + 主区域数据账本”的结构。青色数据脊线用于标识实时手机端数据，状态、金额和到期风险使用一致的语义色，不使用无业务含义的装饰卡片。

## 4. API 映射

Web 页面统一请求 `/api/v1/mobile/*` 或经过字段适配的 `/api/v1/*`；BFF 在服务端转发到对应的 WOD `/api/*`。

| Web 功能 | Web BFF | WOD API |
|---|---|---|
| 资产总览 | `/api/v1/mobile/assets` | `GET /api/assets` |
| 资产详情/出售 | `/api/v1/mobile/assets/{id}` | `GET /api/assets/{id}`、`POST /sell` |
| 收益 | `/api/v1/mobile/revenue*` | `GET /api/revenue*` |
| 消费返佣 | `/api/v1/mobile/user/rebate` | `GET /api/user/rebate` |
| 优惠券 | `/api/v1/mobile/coupons*` | `GET /api/coupons`、`POST /redeem` |
| 邀请 | `/api/v1/mobile/invite/*` | `GET /api/invite/*` |
| 银行卡 | `/api/v1/mobile/bank-cards*` | `/api/bank-cards*` |
| 实名认证 | `/api/v1/mobile/verification` | `GET/POST /api/verification` |
| 提现 | `/api/v1/mobile/withdrawals*` | `/api/withdrawals*` |
| 商家经营 | `/api/v1/mobile/supplier/*` | `/api/supplier/*` |
| 账户资料 | `/api/v1/mobile/user/*` | `/api/user/profile`、`/avatar`、`/password`、`/role/switch` |
| 通知偏好 | `/api/v1/mobile/notifications/preferences` | `/api/notifications/preferences` |
| 订单续费 | `/api/v1/account/orders/{id}/renew` | `/api/orders/{id}/renew` |
| 社区 | `/api/v1/mobile/community/*` | `/api/community/*` |
| 在线客服 | `/api/v1/mobile/chat*` | `/api/chat*` |
| 求购报价 | `/api/v1/mobile/buy-requests*` | `/api/buy-requests*` |
| 财务审核 | `/api/v1/mobile/finance/*` | `/api/finance/*` |
| 真实行情 | `/api/v1/mobile/market/*` | `/api/market/models`、`/prices/latest`、`/prices/candles`、`/sources/status` |
| 设备托管 | `/api/v1/mobile/onboarding*` | `/api/onboarding`、`/api/onboarding/mine` |
| 商家店铺 | `/api/v1/mobile/supplier/{id}` | `/api/supplier/{id}` |

## 5. 分阶段实施

### 第一阶段：交易闭环和个人中心

- [x] 个人资产替换旧租约跳转。
- [x] 补齐收益、返佣、优惠券、邀请、银行卡、实名认证。
- [x] 钱包改用手机端余额、流水、Mapay 充值和银行卡提现模型。
- [x] 商家收益、统计、返佣和资料改用手机端数据。
- [x] 扩展买家中心和商家后台导航。
- [x] 新增同源 BFF 自动化测试，覆盖个人中心 14 个手机端业务接口。

### 第二阶段：内容和服务

- [x] Web 社区迁移到手机端帖子、媒体、评论、点赞和关注。
- [x] 在线客服迁移到 `/api/chat` 和工单。
- [x] 求购报价动作统一为手机端状态机，买卖双方共用同一需求和报价。

### 第三阶段：运营后台

- [x] 实名认证和提现结算迁移到 `/api/finance`。
- [x] 没有手机端数据模型的旧管理能力从主导航移除。
- [x] 补齐银行卡登记复核，并使用 `/api/finance/me` 判断财务管理员权限。
- [ ] 补齐财务审计日志页面。
- [x] 按产品要求保留团队、API Key、旧 Agent 租约、旧 Ping++ 等旧 Web API 和页面，作为后续兼容能力。

### 第四阶段：高级数据与详情（进行中）

- [x] 行情主图接入真实 OHLC candles、latest 报价、型号目录和数据源状态。
- [x] 新增设备托管申请与记录。
- [x] 新增资产详情页，使用 `/api/assets/{id}`。
- [x] 新增手机端商家店铺详情入口。
- [x] 求购列表同时读取 `/api/buy-requests/summary`。
- [ ] 社区独立详情页、财务审计日志、提现详情轮询继续补齐。

### 第一阶段页面与接口清单

| Web 页面 | 已接入的手机端接口 | 可用操作 |
|---|---|---|
| `/account/assets` | `/api/assets`、`/api/assets/{id}/sell` | 筛选、查看状态/收益/到期、出售 |
| `/account/revenue` | `/api/revenue*`、`/api/user/rebate` | 收益摘要、趋势、明细、返佣进度 |
| `/account/referrals` | `/api/invite/summary`、`/api/invite/records` | 复制邀请码、查看邀请和奖励 |
| `/account/coupons` | `/api/coupons`、`/api/coupons/redeem` | 分类查看、兑换优惠券 |
| `/account/bank-accounts` | `/api/bank-cards*` | 添加、默认卡、解绑 |
| `/account/verification` | `/api/verification` | 提交实名资料、查看审核状态 |
| `/account/wallet` | `/api/wallet*`、`/api/payments/mapay/*`、`/api/withdrawals*` | 流水、充值、提现、取消提现 |
| `/supplier/revenue` | `/api/supplier/wallet`、`/api/supplier/revenue/detail` | 收益与结算明细 |
| `/supplier/analytics` | `/api/supplier/stats` | 设备利用率、营收趋势、关注项 |
| `/supplier/rebates` | `/api/supplier/rebate` | 返佣阶梯和进度 |
| `/supplier/settings` | `/api/supplier/mine`、`PUT /api/supplier/profile` | 查看审核状态、维护店铺资料 |
| `/account/settings` | `/api/user/profile`、`/avatar`、`/password`、`/role/switch` | 用户名、头像、密码、身份切换 |
| `/account/notifications` | `/api/notifications*` | 阅读、全部已读、分类通知开关 |
| `/account/orders` | `/api/orders*` | 查看、交付确认、取消、续费 |
| `/community` | `/api/community/*` | 动态、媒体、搜索、关注、点赞、评论、发布 |
| `/support` | `/api/chat*` | 自助客服、历史消息、客服工单 |
| `/account/requests`、`/supplier/requests` | `/api/buy-requests*` | 发布需求、报价、选择报价 |
| `/admin/kyc` | `/api/finance/verifications*` | 证件照片核验、通过、驳回 |
| `/admin/withdrawals` | `/api/finance/withdrawals*` | 审核、揭示收款资料、凭证上传、标记打款 |
| `/admin/bank-cards` | `/api/finance/me`、`/api/finance/bank-cards*` | 财务权限校验、登记复核、通过、驳回 |
| `/market/trends` | `/api/market/models`、`/prices/latest`、`/prices/candles`、`/sources/status` | 真实 OHLC、实时中位价、数据源健康状态 |
| `/account/hosting` | `/api/onboarding`、`/api/onboarding/mine` | 个人/企业托管申请、处理记录 |
| `/account/assets/{id}` | `/api/assets/{id}` | 资产状态、收益、周期、交易限制 |
| `/stores/{id}` | `/api/supplier/{id}` | 商家资料和可售商品 |

## 6. 验收标准

- Web 页面不出现 `mobile_source_unavailable` 的可见主导航入口。
- 同一账号在 iOS 与 Web 看到相同的余额、资产、订单、收益和商家数据。
- 所有写操作经过 BFF 同源校验，JWT 只保存在 HttpOnly Cookie。
- 空状态说明下一步操作；接口失败提供重试，不显示伪造金额或示例记录。
- 桌面和窄屏均可操作，键盘焦点可见，并尊重 `prefers-reduced-motion`。
- TypeScript 检查、生产构建和关键 BFF 接口测试通过。

## 7. Web 中英文支持

Web 已建立独立于手机端业务数据的界面语言层：

- 使用 `kai.locale` Cookie 保存 `zh-CN` 或 `en`，服务端首屏会输出对应的 `<html lang>` 和界面文案。
- 语言切换与主题切换并列，桌面端和移动端均可操作；刷新页面后保持用户选择。
- 公共导航、首页、市场、登录注册、页脚、账户首页和三类工作台导航使用结构化翻译字典。
- 保留的旧 Web 页面通过兼容翻译字典逐步覆盖，旧 API、页面和中文原文均不删除。
- 商家名称、社区帖子等用户生成内容保持原文，不进行机器翻译；后端业务错误在尚无错误码映射时也保持服务端原文。
- 自动化测试分别使用 `kai.locale=en` 与 `kai.locale=zh-CN` 验证服务端首屏语言和核心文案。
