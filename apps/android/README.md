# 算力星图 Android

这是“算力星图”的 Android 客户端源码，正式 applicationId 为 `com.kai.ztwstarmap`。

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

原生 `androidPrivacy.json` 先阻止 DCloud 运行组件在用户同意前加载，随后
`pages/privacy-consent/index` 完成当前法律版本和服务地区选择。未完成必选同意时，
`api/request.ts` 会拒绝请求、上传、下载和受信第三方元数据访问；更新检查、能力刷新、通知轮询
与 KAI 回跳处理也不会启动。所有地区均需通过独立勾选明确确认在中国香港存储、处理及必要
传输个人信息；同意版本、时间、地区和平台只留存在本机。

## 打包要求

- DCloud AppID 沿用 `__UNI__47CF9D3`，更换 applicationId 不得新建或替换现有 AppID；
- Android 包名固定为 `com.kai.ztwstarmap`；
- KAI OAuth 回跳 scheme 为 `kai://auth`；
- keystore、别名、密码、APK/AAB、`.env.local` 和 `dist/` 不得提交；
- 正式签名由项目所有者保管，不能使用旧版测试包签名缓存。

applicationId 变更后，发布负责人还必须在 DCloud 云打包和 KAI OAuth/开放平台配置中登记
`com.kai.ztwstarmap` 以及最终正式签名对应的公钥/证书 MD5。客户端回跳仍为
`kai://auth`；只有在服务端白名单、Android 和 iOS 同一版本一起迁移时才允许更换 scheme。

旧项目中的 `WOD-Android-Package` 是编译产物，不属于本目录源码。历史域名、数据键和
业务记录中的 `wod` 标识用于兼容线上数据，不等同于当前用户可见应用名称。
