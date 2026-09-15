# KAI iOS

这是 KAI 的 iOS 客户端源码，正式 Bundle ID 为 `com.kai.wod`。

## 共享客户端功能

- 手机号登录、注册、找回密码和恢复邮箱；
- 算力行情、商品详情、需求提交、需求市场和商家报价；
- 后端开启直接交易后提供购买、充值、订单、钱包和资产功能；
- 算力社区浏览、评论，以及用户图片或视频发布；
- 个人与商家模式、购买返佣、销售返佣和商家工作台。

Android 和 iOS 使用同一 OpenAPI 契约。能力是否显示以服务端开关为准，客户端不自行
模拟订单、支付、提现或返佣状态。所有数据均来自 `services/api`；iOS 不包含数据库、
支付商户密钥、财务审核或人工打款能力。

## 开发与验证

```powershell
Copy-Item .env.example .env.local
npm ci
npm run type-check
npm test
npm run test:i18n
npm run build:ios
```

原生正式 API 由 `VITE_KAI_APP_API_BASE` 设置，默认示例为
`https://wod.kai.com/api`。H5 只用于本地界面预览，默认端口为 `9000`。

选择头像、身份认证图片或社区媒体时，系统才会请求相册、相机或麦克风权限；用途说明维护在
`src/manifest.json` 的 `privacyDescription` 中。

## 打包要求

- DCloud AppID 在发布环境配置，不写入仓库；
- iOS Bundle ID 固定为 `com.kai.wod`；
- KAI OAuth 回跳 scheme 为 `kai://auth`；
- Apple 证书、Provisioning Profile、密码、安装包、`.env.local` 和 `dist/` 不得提交。
