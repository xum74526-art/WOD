# KAI Unified 全量重构规划

状态：已确认执行
基线日期：2026-08-20

## 1. 已确认决策

1. 当前没有正式用户，不保留旧 App、旧接口或旧数据库兼容。
2. KAI FastAPI 业务模型是新系统的后端基线。
3. 全系统只提供一套正式 API：`/api/v1`。
4. 电脑浏览器和手机浏览器使用同一套 Next.js 响应式网站。
5. iOS 和 Android 使用同一套 uni-app 代码。
6. 不开发 SwiftUI、Kotlin 原生 UI，不将 uni-app H5 作为正式网站。
7. 不保留 `/api/mobile/v1`，不实现旧 WOD `{code,msg,data}` 兼容协议。
8. 不复制旧 WOD 后端；旧项目只作为功能与 UI 参考。
9. 后端采用模块化单体，不在当前阶段拆微服务。
10. PostgreSQL 是唯一生产数据库；SQLite 仅允许用于快速单元测试。

## 2. 产品形态

| 使用端 | 技术 | UI 责任 |
|---|---|---|
| 电脑浏览器 | Next.js | 桌面网站、管理后台、复杂表格 |
| 手机浏览器 | Next.js | 响应式手机网页、公开分享链接 |
| iOS App | uni-app | 移动 App UI |
| Android App | uni-app | 与 iOS 共用移动 App UI |
| 统一后端 | FastAPI | 账户、交易、资产、支付和平台能力 |

网页端与 App 端不追求相同布局，但必须共享业务术语、状态枚举、金额含义、权限规则和 API 契约。

## 3. 目标架构

```text
Next.js Web ───────────┐
                      │
uni-app iOS ──────────┼── FastAPI /api/v1 ── PostgreSQL
                      │          │
uni-app Android ──────┘          ├── Redis
                                 ├── Object Storage
KAI Agent ───────────────────────┤
                                 └── Background Worker
```

后端先保持一个可独立部署的 FastAPI 应用。行情同步、邮件、通知和结算任务在代码上独立，通过 worker 运行，但共享领域模型和部署版本。

## 4. 新仓库目录

```text
KAI-Unified/
├─ apps/
│  ├─ web/                       Next.js
│  └─ mobile/                    uni-app（iOS + Android）
├─ services/
│  └─ api/                       FastAPI 模块化单体
├─ packages/
│  └─ api-contracts/             OpenAPI 快照、生成 SDK 和契约检查
├─ agent/                        Linux / Windows KAI Agent
├─ infra/                        Docker、Caddy、部署配置
├─ tooling/                      仓库级脚本
├─ docs/
├─ .github/workflows/
├─ .gitignore
└─ README.md
```

不复制：

- 旧 WOD `backend/`
- `node_modules/`、`.next/`、`dist/`、`unpackage/`
- Python `.venv/`
- `.env`、数据库、上传文件、证书和密钥
- `/api/mobile/v1` 兼容实验

## 5. 后端模块边界

```text
services/api/app/
├─ core/                         配置、安全、数据库、可观测性
├─ modules/
│  ├─ identity/                 用户、登录、设备会话、权限
│  ├─ catalog/                  商品、资源、库存
│  ├─ market/                   行情、快照、K 线
│  ├─ procurement/              求购、报价
│  ├─ orders/                   订单与状态机
│  ├─ rentals/                  SSH 公钥、租约、Agent 指令
│  ├─ finance/                  钱包、双重记账、支付、退款
│  ├─ suppliers/                入驻、设备、结算、提现
│  ├─ compliance/               KYC、私有文件、审核
│  ├─ community/                资讯、社区、评论与审核
│  ├─ notifications/            站内信、邮件和推送事件
│  ├─ support/                  客服与工单
│  └─ admin/                    平台管理接口
├─ api.py                       `/api/v1` 路由聚合
└─ main.py
```

模块之间通过服务接口调用。路由不得直接修改其他模块的数据表。支付、库存、订单和租约的状态变更必须由领域服务执行。

## 6. API 标准

### 6.1 正常响应

```json
{
  "data": {},
  "meta": {}
}
```

### 6.2 错误响应

```json
{
  "error": {
    "code": "ORDER_NOT_FOUND",
    "message": "订单不存在"
  }
}
```

### 6.3 通用约束

- 路径前缀统一为 `/api/v1`。
- 时间统一传 ISO 8601 UTC，前端负责本地化显示。
- 金额不能使用浮点数作为写入参数；API 使用十进制字符串和明确货币。
- 分页统一 `page`、`page_size`，响应分页信息放入 `meta`。
- 所有写操作支持明确的幂等键或版本号。
- 状态枚举只允许向后兼容地扩展。
- OpenAPI 是 Web 和 App 的共同契约来源。

## 7. 鉴权标准

### Web

- HttpOnly Session Cookie
- 所有写操作检查 CSRF
- Cookie 为 `Secure`、`SameSite=Lax`

### uni-app

- 随机不透明 Bearer Token
- iOS 使用安全存储，Android 使用系统安全存储
- Token 服务端只保存哈希
- 记录设备名称、创建时间、最近活动、到期和撤销状态

两种会话属于同一用户和同一 `sessions` 模型，但必须有 `channel` 区分，不能跨通道重放。

### 账户

- 支持邮箱 + 密码。
- 支持手机号 + 密码，但手机号未完成短信验证时明确标记 `phone_verified=false`。
- 生产开放手机号注册前必须接入短信验证与限流。
- 管理员、个人用户、供应商采用 RBAC，不用前端隐藏代替后端权限检查。

## 8. 数据与业务标准

### 唯一事实来源

- 商品库存：Catalog/Inventory
- 订单状态：Orders
- 使用权资产：Rental Lease，不再维护第二张模拟 Asset 表
- 钱包余额：Ledger 聚合，不直接保存可随意修改的余额
- 支付结果：验签 Webhook + Provider 主动查询
- 服务器状态：KAI Agent 签名上报
- 行情：保存来源、币种、采集时间和质量状态

### 明确禁止

- Web 和 App 使用不同数据库。
- 为了兼容旧 UI 复制订单或钱包逻辑。
- 将美元行情标成 CNY 或“卡时”。
- 伪造收益、库存、支付成功、实名成功或服务器在线状态。
- 长期双写或长期维护旧后端。

## 9. 前端标准

### Next.js

- 同一路由支持桌面和手机响应式布局。
- 公开商品、行情和资讯保留服务端 Metadata。
- 账户和后台页面保留现有 KAI 信息架构，逐步抽取响应式组件。

### uni-app

- 保留 WOD 现有移动视觉方向和底部导航。
- 删除对旧 WOD API 字段的直接依赖。
- API 层只消费 `/api/v1`，页面只消费 ViewModel。
- iOS/Android 差异使用条件编译，公共业务代码不得复制。
- uni-app H5 只用于调试和 QA，不作为正式站点部署。

## 10. 重构阶段

### R0：新仓库与可重复构建

- 建立目录、Git 忽略、根 README 和统一命令。
- 导入干净 KAI Web、KAI API、Agent、Infra 与 WOD Mobile。
- 所有子项目可以在新路径安装、检查和构建。

验收：新仓库不依赖两个旧目录的相对路径；无密钥和构建产物进入 Git。

### R1：统一契约与身份

- 固定 `/api/v1` 响应、错误、分页和金额标准。
- 完成 Web Cookie 与 App Bearer 双通道会话。
- 统一邮箱、手机号、角色、设备和退出登录。
- 建立 OpenAPI 快照与契约测试。

验收：同一账户可分别从 Web 和 App 登录；会话不能跨通道使用。

### R2：目录与领域模块化

- 将现有 KAI 后端按模块边界迁移，保持 API 行为。
- 建立模块依赖检查与数据库迁移检查。
- 将 scheduler 拆为 worker 启动入口。

验收：Web 全部回归测试通过；API OpenAPI 差异经过审核。

### R3：公开浏览闭环

- Web 和 App 统一接商品、商品详情、行情和资讯。
- 统一行情币种与来源展示。
- Next.js 完成公开页面手机响应式。

验收：同一商品和行情在 Web/App 字段含义一致。

### R4：用户交易闭环

- 求购、报价、订单、库存预留。
- SSH 公钥、服务器租约、续租和退款。
- App 将 Lease 展示为“资产”。

验收：跨端状态一致；重复请求不会重复占库存或生成订单。

### R5：资金闭环

- 钱包、双重记账、支付、退款、结算和提现。
- 所有金额与状态完成对账测试。

验收：任意交易的借贷平衡；支付回调幂等；客户端不能直接改变资金状态。

### R6：供应商、合规和运营

- 供应商入驻、资源、Agent、KYC、私有文件。
- 通知、社区、客服和后台审核。
- 重新评估优惠券与邀请返佣；没有真实业务规则则不迁入。

### R7：发布

- Web 生产部署。
- iOS 签名与 TestFlight。
- Android AAB 内测。
- 安全审计、备份恢复演练和监控告警。

## 11. 测试门槛

- API：单元、领域状态机、权限、契约、迁移和集成测试。
- Web：TypeScript、生产构建、Playwright、桌面/手机截图回归。
- Mobile：TypeScript、单元测试、App 构建、iOS/Android 真机冒烟。
- Agent：Linux/Windows 交叉编译、签名、防重放与离线到期测试。
- Infra：Docker Compose 配置、健康检查、迁移和备份恢复验证。
- 安全：密钥扫描、依赖检查、越权、CSRF、Token 重放、上传隔离。

任何阶段只有在上一个阶段的测试门槛通过后才进入下一阶段。

## 12. 首轮执行清单

- [x] 创建新目录结构。
- [x] 从 KAI Git `HEAD` 导入干净源码，不带本地兼容实验。
- [x] 从 WOD 只导入 `frontend` 移动源码。
- [x] 新建仓库级 `.gitignore`。
- [x] 新建根 `README.md` 和统一检查脚本。
- [x] 初始化本地 Git `main` 分支，不设置远端、不推送。
- [x] 验证 Web、Mobile、API、Agent 和 Compose。
- [x] 完成 R1 身份双通道与 Mobile `/api/v1` 契约统一。

后续生产发布门槛和本轮真实验证见 `docs/IMPLEMENTATION_STATUS.md` 与 `docs/BACKEND_UNIFICATION_REPORT.md`。
