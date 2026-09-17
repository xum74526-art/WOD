# 生产上线状态

本文区分“代码已经通过工程检查”和“业务具备公开运营条件”。前者可以由 CI 验证，后者还
需要证书、商户、隐私合规和运维演练，不应混为一个完成状态。

## 已通过的工程门禁

- FastAPI 是唯一数据库访问者；Collector、Web、H5、iOS 和 Android 不包含数据库配置。
- Web 以 HttpOnly Cookie + `/api/v1/canonical/*` BFF 访问云端 API。
- 原生 App 只接受以 `/api` 结尾的 HTTPS 地址，默认为 `https://wod.kai.com/api`。
- FastAPI OpenAPI 是唯一 HTTP 契约，CI 会拒绝过期快照、旧客户端路由和客户端数据库配置。
- API 单元测试、Web 生产构建、H5/App 生产构建和三套依赖安全审计全部进入 CI。
- Python JWT 已从含无修复 ECDSA 问题的 `python-jose` 迁移到 PyJWT。

## 每次合并前的自动门禁

从仓库根目录执行：

```bash
npm run check:all
npm run audit:deps
git diff --check
```

| 门禁 | 通过标准 |
|---|---|
| API | 编译、单元测试和 OpenAPI 快照通过 |
| Collector | 编译、适配器/内部接入契约测试通过，源码不包含数据库配置 |
| Web | 单元测试、TypeScript 检查和 production build 通过 |
| Mobile | 单元测试、TypeScript 检查及 API 边界检查通过 |
| 移动端构建 | CI 的 H5 和 App production build 通过 |
| 依赖安全 | Python、Web、Mobile 没有命令报告的已知漏洞 |
| Git | 没有意外构建产物、密钥或未解释的兼容代码 |

检查失败必须修复根因；不能通过跳过断言、降低审计级别或提交生成目录获得“通过”。

## 外部上线条件

以下不能由仓库自动生成；未完成时不应宣布 App Store 或应用商店正式上线：

1. 配置正式 DCloud AppID、iOS Bundle ID、Apple 开发者证书和 Provisioning Profile；
2. 确认源码中的正式标识 `com.kai.ztwstarmap` 已在 Android 与 Apple 发布账户登记，并使用长期稳定的签名；
3. 完成手机号短信归属验证，并让用户协议、隐私政策与实际认证、支付和数据处理流程一致；
4. 配置正式客服和个人信息处理联系方式，完成隐私/支付合规审核；
5. 在支付商户沙箱或经授权的小额真实交易中，验证下单、回调、查单、超时和重复回调；
6. 验证云端数据库自动备份、恢复演练、告警和磁盘容量策略。

建议发布负责人在每次正式版本中记录责任人、完成日期和证据链接。仓库中的环境变量示例
只能表明“代码支持该配置”，不能证明生产账号、证书或商户审核已经完成。

## 发布前人工清单

- [ ] 目标提交已经合并到 `main`，本地与 GitHub 提交号一致；
- [ ] CI 全绿，依赖审计没有未接受的风险；
- [ ] 变更包含必要的数据迁移、回滚说明和用户影响说明；
- [ ] 生产密钥、OAuth 回跳、支付回调和域名证书仍有效；
- [ ] 数据库备份完成并确认备份文件非空、权限受限；
- [ ] 支付相关改动已在沙箱或授权环境验证幂等和验签；
- [ ] 启用外部数据采集前已确认来源授权，内部 ingestion token 独立生成且接口未暴露到公网；
- [ ] 值班人员知道本次发布版本、观察指标和回滚版本。

## 发布后人工清单

- [ ] 本机和公网 `/health`、`/api/v1/health` 正常；
- [ ] 首页、登录、市场、行情、社区和资产关键页面可访问；
- [ ] 本地测试 Web、线上 Web 与 Mobile 的同一接口返回一致业务数据；
- [ ] API/Collector/Web 服务 active，日志没有持续异常或重启循环；
- [ ] 磁盘、数据库、上传目录和备份目录容量正常；
- [ ] 记录实际发布提交和可回滚 release 目录。

## 发布准则

代码只在本地修改，通过 `npm run check:all` 和 `npm run audit:deps` 后推送 GitHub。云端只允许 `git pull --ff-only`、安装锁定依赖、构建、备份和重启；禁止在服务器直接编辑源码。

只有上述自动门禁、对应的人工清单和适用的外部上线条件都完成，才能把版本标记为“可公开
生产上线”。详细操作见 [`DEPLOYMENT.md`](DEPLOYMENT.md)。
