# KAI Android

这是 KAI 的 Android 客户端源码，正式 applicationId 为 `com.kai.wod`。

## 功能边界

- KAI Pricing 实时行情；
- KAI 商品按小时购买；
- 充值、充值订单查询、业务订单查询；
- 余额、资产和必要账户资料；
- 登录后显式绑定 Kai 统一身份；
- 管理信息只读，不在 Android 端执行财务、审核或系统配置写操作。

所有数据均来自 `services/api`，Android 不包含数据库和支付商户密钥。

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
- 正式签名由项目所有者保管，不能使用旧 WOD 测试包签名缓存。

旧项目中的 `WOD-Android-Package` 是编译产物，不属于本目录源码。
