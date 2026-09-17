# Mobile 客户端一致性

`apps/android` 和 `apps/ios` 是同一产品的两个原生容器，业务状态和 HTTP 契约都来自
`services/api`。共享页面优先保持同一实现，平台差异只放在清单、签名、更新渠道和原生权限层。

## 共享能力

| 范围 | Android 与 iOS 的共同要求 |
|---|---|
| 登录 | 手机号、注册、密码找回、恢复邮箱和安全的登录后返回路径一致 |
| 市场 | 行情、热度与价格排序、商品详情、需求预填和询价流程一致 |
| 需求 | 买家查看自己的需求；商家可分别进入需求市场和自己的采购需求 |
| 交易 | 购买、充值、提现、订单和资产严格遵守后端能力开关 |
| 返佣 | 个人购买返佣与商家销售返佣独立展示，口径和月上限说明一致 |
| 社区 | 图文、用户视频、聚合视频、评论、点赞和关注流程一致 |
| 视频 | 聚合视频使用受信任的元数据请求和原生播放器，支持进度、全屏及 0.5/0.8/1/1.25/1.5/2 倍速 |

`npm run check:client-experience` 会检查关键能力证据和要求完全镜像的 Mobile 文件。新增共享
功能时应同时更新两端及该检查，避免只在一个平台出现入口或修复。

## 平台差异

- Android 包名为 `com.kai.ztwstarmap`，分发产物是 APK/AAB；iOS Bundle ID 为
  `com.kai.ztwstarmap`，分发产物是归档或 IPA。旧 Android 包 `com.kai.wod`
  不能覆盖安装新包，只使用独立的历史更新元数据。
- Android 更新可由受控 APK 渠道处理；iOS 正式更新必须遵守 Apple 分发渠道。
- iOS 的相册、相机和麦克风用途说明位于 `apps/ios/src/manifest.json`；Android 权限由
  构建清单和所用模块生成，并明确排除安装包和电话状态权限。
- 模拟器 `.app`、APK/AAB、IPA、签名资料和 `dist/` 都是构建产物，不进入 Git。

## 本地验证

```bash
npm ci --prefix apps/android
npm ci --prefix apps/ios
npm test --prefix apps/android
npm test --prefix apps/ios
npm run type-check --prefix apps/android
npm run type-check --prefix apps/ios
npm run check:client-experience
npm run build:android:app
npm run build:ios:app
```

`build:*:app` 生成 uni-app 业务资源。安装到 Android 或 iOS 模拟器时，还需要匹配平台的原生
基座或工程；该本地安装步骤不会产生应提交到仓库的源码文件。
