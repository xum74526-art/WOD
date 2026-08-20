# KAI Mobile

uni-app + Vue 3 + TypeScript 前端，可构建 H5、Android/iOS App 和微信小程序。

## 开发

```powershell
Copy-Item .env.example .env.local
npm ci
npm run dev:h5
```

环境变量：

- `KAI_H5_API_TARGET`：H5 开发代理目标，例如 `http://127.0.0.1:8100`。
- `VITE_KAI_API_BASE`：原生 App 使用的完整 HTTPS API，例如 `https://api.example.com/api/v1`。

浏览器页面统一请求 `/api/v1`；原生 App 在构建时写入 `VITE_KAI_API_BASE`。前端目录中禁止保存任何第三方私钥或服务端 Token。

## 验证

```powershell
npm run type-check
npm test
npm run test:i18n
npm run check:ios
npm run build:h5
npm run build:app
```

## App 配置

交付版 `src/manifest.json` 已清空 DCloud AppID，并使用示例包名 `com.example.kai`。云打包前必须改为接收方自己的：

1. DCloud AppID
2. Android applicationId/包名
3. 版本号与版本代码
4. Android 签名证书
5. 正式 HTTPS API 地址

详见 `../../docs/BUILD_GUIDE.md` 和 `../../docs/ANDROID_BUILD.md`。

## 主要目录

- `src/api`：API 契约
- `src/pages`：业务页面
- `src/components`：可复用组件
- `src/store`：账户、语言、主题与业务状态
- `src/utils`：格式化、行情策略、安全解析
- `src/static`：随 App 打包的静态资源
- `tests`：Node 原生测试
- `scripts/check-i18n.mjs`：中英文键与字面量审计

正式发布前请确认 `src/static/gpu` 中的品牌图片拥有合法使用权。

## iOS

- `VITE_KAI_IOS_DISTRIBUTION=app-store`：公开伴侣版，隐藏外部充值和直接购买入口。
- `VITE_KAI_IOS_DISTRIBUTION=enterprise`：经授权的企业/内部完整版本。
- `src/nativeResources/ios/PrivacyInfo.xcprivacy`：项目隐私清单。
- `src/static/logo/ios-appstore-1024.png`：1024×1024、无透明通道的 App Store 主图标。

完整 iOS/Android 编译与发布步骤见 `../../docs/BUILD_GUIDE.md`。
