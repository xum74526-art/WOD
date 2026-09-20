# iOS TestFlight 与 App Store 发布清单

本文用于 `apps/ios` 的内部测试、外部 TestFlight 和 App Store 审核。每次发布都从头核对，不能用上一次构建的结论代替最终 IPA 检查。

## 当前发布身份

| 项目 | 当前值 |
|---|---|
| App 名称 | KAI星算 |
| DCloud AppID | `__UNI__47CF9D3` |
| Bundle ID | `com.kai.ztwstarmap` |
| Marketing Version | `1.2.1` |
| Build | `124` |
| 支持设备 | iPhone |
| 生产 API | `https://wod.kai.com/api` |
| 业务模式 | 算力需求撮合；直接交易、支付、充值和提现保持关闭 |

每次上传必须递增 `versionCode`。同一 App Store 版本不能重复上传相同 Build。

## 当前仓库已经具备

- App 首次业务网络请求前展示隐私政策和用户协议；所有服务地区均通过独立勾选确认中国香港存储、处理与必要传输，拒绝时不启动业务联网运行时。
- iOS、Android 与 Web 使用同一 `/api/community` 契约，具备内容过滤、举报、屏蔽、作者删除和管理员处置队列。
- 审核构建由 API 的发布策略关闭第三方聚合内容；客户端的兼容查询参数不能绕过该策略。
- 首版审核由 API 关闭用户图片/视频发布，并隐藏历史用户媒体动态及其详情、评论、点赞和媒体直链；iOS、Android 与 Web 发布器只展示文字和话题入口。
- 社区公开响应不返回用户头像；新注册和资料修改会过滤公开昵称，历史不合规昵称回退为安全通用名称。
- 三端商品卡使用仓库内已完成权利确认的 GPU 图片；Wikimedia Commons 衍生图片的原作、作者、许可、修改方式和型号复用关系记录在各移动端的 `src/static/gpu/ATTRIBUTION.md`，并通过 App 设置中的“图片来源与许可”和 Web `/image-attributions` 向用户公开。其余项目图片由运营方持有所有权或已取得直接使用授权。
- App 内有账号注销入口，公开注销说明可访问。
- iOS 隐私清单位于 `apps/ios/nativeResources/ios/PrivacyInfo.xcprivacy`。
- 相册和相机权限仅用于头像与身份认证资料，说明提供英文、简体中文和繁体中文版本；审核包不声明麦克风用途。
- `dSYMs` 已启用；云打包完成后必须立即下载并归档符号表。
- 生产 API 只允许 HTTPS，DCloud 统计关闭。

这些代码只有在 API、Web 和 App 使用同一已发布提交时才构成完整闭环。若只上传 IPA、未部署新的 API，举报、屏蔽和隐私相关接口会不可用。

## 本地与账号侧准备

发布负责人在本机完成以下项目，证书、密码、审核账号和验证码不得提交 Git：

1. Apple Developer 会员主体和 App 实际经营主体一致。Apple 允许个人/个体经营者和组织加入计划；本项目涉及敏感身份资料、银行卡、钱包和账务功能，为让商店 Seller、隐私政策经营者和实际服务方保持一致，发布方案采用实际运营法律实体的组织会员。若现有会员是个人类型，先完成主体与责任评估，不直接以个人名义提交本项目。
2. 在 Certificates, Identifiers & Profiles 注册显式 App ID `com.kai.ztwstarmap`。
3. 在 App Store Connect 创建 iOS App，Bundle ID 选择上述显式 App ID，SKU 使用内部稳定编号。
4. 创建 Apple Distribution 证书与 App Store Distribution Provisioning Profile，或在 HBuilderX 云打包中使用受控的自动签名流程。
5. 确认本机 Xcode/Transporter 登录的是该团队中有上传权限的账号。
6. 确认 DCloud 账号拥有 `__UNI__47CF9D3`，且使用支持当前 Apple SDK 的最新版 HBuilderX。

发布前本机快速检查：

```bash
security find-identity -v -p codesigning
find "$HOME/Library/MobileDevice/Provisioning Profiles" -type f 2>/dev/null
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild -version
```

没有可用 Distribution 身份或 Profile 时不能生成可上传的正式 IPA，但不影响继续做模拟器和 H5 测试。

模拟器中当前安装的 `io.dcloud.HBuilder` 只是 HBuilder 调试壳，包含的 SDK、权限、Bundle ID 和签名均不代表正式产品包。该调试壳不能上传 App Store Connect，也不能据此填写 App Privacy。只验收并上传使用 `com.kai.ztwstarmap` 生成的 App Store 发布 IPA。

## 构建前门禁

从干净提交执行：

```bash
npm ci --prefix apps/ios
npm ci --prefix apps/android
npm ci --prefix apps/web
npm run check:all
npm run audit:deps
git diff --check
```

同时确认：

- `VITE_ENABLE_DIRECT_TRADE=false`；
- API 发布环境中 `THIRD_PARTY_MERCHANT_PUBLIC_CATALOG_ENABLED=false`，公开目录只展示 KAI 自营资源；
- API 发布环境中 `COMMUNITY_AGGREGATED_CONTENT_ENABLED=false`；
- API 发布环境中 `COMMUNITY_USER_MEDIA_ENABLED=false`；
- 生产 API 的 `/api/v1/health` 正常；
- API、Web 和移动端来自同一提交并已完成服务器部署验收；
- `https://wod.kai.com/privacy/zh-cn` 与 `https://wod.kai.com/terms` 展示的版本、更新日期和正文与 App 内置法律文本一致；
- `https://wod.kai.com/image-attributions` 可公开访问，App 设置中的“图片来源与许可”能够打开并展示简体中文、繁体中文和英文署名；
- 普通用户和商家审核账号可用，验证码、KYC 或待审核状态不会阻断 Apple 审核员；
- 审核账号不要求审核员提交真实身份证或银行卡；
- 账号注销、发帖、评论、举报、屏蔽和客服入口实际可用；
- AI 客服若启用，隐私政策和 App Privacy 已披露服务商、发送数据、目的、地点和保留期限；否则保持自助客服模式；
- KAI 登录若是同一经营主体的第一方统一账号，在 Review Notes 说明主体关系；若属于第三方社交登录，先完成 Sign in with Apple 适用性评估；
- 没有把数据库、上传文件、Token、证书、Profile、`.p12` 或审核账号写入仓库。

## 生成正式 IPA

`npm run build:ios` 只生成 uni-app 资源，不会生成可上传 IPA。正式包使用 HBuilderX：

1. 打开 `apps/ios`。
2. 选择 **发行 → 原生 App-云打包**。
3. 平台选择 iOS，构建类型选择 App Store 发布包。
4. 核对 AppID、Bundle ID、版本、Build、iPhone 设备范围、证书和 Profile。
5. 保持广告标识和统计关闭，不勾选未使用的原生模块。
6. 完成云打包后保存 IPA、完整构建日志和 dSYM；dSYM 下载链接有效期有限，应立即归档。

不要先上传。先对这个最终 IPA 做下节检查。

## 最终 IPA 验收

将实际文件路径代入：

```bash
rm -rf /tmp/kai-ipa-audit
mkdir -p /tmp/kai-ipa-audit
unzip -q /path/to/KAI.ipa -d /tmp/kai-ipa-audit
find /tmp/kai-ipa-audit/Payload \( -name Info.plist -o -name PrivacyInfo.xcprivacy \)
plutil -p /tmp/kai-ipa-audit/Payload/*.app/Info.plist
codesign --verify --deep --strict --verbose=2 /tmp/kai-ipa-audit/Payload/*.app
codesign -d --entitlements :- /tmp/kai-ipa-audit/Payload/*.app
find /tmp/kai-ipa-audit/Payload -name PrivacyInfo.xcprivacy -exec plutil -lint {} \;
find /tmp/kai-ipa-audit/Payload -type d -name '*.framework'
```

验收人记录并截图留档：

- `CFBundleIdentifier`、版本、Build、最低系统版本和设备范围正确；
- `DTSDKName` 显示 iOS 26 或更高版本；Apple 自 2026 年 4 月 28 日起要求上传包使用 iOS 26 SDK 或更高版本构建；
- App 图标和冷启动画面均为本次品牌资源，卸载旧版后重装验证；
- 首页、算力市场和商品详情显示与型号映射一致的已授权 GPU 图片；图片加载失败时仍回退到项目自有中性插图，且设置中的图片署名与最终 IPA 内资源一致；
- 主 App 和所有第三方 Framework 的隐私清单完整；
- Xcode Privacy Report 中的数据类型、域名和 Required Reason API 与实际用途一致；
- 相册和相机只在用户主动选择头像或身份认证资料时请求，三种语言的系统弹窗文案正确；审核包不请求麦克风权限；
- 没有 IDFA、广告、未披露统计、测试服务器、HTTP 域名或不需要的 SDK；
- 仅出现预期域名，账号、社区、上传、注销和客服请求均走 HTTPS；
- dSYM UUID 与构建匹配并已存入发布档案；
- iPhone 小屏、刘海屏和最大尺寸机型完成登录、语言切换、深色模式、后台恢复和注销回归。

最终 IPA 的检测结果优先于源码推断。如果云打包注入了额外 SDK，必须先更新隐私政策、隐私清单和 App Store Connect 申报，再上传。

## App Store Connect 元数据

可直接使用的公开地址：

| 字段 | 地址 |
|---|---|
| Privacy Policy URL | `https://wod.kai.com/privacy/zh-cn` |
| Support URL | `https://wod.kai.com/contact` |
| User Privacy Choices / Account Deletion | `https://wod.kai.com/account-deletion` |
| Terms / EULA | `https://wod.kai.com/terms` |
| Image Sources & Licenses | `https://wod.kai.com/image-attributions` |
| Marketing URL（可选） | `https://wod.kai.com/info` |

还需准备：

- App 名称、副标题、关键词、推广文本和完整描述统一定位为“算力资源信息、需求撮合与技术社区”，避免宣传未开放的购买、充值、提现或收益功能，也不使用“新闻”“资讯聚合”“快讯”等表述；
- iPhone 各要求尺寸的真实截图，至少覆盖首页、算力行情、需求撮合、文字技术社区的举报/屏蔽入口和账号设置；截图不得出现第三方聚合新闻或外部视频；
- 1024×1024 App Store 图标；
- 主类别使用 `Business`，可选副类别使用 `Utilities`，不要选择 `News`；同时完成年龄分级、内容权利、出口合规和地区范围；
- 欧盟《数字服务法》交易者身份申报；即使首版不在欧盟分发，也要在 App Store Connect 完成 trader status 选择，若在欧盟分发则完成地址、电话和邮箱验证及展示要求；
- App Review 联系人、可接听电话和受监控邮箱；
- 两组长期有效且可重置的审核账号：普通用户、已审批商家；
- 登录和主要功能操作说明。审核账号只填 App Store Connect。

## App Privacy 填写底稿

必须以最终 IPA、线上配置和实际服务器日志为准。当前功能至少需要逐项核对：

| Apple 类别 | 可能涉及的数据 | 主要目的 | 通常是否关联身份 |
|---|---|---|---|
| Contact Info | 姓名、手机号、恢复/KAI 邮箱、地址、联系人和联系电话 | App 功能、账号安全、客户支持 | 是 |
| Financial Info | 银行卡登记资料、钱包和账务记录、订单、结算、返佣、退款 | App 功能、防欺诈 | 是 |
| Sensitive Info | 身份证号、证件图片、实名 OCR 与审核结果 | 身份验证、合规 | 是 |
| User Content | 头像、帖子、评论、身份认证图片、需求、报价、客服消息和上传文件 | App 功能、内容安全、客户支持 | 是 |
| Identifiers | 用户 ID、KAI subject、会话标识 | App 功能、账号安全 | 是 |
| Purchases | 订单、资源使用和历史交易记录 | App 功能 | 是 |
| Usage Data | 点赞、关注、发布、搜索和登录操作 | App 功能、内容安全 | 视实际日志而定 |
| Diagnostics | 崩溃、性能和其他诊断 | 稳定性 | 以最终 SDK 为准 |

当前构建不用于跨 App/网站跟踪。不要申报通讯录或定位，除非最终包确实新增并使用对应能力。App Store Connect、隐私政策和 `PrivacyInfo.xcprivacy` 三处必须一致。

## 审核备注模板

根据实际审核账号补全方括号，凭据不要写入本文：

> 本版本为算力资源信息与需求撮合应用。直接交易、在线支付、充值、提现均未开放；用户提交需求后由平台或商家人工确认配置、库存、报价和交付方案。历史账务页面仅用于已存在记录的查看。
>
> 普通审核账号：[在 App Store Connect 填写]；已审批商家账号：[在 App Store Connect 填写]。登录后可测试首页、算力行情、发布需求、社区发帖/评论，以及“我的 → 账号设置 → 注销账号”。审核账号不需要上传真实身份证或银行卡。
>
> 社区仅用于算力产品、站内平台行情与技术交流，不提供新闻采编、转载、公共事务或突发事件报道。社区内容菜单提供举报、屏蔽用户和删除本人内容；管理员通过受保护的审核队列处置举报。首版仅支持文字动态，用户图片/视频发布、历史媒体动态和社区公开头像已由服务端关闭；公开昵称经过内容过滤，第三方聚合内容和视频也已由服务端关闭。首版公开资源目录仅展示 KAI 自营资源，第三方商家店铺和商品公开入口由服务端关闭。
>
> KAI 登录由[同一经营主体/实际关系说明]提供，用于本平台统一账号。若该说明不成立，请在提交前完成 Sign in with Apple 评估和必要实现。
>
> 隐私政策：https://wod.kai.com/privacy/zh-cn；支持：https://wod.kai.com/contact；账号注销说明：https://wod.kai.com/account-deletion。

## TestFlight 顺序

1. 用 Xcode Organizer 或 Transporter 上传已验收 IPA。
2. 等待 App Store Connect 完成 Processing，处理所有 Missing Compliance、隐私或签名提示。
3. 先添加内部测试组，安装后执行完整冒烟测试。
4. 修复崩溃、启动、登录、权限、社区、语言和注销问题并上传更高 Build。
5. 再配置外部测试信息并提交 Beta App Review。
6. 外部测试稳定后，为正式版本选择该 Build，补齐隐私、分级、内容权利、地区和审核信息，再提交 App Review。

内部测试通过不代表正式审核合规；外部 TestFlight 也需要 Beta App Review。

## 中国大陆地区

网站 ICP 备案不能替代移动应用备案。启用中国大陆 storefront 前，应由发布负责人和法务确认：

- APP 备案已完成，主体、App 名称和 Bundle ID 与工信部记录一致；
- 社区与平台行情的实际内容始终保持在算力产品、站内数据和技术交流范围内，且聚合内容门禁持续关闭；
- 实名、银行卡、跨境传输及数据保留流程符合适用要求；
- 开发者会员、App Store Connect Seller、隐私政策经营者和实际运营主体一致。

材料未齐时，首版不要选择中国大陆销售区域；其他地区的上线不免除当地隐私、消费者和内容权利义务。

## 仍需外部确认的发布阻塞

- Apple Distribution 证书、App Store Profile、App Store Connect App 和有上传权限的团队成员已就绪；
- DCloud AppID 所有权和云打包账号已确认；
- 正式 IPA 已完成隐私报告、Required Reason API、SDK、域名、签名和 dSYM 验收；
- API/Web 已部署本次社区安全契约，生产环境保持 `THIRD_PARTY_MERCHANT_PUBLIC_CATALOG_ENABLED=false`、`COMMUNITY_AGGREGATED_CONTENT_ENABLED=false` 和 `COMMUNITY_USER_MEDIA_ENABLED=false`，线上举报队列有人值守并有处理时限；
- 审核账号、截图、元数据、隐私问卷、年龄分级、内容权利和出口合规已填完；
- 欧盟 DSA trader status 已申报，且是否在欧盟分发的决定与所需联系方式验证已完成；
- KAI 登录主体关系、AI 客服模式、短信号码归属验证、数据保留期限和跨境合规已由负责人确认；
- 如启用中国大陆地区，APP 备案及实际业务可能适用的专项资质已完成。

以上项目全部有证据后，才将版本状态标记为“可提交审核”。
