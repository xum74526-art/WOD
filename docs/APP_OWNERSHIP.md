# 客户端目录与职责

本文件定义 KAI monorepo 中各客户端的源码边界。所有客户端共享
`services/api` 提供的唯一业务后端和数据库，不在客户端保存或复制业务数据库。

## 目录归属

| 目录 | 发布目标 | 功能边界 | 数据访问 |
|---|---|---|---|
| `apps/web` | 桌面与移动浏览器 | 功能最完整；通过 Next.js BFF 提供业务与管理界面 | 同源 `/api/v1/canonical/*` |
| `apps/ios` | iPhone/iPad | 行情、小时购买、充值、订单、资产等必要能力；管理能力只读 | FastAPI `/api/*` |
| `apps/android` | Android | 行情、小时购买、充值、订单、资产等必要能力；管理能力只读 | FastAPI `/api/*` |
| `services/api` | 云端 API | 唯一业务规则、认证、支付、数据库和审计所有者 | 唯一允许访问数据库 |
| `packages/api-contracts` | 全客户端 | OpenAPI 快照与客户端契约检查 | 不访问数据库 |

## 共享数据与来源识别

- Web、iOS 和 Android 登录后使用同一个 KAI 用户身份、余额、资产和订单。
- 业务记录只保存一份，不按客户端复制三份。
- 后端在认证会话和可写业务记录上保存来源信息：
  `web`、`ios`、`android`、`admin`、`legacy`；管理员后台可按来源筛选。
- 来源由服务端认证会话固化，不能只信任客户端随意提交的请求头。
- 历史数据没有可靠来源时标记为 `legacy`，不得猜测。

## 实时行情与购买规则

- `KAI Pricing` 是唯一实时行情源；不得恢复 Vast 或 AutoDL 实时采集。
- 新 KAI 商品只按整数小时购买，客户端不得重新发送日周期字段。
- 价格、库存语义、订单状态和支付状态均以后端 OpenAPI 为准。

## Android 迁移白名单

从旧 WOD Android/uni-app 项目仅迁移：

- `src/` 业务源码与打包静态资源；
- `tests/` 客户端测试；
- `scripts/check-i18n.mjs`；
- `package.json`、锁文件、TypeScript、Vite、uni-app 和环境变量示例。

明确不迁移：

- `node_modules/`、`dist/`、`unpackage/`；
- APK/AAB、keystore、云证书缓存及任何签名资料；
- `.env`、Token、数据库、上传文件；
- 日志、QA 截图、临时脚本、自动登录页和本地测试账号；
- 旧的 `WOD-Android-Package` 编译输出。

## 修改规则

1. API 变化先修改 `services/api`，重新导出 OpenAPI，再更新三个客户端。
2. Web 管理功能可以完整；iOS/Android 管理页面只能读取，不能直接执行财务或审核写操作。
3. iOS/Android 若实现相同功能，应保持相同 API 契约和测试用例；平台差异仅限回跳、权限、签名和系统能力。
4. 正式 Android applicationId 固定为 `com.kai.wod`；签名材料不进入仓库。
5. 支付密钥只存在于云端 API 环境，任何客户端都不得包含商户密钥。

## 当前移动端一致性基线

- `apps/ios/src` 与 `apps/android/src` 当前各包含 225 个文件，其中 223 个文件内容一致。
- 两端文件集合一致，除 `src/manifest.json` 和 `src/utils/client-platform.ts` 外，其他源码
  SHA-256 一致。
- 这两个差异分别承载平台打包/回跳配置和服务端 `client_id`，不允许把其中一端的文件直接
  覆盖到另一端。
- 任何共同业务修改必须在两端同步，并分别执行单元测试、类型检查、i18n 审计和 App 构建。
