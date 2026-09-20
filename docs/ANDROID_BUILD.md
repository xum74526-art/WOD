# Android 开发、预览与打包

Android 客户端位于 `apps/android`，正式 applicationId 为 `com.kai.ztwstarmap`。它与 iOS 使用同一 OpenAPI 和业务状态，但拥有独立的 Android manifest、回跳和发布配置。旧 `com.kai.wod` 不能原位升级到新包，只保留独立历史更新通道。

## 本机已经安装的环境

- HBuilderX 5.24：`/Applications/HBuilderX.app`
- JDK 17：使用 HBuilderX 内置 Amazon Corretto
- Android SDK：`/Volumes/mydisk2t/Android/sdk`
- Android AVD：`/Volumes/mydisk2t/Android/avd`
- 模拟器：`KAI_Pixel_9_API_36`（Android 16、arm64）
- SDK 组件：Platform 36、Build Tools 35.0.0、Platform Tools、Android Emulator

大体积 SDK、系统镜像和模拟器数据均在 APFS 外接硬盘；使用前需先挂载 `mydisk2t`。

## 编译业务资源

在仓库根目录执行：

```bash
npm ci --prefix apps/android
npm run check:android
npm run test:android
npm run build:android:app
```

生成的 Android 业务资源位于 `apps/android/dist/build/app`。这不是独立 APK；它供 HBuilderX 调试基座或原生打包使用。

## 启动本机 Android 模拟器

```bash
export JAVA_HOME=/Applications/HBuilderX.app/Contents/HBuilderX/plugins/amazon-corretto
export ANDROID_SDK_ROOT=/Volumes/mydisk2t/Android/sdk
export ANDROID_HOME="$ANDROID_SDK_ROOT"
export ANDROID_AVD_HOME=/Volumes/mydisk2t/Android/avd
export ANDROID_USER_HOME=/Volumes/mydisk2t/Android/user
export PATH="$ANDROID_SDK_ROOT/platform-tools:$PATH"

"$ANDROID_SDK_ROOT/emulator/emulator" \
  -avd KAI_Pixel_9_API_36 \
  -no-snapshot -gpu host
```

等待 `adb shell getprop sys.boot_completed` 返回 `1` 后，在 HBuilderX 中导入 `apps/android`，选择“运行 → 运行到手机或模拟器 → Android”。也可以使用命令行：

```bash
/Applications/HBuilderX.app/Contents/MacOS/cli launch app-android \
  --project "$PWD/apps/android" \
  --deviceId emulator-5554 \
  --playground standard \
  --native-log true
```

标准调试基座的包名是 `io.dcloud.HBuilder`，其权限弹窗不代表最终 KAI 安装包的权限。正式包以 `src/manifest.json` 为准。

## API 地址

复制 `apps/android/.env.example` 为被 Git 忽略的 `.env.local`。原生包只接受以 `/api`
结尾的 HTTPS 地址：

```dotenv
VITE_KAI_APP_API_BASE=https://wod.kai.com/api
```

如需连接本地后端，应先提供受信任的 HTTPS 测试域名或隧道；不要把 `127.0.0.1` 或明文
HTTP 用作真机地址。

## 生成正式 APK 或 AAB

目前仓库刻意未保存发布身份材料，因此只能运行调试基座。正式打包前由项目所有者登录自己的 DCloud 账号，并提供和配置：

1. 沿用 DCloud AppID `__UNI__47CF9D3`；
2. 唯一且长期不变的 Android applicationId：`com.kai.ztwstarmap`；
3. DCloud 云打包与 KAI OAuth/开放平台均已登记该 applicationId 和最终正式签名的公钥/证书 MD5；
4. 原生回跳 scheme 仍为 `kai://auth`，并存在于后端精确白名单；
5. 自有 keystore、别名和密码；
6. 正式 HTTPS API；
7. 版本名与递增的 versionCode。

直接交易发布还必须使用独立的新版本号，在构建环境显式设置：

```dotenv
VITE_ENABLE_DIRECT_TRADE=true
```

仓库 `apps/android/.env.example` 继续保持 `false`，避免普通调试或审核构建意外出现资金入口。这个变量在编译时固化；只开服务器开关不会让已安装的旧 APK/AAB 获得充值、购买、银行卡或提现入口。服务器能力不可达时客户端仍按关闭处理。

七相支付返回使用独立 HTTPS 地址 `https://wod.kai.com/payment/qixiang/return`，不增加新的自定义 scheme，也不复用 KAI OAuth 的 `kai://auth`。原生收银台只在精确匹配该 origin 和 path 时关闭，随后回到钱包并请求服务端查单；return query、页面文案和客户端回跳均不能作为支付成功凭据。

然后在 HBuilderX 中选择“发行 → 原生 App 云打包”，选择 Android、自有证书和 APK/AAB。keystore、密码、APK/AAB、`.env.local` 与 `dist` 都不得提交到 Git。

## 直接交易包验收

模拟器可以验证页面与能力门禁，但支付宝、微信、外部 App 切换和真实返回必须在至少一台物理 Android 设备上完成。发布前逐项留存证据：

1. 服务器关闭能力时，充值、购买、银行卡和提现入口均不可用；开启后四类入口与 Web、iOS 一致；
2. 七相收银台可分别拉起已获商户权限的支付宝/微信渠道，取消、失败和未安装支付 App 均不会误报成功；
3. 只有 `https://wod.kai.com/payment/qixiang/return` 会关闭原生 WebView，相似域名、额外路径和 `kai://auth` 不会触发支付回跳；
4. 返回钱包后客户端主动查询服务端，只有统一账本确认后才显示充值成功并刷新余额；重复通知和重复返回不重复入账；
5. 充值卡时不能提现，直接订单使用钱包卡时，取消/退款按服务端状态退回钱包或解除冻结；
6. 银行卡登记明确为人工审核，提现申请冻结可提现卡时，运营审核拒绝或打款失败后正确解冻；
7. 增加 `versionCode`，使用正式 keystore 生成并验签 APK/AAB，再更新生产下载元数据；旧 `com.kai.wod` 通道不得指向新包。

Pixel 9 / Android 16 模拟器此前已验证登录、钱包、行情、市场、社区、资产页和个人中心；这不能替代上述生产商户、真机支付、人工打款和回滚演练。
