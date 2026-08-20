# 三端统一后端与移动构建报告

日期：2026-08-21

## 结论

电脑/手机浏览器使用 Next.js，iOS/Android 使用同一份 uni-app UI；三端的业务请求都进入同一个 FastAPI `services/api` 和正式前缀 `/api/v1`。系统没有保留旧 WOD 后端，也没有 `/api/mobile/v1` 兼容桥。

```text
Next.js Web ─────────────┐
uni-app iOS ─────────────┼── FastAPI /api/v1 ── PostgreSQL（生产）
uni-app Android ─────────┘                    └─ SQLite（仅本地测试）
```

“后端完全相同”在源码层的验收依据是：`packages/api-contracts/check-mobile-api.mjs` 扫描 Mobile API 层和页面的所有请求，并与 FastAPI OpenAPI 路由匹配；同时禁止页面绕过统一请求层直接联网。本轮结果为 118 个可执行请求全部属于正式契约，缺失路由和旁路请求均为 0。

账号入口也已统一：Web、iOS 和 Android 均允许使用邮箱或手机号配合密码注册、登录，同一个密码账号可跨端复用。浏览器继续使用 Cookie + CSRF，App 继续使用限定为 `app` 通道的 Bearer Token，二者不能互相重放。Kai 统一认证已实现授权码 + PKCE、状态一次性消费、已验证邮箱/手机号自动绑定和 App 一次性票据兑换；自动测试已验证同一 Kai 身份先在 Web 注册后可在 App 登录。真实 Kai 登录仍需部署方提供客户端 ID、密钥和回调地址。

## 实际运行验证

测试账号：

```text
手机号：13800000000
密码：Kai-Test-2026!
```

测试账号仅由本地开发脚本创建，生产环境会拒绝运行该脚本。

iPhone 17 Pro / iOS 26.5 模拟器已通过 HBuilderX 标准调试基座打开 App，并成功登录为“KAI 测试用户”。运行中的 `app-service.js` 已核对为 `http://192.168.31.5:8100/api/v1`，不再包含旧的 `api.example.com`。

同一个 Bearer Token 对下列统一接口的 HTTP 烟测均返回 200：

- `/api/v1/auth/token/me`
- `/api/v1/notifications/preferences`
- `/api/v1/account/wallet`
- `/api/v1/account/wallet/ledger`
- `/api/v1/public/products`
- `/api/v1/public/market/summary`
- `/api/v1/feed/recommended`
- `/api/v1/feed/latest`
- `/api/v1/favorites`

社区文章和视频共用 `content_favorites` 表。测试账号已在 iOS 模拟器完成“关注 → 进入关注列表 → 取消后移除”的真实交互验证。

Mobile 与 Web 的“算力市场”直接读取同一个 `/api/v1/public/products`，不再混入外部 GPU 行情排行；搜索、筛选和价格排序只作用于这批服务器资源。Mobile 右上角“行情曲线”与 Web“算力行情”直接读取同一个 `/api/v1/public/market/summary`，当前实测返回 27 个 GPU 型号，每个型号最多 14 个周历史点。iOS 模拟器已显示 GetDeploying 的 H100 14 点 K 线和价格线。

本地开发库另外使用 `scripts.seed_market_catalog` 生成了 120 台显式标注为“演示”的服务器，覆盖同一批 27 个 GPU 型号、8 个演示商家和 10 个地区，价格围绕行情中位价生成。公开接口实测 120/120 台 Agent 在线且 120/120 条商品均返回 `image_url`。Mobile 市场已改为双列商品卡片，型号名称带 Nvidia/AMD 等厂商前缀时也能命中正确图片；这些记录只用于本地界面和业务流程测试，不代表真实库存或真实报价。

## 构建结果

| 产物 | 本地路径 | 当前大小 | 状态 |
|---|---|---:|---|
| uni-app iOS/Android 业务资源 | `apps/mobile/dist/build/app` | 约 10 MB | 已编译 |
| 移动 H5 QA 资源 | `apps/mobile/dist/build/h5` | 约 8.5 MB | 已编译 |
| iOS 调试运行 | HBuilderX 标准基座 + Xcode Simulator | — | 已登录验证 |
| Android 调试运行 | HBuilderX 标准基座 + Pixel 9 / Android 16 模拟器 | — | 已登录并完成五个主标签冒烟测试 |
| 正式 IPA | 需要 DCloud AppID、Bundle ID、Apple 证书/描述文件 | — | 未生成 |
| 正式 APK/AAB | 需要 DCloud AppID、Android 包名与 keystore | — | 未生成 |

`dist`、IPA、APK、AAB、证书和本机 `.env.local` 均被 Git 忽略，不应上传到源码仓库。

## 可重复验证命令

```bash
./tooling/check-all.sh
npm run check:contracts
npm run build:mobile:h5
npm run build:mobile:app
```

正式包的 HBuilderX 操作与环境变量见 `docs/DEVELOPMENT.md` 和 `docs/ANDROID_BUILD.md`。

## 当前边界

接口路径和身份体系已经统一，但第三方能力是否真正可用取决于生产配置。Kai、支付、短信、邮件、对象存储、推送、Apple/Android 签名没有账号或密钥时必须明确不可用，不能用前端模拟成功。移动 UI 仍保留原设计和部分“卡时”术语；正式运营前应确认其与后端币种、账本和退款规则的最终产品定义。
