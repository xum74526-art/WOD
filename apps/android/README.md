# KAI Android

这是 KAI 的 Android 客户端源码，正式 applicationId 为 `com.kai.wod`。

## 共享客户端功能

- 手机号登录、注册、找回密码和恢复邮箱；
- 算力行情、商品详情、需求提交、需求市场和商家报价；
- 后端开启直接交易后提供购买、充值、订单、钱包和资产功能；
- 算力社区浏览、评论，以及用户图片或视频发布；
- 个人与商家模式、购买返佣、销售返佣和商家工作台。

Android 和 iOS 使用同一 OpenAPI 契约。能力是否显示以服务端开关为准，客户端不自行
模拟订单、支付、提现或返佣状态。所有数据均来自 `services/api`；Android 不包含数据库、
支付商户密钥、财务审核或人工打款能力。

## 开发与验证

```powershell
Copy-Item .env.example .env.local
npm ci
npm run type-check
npm test
npm run test:i18n
npm run build:android
```

原生正式 API 由 `VITE_KAI_APP_API_BASE` 设置，默认示例为
`https://wod.kai.com/api`。H5 仅用于本地界面预览，默认端口为 `9001`。

## 打包要求

- DCloud AppID 在发布环境配置，不写入仓库；
- Android 包名固定为 `com.kai.wod`；
- KAI OAuth 回跳 scheme 为 `kai://auth`；
- keystore、别名、密码、APK/AAB、`.env.local` 和 `dist/` 不得提交；
- 正式签名由项目所有者保管，不能使用旧版测试包签名缓存。

旧项目中的 `WOD-Android-Package` 是编译产物，不属于本目录源码。
