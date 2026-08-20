# GitHub 上传说明

`KAI-Unified` 已是独立 Git 仓库，主分支为 `main`。网页、iOS/Android、API、Agent 和部署文件应作为一个仓库整体上传，不要再上传两个旧项目目录。

## 应上传

- `apps/web`：Next.js 网页源码、公开图片和锁定文件
- `apps/mobile`：uni-app iOS/Android 源码、静态资源、测试和锁定文件
- `services/api`：FastAPI、Alembic 迁移、测试和非敏感公开数据快照
- `packages/api-contracts`：OpenAPI 契约快照和检查工具
- `agent`：Linux/Windows Agent 源码
- `infra`：Docker/Caddy 配置和仅包含占位值的示例配置
- `docs`、`tooling`、`.github/workflows`
- 根目录 `README.md`、`package.json`、`.gitignore`、`.gitattributes`、`.editorconfig` 和 `.dockerignore`

`docs/ANDROID_TEST_REPORT.md` 是维护的项目验收文档，可以提交。不要提交 Playwright 等工具临时生成的 `playwright-report`/`test-results`/`coverage` 目录。

## 永远不上传

- `.env`、`.env.local`、真实密码、Token 和生产配置
- 私钥、keystore、Apple/Android 签名证书、Provisioning Profile
- `node_modules`、`.venv`、`.next`、`dist`、`unpackage`
- SQLite/PostgreSQL 备份、上传文件、日志、缓存和本地 QA 产物
- IPA、APK、AAB、xcarchive、dSYM 和 DerivedData

## 上传前检查

当前仓库没有远程地址，也没有创建初始提交。先在根目录执行：

```bash
git status --short
git status --ignored --short
git add --dry-run .
git check-ignore -v apps/mobile/.env.local kai.db apps/web/node_modules services/api/.venv
```

预期最后一条命令会显示这些本机文件均由 `.gitignore` 排除。如果待上传列表出现真实 `.env`、数据库、密钥、证书或安装包，应先停止并修正忽略规则。允许提交的例外只有 `.env.example`，以及 `infra/secrets/examples` 中仅含占位文本的示例证书文件。

然后运行项目检查：

```bash
./tooling/check-all.sh
git diff --check
```

## 第一次上传

先在 GitHub 创建一个空仓库，不要让 GitHub 自动生成 README、`.gitignore` 或 License。当仓库地址确定后再执行：

```bash
git add .
git status
git diff --cached --check
git commit -m "chore: initialize unified KAI platform"
git remote add origin git@github.com:你的账号/你的仓库.git
git push -u origin main
```

如果使用 HTTPS，把远程地址换成 `https://github.com/你的账号/你的仓库.git`。

## 后续更新

```bash
git status
git add .
git diff --cached --check
git commit -m "feat: describe the change"
git push
```

正式开源前需要由项目所有者选择 License；当前不会自动假设开源授权。
