# Web 以手机端后端为唯一数据源的重构方案

状态：本地第一阶段已落地
修订日期：2026-08-21

## 已确认决策

1. `services/mobile-api`（WOD FastAPI）是唯一业务后端。
2. `services/mobile-api/wod.db` 是当前本地唯一数据库。
3. `apps/mobile` 保持 WOD 原生 `/api` 契约，不再适配旧 KAI Web 后端。
4. `apps/web` 不建立数据库，也不直接连接数据库。
5. Web 使用 Next.js BFF 保存 HttpOnly 登录 Cookie，并转发到 WOD。
6. `services/api` 不参与当前运行；未迁移模块不得读取它的数据或返回模拟数据。

## 请求链路

```text
Web Client
  │ same-origin /api/v1
  ▼
Next.js Route Handler (BFF, no database)
  │ Authorization: Bearer <HttpOnly cookie token>
  ▼
WOD FastAPI /api
  ▼
wod.db
```

新 Web 页面优先使用 `/api/v1/mobile/*`，其余 `/api/v1` 路由是旧 Web UI 到 WOD 字段的迁移适配层。适配层只允许转换、聚合和隐藏 Token，不保存业务状态。

## 当前已接通

- 图形验证码、手机号注册/登录、当前用户、退出登录；
- 商品列表、商品详情、行情汇总；
- 手机端钱包与真实流水；
- 买家订单创建、列表、详情、取消、确认交付；
- 商家申请、商品、库存、上下架、订单 SSH 交付；
- 地址与通知；
- 账户与商家汇总。

## 明确停用

手机端没有数据模型的旧 Web 功能返回 `503 mobile_source_unavailable`：

- 团队与邀请；
- API Key；
- KAI Agent 与自动公钥租约；
- 旧 Web 支付意图、争议、私有文件等独立模型。

不能为了让旧页面“看起来可用”而从 `services/api` 取数、复制数据或伪造成功。

## 后续阶段

1. 将社区、求购、资产、商家收益与设置页面改为 `/api/v1/mobile/*` 原生字段。
2. 删除或归档已经没有入口的旧 Web 组件和 `services/api`。
3. 为 BFF 适配器补充自动化契约测试和浏览器测试。
4. 云端部署时将 WOD 数据库迁移到受支持的持久化数据库，并设置 `MOBILE_API_ORIGIN` 为内部 HTTPS 地址。
5. 完成备份恢复、支付/敏感能力密钥、单 worker 后台任务与上传目录持久化验证。

## 验收条件

- 停止 `services/api` 后，Web 核心页面仍可运行；
- Web 注册用户、地址、订单等操作能在手机端后端立即读到；
- Web 进程不创建或连接业务数据库；
- 同一账号从 App 与 Web 看到相同的余额、库存和订单状态；
- 未迁移功能明确不可用，不回退到旧数据库。
