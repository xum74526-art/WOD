# 外部 Provider 接入说明

支付和私有对象存储通过 `app.providers` 与业务层隔离。支付已经提供 Ping++ 适配器；KYC 第一版使用平台人工审核与独立字段加密，对象存储仍为 Disabled Provider。生产环境不能只把旧的 `*_PROVIDER_ENABLED` 改成 `true`，还必须配置明确的 Provider 名称与完整凭据。

## Ping++ 支付

当前使用 Ping++ Charge/Refund API。Test Key 会生成 `livemode=false` 的 Charge 并进入官方模拟支付页；Live Key 用于正式渠道。支付通知按原始请求体使用 Ping++ 公钥做 RSA-SHA256 验签，后端再主动查询 Charge 确认状态，随后以事件 ID 幂等入账；服务器租赁只有在这一步完成后才会向 Agent 下发买家 SSH 公钥。退款由平台调用 Refund API，只有验签后的 `refund.succeeded` 才会完成账本冲销。

必须配置：

- `PAYMENT_PROVIDER_ENABLED=true`
- `PAYMENT_PROVIDER=pingxx`
- `PINGXX_API_KEY`：`sk_test_` 或 `sk_live_` 开头的 API Key
- `PINGXX_APP_ID`：Ping++ 应用 ID
- `PINGXX_PUBLIC_KEY`：Ping++ 公钥，用于 Webhook 验签
- `PINGXX_MERCHANT_PRIVATE_KEY`：商户 RSA 私钥；生产请求签名必填
- `PINGXX_LIVE_MODE`：模拟测试为 `false`，正式环境为 `true`
- `PUBLIC_API_BASE_URL`：公网 HTTPS API 地址，不能是 localhost；回调地址固定为 `/api/v1/payments/webhooks/pingxx`
- `FRONTEND_BASE_URL`：支付完成后返回的站点地址

`PINGXX_DEFAULT_CHANNEL` 默认是 `alipay_pc_direct`，也支持 `alipay_wap`、`wx_wap`、`upacp_pc` 和 `upacp_wap`。业务金额按人民币元保存，调用 Ping++ 时转换为整数分。密钥中的换行可以在环境变量里写成 `\n`。

本机 SQLite、localhost 前后端且支付 Provider 关闭时，服务器租赁继续使用 `local_placeholder` 测试支付；非本机环境不会回退到测试支付。

## 接入点

- 支付：实现 `PaymentProvider.create_checkout()`、`query_payment()`、`create_refund()` 和 `verify_notification()`。
- KYC：当前人工审核无需外部 Provider；若未来改用第三方，再实现 `KycProvider.start_verification()` 与签名回调，并保留现有业务状态接口。
- 存储：实现 `StorageProvider.create_upload()` 和 `complete_upload()`。
- 在 `registry.py` 中按配置名称构造适配器，例如 `aliyun_oss`、`alipay`。

适配器凭据只能来自后端环境或 Secret Manager，不得进入 `NEXT_PUBLIC_*`、数据库响应、前端 bundle 或日志。

## 状态与回调

当前数据库已经包含：

- `payment_intents`
- `ledger_accounts` / `ledger_journals` / `ledger_entries`
- `kyc_applications`
- `stored_objects` / `upload_sessions`

真实适配器接入时还必须增加对应的 Webhook 路由。Webhook 上线前必须同时具备：

1. 原始请求体签名校验和时间窗校验。
2. 服务商事件 ID 幂等约束。
3. 状态机校验，不能由客户端直接把支付或 KYC 改成成功。
4. 回调审计记录、失败重试和死信处理。
5. 支付入账必须调用 `post_balanced_journal()`，借贷不平衡时整体拒绝。

## 私有文件

上传地址必须短期有效并限制对象键、大小、Content-Type 和写入方法。对象默认私有；下载必须使用短期签名地址并重新执行当前用户权限检查。KYC、合同和交付材料应使用不同前缀和生命周期规则，并启用恶意文件扫描/隔离。

## 禁用态保证

Disabled Provider 的发起操作始终失败，且失败发生在创建业务记录之前。因此未配置环境不会产生伪造支付单、KYC 申请或文件元数据。
