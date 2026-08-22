# KAI iOS

这是 KAI 的 iOS 客户端源码，正式 Bundle ID 为 `com.kai.wod`。

## 功能边界

- KAI Pricing 实时行情；
- KAI 商品按小时购买；
- 充值、充值订单查询和取消、业务订单查询；
- 余额、资产和必要账户资料；
- 登录后显式绑定 Kai 统一身份；
- 商家设备、订单、收益和资料仅供查看，管理操作统一在 Web 完成。

所有数据均来自 `services/api`。iOS 不包含数据库、支付商户密钥、财务审核或人工打款能力。

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

## 打包要求

- DCloud AppID 在发布环境配置，不写入仓库；
- iOS Bundle ID 固定为 `com.kai.wod`；
- KAI OAuth 回跳 scheme 为 `kai://auth`；
- Apple 证书、Provisioning Profile、密码、安装包、`.env.local` 和 `dist/` 不得提交。
