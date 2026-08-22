# Android 开发、预览与打包

Android 客户端位于 `apps/android`，正式 applicationId 为 `com.kai.wod`。它与 iOS 使用同一 OpenAPI 和业务状态，但拥有独立的 Android manifest、回跳和发布配置。

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

1. DCloud AppID；
2. 唯一且长期不变的 Android applicationId：`com.kai.wod`；
3. 自有 keystore、别名和密码；
4. 正式 HTTPS API；
5. 版本名与递增的 versionCode。

然后在 HBuilderX 中选择“发行 → 原生 App 云打包”，选择 Android、自有证书和 APK/AAB。keystore、密码、APK/AAB、`.env.local` 与 `dist` 都不得提交到 Git。

## 已验证范围

Pixel 9 / Android 16 模拟器已验证手机号密码登录、统一 100 卡时余额、首页行情、双列算力市场、社区四标签及图片、资产页和个人中心。Android 保留充值与购买算力入口；iOS App Store 版本继续按平台规则隐藏直接交易入口。
