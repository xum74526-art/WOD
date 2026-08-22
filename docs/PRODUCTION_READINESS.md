# 生产上线状态

## 已通过的工程门禁

- FastAPI 是唯一数据库访问者；Web、H5、iOS 和 Android 不包含数据库配置。
- Web 以 HttpOnly Cookie + `/api/v1/canonical/*` BFF 访问云端 API。
- 原生 App 只接受以 `/api` 结尾的 HTTPS 地址，默认为 `https://wod.kai.com/api`。
- FastAPI OpenAPI 是唯一 HTTP 契约，CI 会拒绝过期快照、旧客户端路由和客户端数据库配置。
- API 单元测试、Web 生产构建、H5/App 生产构建和三套依赖安全审计全部进入 CI。
- Python JWT 已从含无修复 ECDSA 问题的 `python-jose` 迁移到 PyJWT。

## 外部上线条件

以下不能由仓库自动生成，未完成时只能作为 Web/封闭测试版，不应宣布 App Store 正式上线：

1. 配置正式 DCloud AppID、iOS Bundle ID、Apple 开发者证书和 Provisioning Profile；
2. 将 `com.example.kai` 替换为已登记的正式包名；
3. 完成手机号短信归属验证，并更新用户协议/隐私政策中的封闭测试说明；
4. 配置正式客服和个人信息处理联系方式，完成隐私/支付合规审核；
5. 在支付商户沙箱或经授权的小额真实交易中，验证下单、回调、查单、超时和重复回调；
6. 验证云端数据库自动备份、恢复演练、告警和磁盘容量策略。

## 发布准则

代码只在本地修改，通过 `npm run check:all` 和 `npm run audit:deps` 后推送 GitHub。云端只允许 `git pull --ff-only`、安装锁定依赖、构建、备份和重启；禁止在服务器直接编辑源码。
