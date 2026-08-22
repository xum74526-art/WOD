# KAI API

KAI 唯一 FastAPI + SQLAlchemy 业务后端，为 Web、iOS 和 Android 提供账号、商品、行情、订单、资产、钱包、商家、通知、后台任务和受控上传能力。

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
docker build -t kai-api .
```

镜像包含 Tesseract、`chi_sim` 与 `eng`。入口脚本会拒绝空的必需变量和源码内置开发密钥，并在启动前执行 `init_db.py`。

## 数据目录

- 数据库：由 `DATABASE_URL` 指定。
- 上传：`UPLOAD_ROOT`，包含头像、社区媒体、身份证照片和打款凭证。

数据库和上传均不应进入源码仓库。身份证与财务凭证目录应限制为服务账户可读。

## 行情与购买规则

- `https://pricing.kai.com` 是唯一参与商品目录和下单的实时行情源，价格单位为 CNY/GPU-hour。
- 官方历史 OHLC 由定时 Candle Agent 预取到 `market_price_candles`；公开行情接口只读数据库，上游失败时保留最后成功数据。
- Vast.ai 授权报价只写入 `vast_offers`、`vast_price_snapshots` 和 `vast_sync_status` 参考表，不创建商品、不代表平台库存，也不参与下单。
- AutoDL 不再运行采集器或下载任务；已有来源标识、历史快照和订单仍保留用于审计。
- KAI 商品使用显式 `market_source` 与 `external_product_id`，上游最大可配置数量不等同实时库存。
- 新 KAI 订单只接受 `hours`（1–720 的整数）；`cycle_days` 仅用于历史 WOD 日周期订单。
- 下单与续费使用客户端请求号保证幂等，金额、结束时间和续费审计均由后端计算。
- `created_platform`/`last_modified_platform` 来自服务端认证会话，不接受客户端自报平台。

### Vast.ai 授权参考行情

FastAPI 只负责接收标准批次和写数据库。配置独立内部服务令牌：

```dotenv
MARKET_INGESTION_ENABLED=true
MARKET_INGESTION_TOKEN=<独立随机密钥>
```

Collector 位于 `services/collector`，不导入 ORM、不连接数据库。它通过固定接口提交标准化批次：

```text
POST /internal/v1/ingestion/market-offers/batches
```

接口使用 Bearer 服务令牌、Pydantic 严格校验和持久 `batch_id` 幂等；同一个批次重复提交不会重复写入，复用批次号提交不同内容会返回 409。批次中的报价、快照、同步状态和审计记录在同一个数据库事务内提交。

按需报价默认每 10 分钟、竞价每 5 分钟、预留报价每 30 分钟采集。失联报价 30 分钟后标记无效，48 小时后删除；聚合历史默认保留 90 天。API 限流或同步失败时保留上次成功数据。

KAI K 线同步与 Vast Collector 相互独立。默认每 5 分钟更新一次、请求 90 天官方历史并保留 100 天；它不创建商品，
也不把历史价格视为库存。`/api/market/prices/candles` 的
`provenance.dataset_source=market_price_candles` 表示响应来自数据库缓存。

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
