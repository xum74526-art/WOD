# 三端统一实现交付说明

本文记录当前本地 monorepo 的实际实现边界。它用于代码评审和后续发布决策，不代表已经部署、
迁移生产数据库或完成应用商店签名。

## 最终目录

```text
KAI-main/
├── apps/
│   ├── web/          # Next.js Web、BFF、完整业务与管理界面
│   ├── ios/          # uni-app iOS 客户端
│   └── android/      # uni-app Android 客户端，包名 com.kai.wod
├── services/
│   └── api/          # 唯一 FastAPI 业务后端和数据库所有者
├── packages/
│   └── api-contracts/# FastAPI OpenAPI 快照及客户端契约检查
├── infra/            # 部署配置示例，不保存生产密钥
└── docs/             # 架构、开发、发布和本交付说明
```

旧目录 `WOD-Android-Package` 中的 APK、云证书缓存、keystore、`unpackage` 和编译后文件没有
迁入本仓库。Android 是从可维护源码整理出的新客户端，不以旧 APK 反编译产物作为源码。

## 一套后端、一份业务数据

三端不会各自保存一份业务数据库。它们共同调用 `services/api`，账号、余额、资产、订单、充值、
实名、银行卡和提现均只保存一份：

```text
Web 浏览器 -> Next.js 同源 BFF -> FastAPI -> 唯一数据库
iOS App -----------------------> FastAPI -> 唯一数据库
Android App -------------------> FastAPI -> 唯一数据库
```

因此，同一用户从任一端登录，都能看到同一余额、资产和订单。所谓“区分三端数据”是给业务记录
增加不可变来源审计字段，不是复制三份记录或拆三套数据库。

## 平台来源审计

登录或注册时，客户端声明已登记的 `client_id`：

| 客户端 | `client_id` | 服务端来源 |
|---|---|---|
| Web | `web` | `web` |
| iOS | `ios` | `ios` |
| Android | `android` | `android` |
| 管理操作 | `admin` | `admin` |
| 无可靠历史来源 | - | `legacy` |

FastAPI 登录后创建服务端 `AuthSession`，JWT 只引用该会话。订单、充值、实名、银行卡、提现、
社区、邀请等写入记录从服务端会话固化 `created_platform`；适用记录同时保存
`last_modified_platform`。客户端自行伪造 `X-Platform` 等请求头不能覆盖会话来源。

管理员可按 `web / ios / android / admin / legacy` 查看总览、用户、订单、充值以及财务列表。
平台来源只用于统计和审计，不能替代管理员角色或财务白名单。若将来需要证明是真实设备或官方
安装包，仍需独立接入 Apple App Attest / DeviceCheck 和 Google Play Integrity。

## Kai 身份绑定

Kai 身份已改为“先登录本地账号，再显式绑定”，避免同一人被自动创建成第二个用户：

1. 用户使用手机号登录或注册本地账号，客户端发送对应的 `client_id`。
2. 用户在账号设置中选择绑定 Kai 身份。
3. 已登录客户端请求 `POST /api/auth/kai/bind/start`。
4. FastAPI 创建带 state、PKCE、nonce 和发起会话的授权流程。
5. 系统浏览器完成 Kai 授权并回跳 App 或 Web。
6. 回调只发放短时、一次性的 `kai_bind_ticket`。
7. 原登录会话调用 `POST /api/auth/kai/bind/exchange` 完成绑定。
8. ticket 只能由最初发起绑定的同一用户兑换；身份已被其他账号绑定时拒绝冲突。

未绑定的 Kai 身份直接尝试登录时，后端返回 `identity_not_bound`，不会自动创建 `kai_*` 用户。
绑定成功也不会替换当前登录 Token。

## 行情与小时购买

- `KAI Pricing` 是唯一实时行情源。
- Vast、AutoDL 不再参与实时同步、当前商品目录、排行或客户端主动行情请求。
- 旧来源记录只作为历史审计保留，不冒充 KAI 数据。
- 新 KAI 商品只允许整数小时购买，范围为 1–720 小时。
- 新购和续费都要求 `client_request_id`，服务端通过持久续费事件保证重试不重复扣款。
- 旧日周期订单只保持历史读取兼容，客户端不会给新 KAI 订单发送 `cycle_days`。
- KAI 报价是 CNY/GPU-hour；报价样本不冒充实时库存。

## 支付

三端新充值统一使用服务端 `/api/payments/qixiang/*`：

- 客户端可以创建、查看、查询和在后端允许时取消充值订单；
- Web 收银台通过同源 BFF 转发，不把商户密钥暴露给浏览器；
- 入账只相信服务端验签回调或主动查单结果，不相信客户端“跳转成功”；
- 商户 PID、KEY 和回调配置只允许存在于云端受保护环境，不进入仓库或安装包；
- 历史支付路由只作为已安装旧客户端和旧订单兼容边界保留。

本次没有调用真实商户、创建真实订单或执行真实付款。

## 各端能力边界

| 能力 | Web | iOS | Android |
|---|---:|---:|---:|
| 行情、机型榜、区域价差 | 完整 | 保留 | 保留 |
| KAI 商品小时购买 | 完整 | 保留 | 保留 |
| 充值、充值记录、查单、允许时取消 | 完整 | 保留 | 保留 |
| 订单查询、续费、资产查看 | 完整 | 保留 | 保留 |
| Kai 身份显式绑定 | 完整 | 保留 | 保留 |
| 社区和用户自助业务 | 完整 | 保留必要能力 | 保留必要能力 |
| 管理员来源审计 | 完整 | 不提供写管理 | 不提供写管理 |
| 财务审核、人工打款 | Web 且仍受财务白名单限制 | 移除 | 移除 |
| 商家资料编辑、商品发布、设备修改、SSH 交付 | Web 管理边界 | 只读或移除 | 只读或移除 |

iOS 和 Android 当前各有 225 个 `src` 文件，文件集合完全一致；只有
`src/manifest.json` 和 `src/utils/client-platform.ts` 是预期的平台差异，其余 223 个文件
内容一致。业务改动必须同步两端并
复跑各自测试。

## 验收门禁

本地最终验收（2026-08-22）结果：

| 范围 | 结果 |
|---|---|
| FastAPI | 262/262 单元测试通过；`compileall` 通过 |
| OpenAPI | 快照一致；212 个 Mobile API 调用契约通过；客户端边界检查通过 |
| Web | 11/11 测试、TypeScript、Next.js production build 通过 |
| iOS | 88/88 测试、TypeScript、i18n 审计、App build 通过 |
| Android | 88/88 测试、TypeScript、i18n 审计、App build 通过 |
| 依赖 | Python、Web、iOS、Android 已知依赖漏洞审计均为 0 |
| 静态安全 | 未带入真实 `.env`、数据库、APK/IPA/AAB、keystore、私钥或支付 KEY |
| 移动端一致性 | 两端各 225 个源码文件，仅两个预期平台文件不同 |

双端构建仍会输出 Node module-type 性能提示和 Sass legacy API/`@import` 弃用提示；它们不影响
当前构建结果，但后续升级 uni-app/Sass 工具链时应一并处理。

每次后端契约变化后：

```bash
npm run export:openapi
npm run check:contracts
```

完整合并前：

```bash
npm run check:all
npm run audit:deps
git diff --check
```

检查范围包括 FastAPI 全量测试与编译、OpenAPI 快照、Web 测试/类型检查/生产构建、iOS 与
Android 测试/类型检查/App 构建、客户端路由边界及依赖漏洞审计。

## 本次不包含的外部动作

以下仍需发布负责人另行完成，本次本地整理没有执行：

- 将代码提交到正式 Git 仓库并建立可回滚提交；当前收到的工作副本没有 `.git` 元数据；
- 把本地数据库迁移或合并到生产数据库；
- 修改、重启或部署 `wod.kai.com` 服务器；
- 写入生产 OAuth、Kai Auth 或齐象支付密钥；
- 执行真实支付；
- 生成、签名或上传 APK/IPA；
- 在 Apple/DCloud/Android 发布账户中登记正式标识、证书和回跳白名单。

生产迁移必须等同事代码冻结后，从同一个 Git 提交构建，先备份并在生产数据库副本上连续跑两次
迁移、核对账号与金额守恒，再进行原子切换和回滚演练。
