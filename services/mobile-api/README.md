# WOD 后端

FastAPI + SQLAlchemy 后端，提供 WOD 全部业务 API、后台同步任务和受控上传能力。

## 本地启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

将本地数据库和上传目录改为：

```dotenv
DATABASE_URL=sqlite:///./wod.db
UPLOAD_ROOT=./uploads
```

生成并填写两个独立密钥：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

然后：

```powershell
python init_db.py
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

## Docker

```powershell
docker build -t wod-backend .
```

镜像包含 Tesseract、`chi_sim` 与 `eng`。入口脚本会拒绝空的必需变量和源码内置开发密钥，并在启动前执行 `init_db.py`。

## 数据目录

- 数据库：由 `DATABASE_URL` 指定。
- 上传：`UPLOAD_ROOT`，包含头像、社区媒体、身份证照片和打款凭证。
- 行情下载缓存：`MARKET_HISTORY_CACHE_ROOT`；为空时使用应用默认私有缓存目录。

数据库、上传和缓存均不应进入源码仓库。身份证与财务凭证目录应限制为服务账户可读。

## 测试

```powershell
python -m compileall -q app init_db.py
python -m unittest discover -s tests -p "test_*.py" -v
```

## 数据库迁移

项目当前未使用 Alembic，`init_db.py` 包含建表和向后兼容迁移。规则：

1. 对已有数据库执行前先做一致性备份。
2. 首次在数据库副本上执行两次，确认幂等及业务计数守恒。
3. 再在短维护窗口执行正式迁移。
4. 不要删除迁移标记或手工重放资金迁移。

## 安全边界

- OCR 只做身份证图片文字预审，最终结果必须由财务管理员确认。
- 银行卡登记只做格式、Luhn 和本地实名姓名一致性，不是银行核验。
- 提现由系统冻结可提现余额，管理员在银行端人工打款后上传凭证；系统不提供自动代付。
- 支付回调必须验签，并且订单数据库与回调环境必须一致。
- 调度器和部分状态同步按单 worker 设计；直接增加 Uvicorn workers 会重复执行任务。
